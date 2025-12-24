# Implementation Notes

## Core Architecture

### Server Components
- **API Server** (`server/api.py`): FastAPI server providing REST endpoints
- **Worker** (`server/worker.py`): Single long-running worker loop that executes bids
- **eBay Client** (`server/ebay_client.py`): Handles eBay API interactions
- **Database** (`database/models.py`): SQLAlchemy models for Auction and BidAttempt

### CLI Components
- **CLI** (`cli/main.py`): Click-based command-line interface
- **Client** (`cli/client.py`): HTTP client for server communication
- **Config** (`cli/config.py`): Local configuration (token, timezone)

## Key Implementation Details

### Idempotency
- Atomic database update: `Scheduled → Executing` transition ensures only one bid attempt
- If update affects 0 rows, auction is already being processed or in terminal state
- Each auction has at most one BidAttempt record (unique constraint on auction_id)

### Price Refresh Logic
- Cache TTL: 60 seconds
- Refreshes occur:
  1. On `sniper add` (always)
  2. On `sniper list` (if cached price > 60s old)
  3. On `sniper status` (if cached price > 60s old)
  4. Exactly once at T-60s before bid execution

### Pre-Bid Price Check (T-60s)
- Fetches current price from eBay
- If `current_price > max_bid`: Set status to `Skipped`, record reason
- If price fetch fails: Log error, continue with execution (do NOT skip)
- Not retried

### Bid Execution
- Timing: `auction_end_time_utc - 3 seconds` (configurable via BID_OFFSET_SECONDS)
- Bid amount: `max_bid` (eBay's proxy bidding system will automatically bid incrementally up to this amount)
- Retry strategy:
  - Max 4 attempts
  - Delays: 100ms → 250ms → 500ms
  - Timeout: 300-600ms per request
  - Abort if `now >= auction_end_time_utc - 300ms`
- Retry conditions: Network timeouts, eBay 5xx, 429 (if time allows)
- No retries: Auction ended, invalid bid, non-recoverable auth errors

### Auction State Transitions
- `Scheduled → Skipped`: Price > max_bid at T-60s
- `Scheduled → Executing`: At bid execution time (atomic update)
- `Executing → BidPlaced`: Bid succeeded
- `Executing → Failed`: Bid failed (all retries exhausted or non-retryable error)
- `Scheduled → Cancelled`: User cancelled via CLI

Terminal states (never execute bid): `Skipped`, `Cancelled`, `BidPlaced`, `Failed`

### Worker Crash Recovery
- If auction stuck in `Executing` state and `auction_end_time_utc` has passed → mark `Failed`
- Handled in worker loop on each iteration

### OAuth Token Management
- Server owns OAuth tokens (set via `EBAY_OAUTH_TOKEN` env var or `set_oauth_token()`)
- Token refresh should occur ~5 minutes before auction end (placeholder implemented)
- Token stored in memory (single-tenant design)

## Database Schema

### Auction Table
- `id`: Primary key
- `listing_number`: eBay listing ID (indexed)
- `listing_url`: Full URL to listing
- `item_title`: Item name
- `current_price`: Current auction price (cached)
- `max_bid`: User's maximum bid amount
- `currency`: Currency code (default: USD)
- `auction_end_time_utc`: Auction end time in UTC (indexed)
- `last_price_refresh_utc`: Last time price was fetched
- `status`: Current state (indexed)
- `skip_reason`: Reason for skipping (nullable)
- `created_at`, `updated_at`: Timestamps

### BidAttempt Table
- `auction_id`: Foreign key to Auction (primary key, unique)
- `attempt_time_utc`: When bid was attempted
- `result`: `success` or `failed`
- `error_message`: Error details if failed (nullable)

## CLI Commands

All commands require authentication (stored token in `~/.ebay-sniper/token.txt`).

- `sniper auth`: Authenticate and store token
- `sniper add <listing_number> <max_bid>`: Add new sniper
- `sniper list`: List all snipers (refreshes prices if stale)
- `sniper status <auction_id>`: Get auction status (refreshes price if stale)
- `sniper remove <auction_id>`: Cancel sniper (only if Scheduled)
- `sniper logs <auction_id>`: View bid attempt logs

## Timezone Handling

- Server stores all times in UTC
- CLI converts to user's local timezone (stored in `~/.ebay-sniper/config.json`)
- Default timezone: UTC

## Notes

- eBay Trading API requires XML format for bid placement (PlaceOffer call)
- Current implementation includes XML structure but may need refinement per eBay API docs
- OAuth token refresh logic is a placeholder - implement actual refresh flow for production
- Single-tenant design assumes one user/instance

