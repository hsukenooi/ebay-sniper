# eBay API Call Optimization Analysis

## Current Call Map

### eBay API Endpoints Called

1. **Browse API - getItemByLegacyId** (`get_auction_details`)
   - Used for: Fetching auction details (price, end time, title, URL)
   - Called from:
     - `POST /sniper/add` - When adding new listing
     - `POST /sniper/bulk` - When bulk adding listings
     - `GET /sniper/list` - Refresh-on-read (if cache expired >60s)
     - `GET /sniper/{id}/status` - Refresh-on-read (if cache expired >60s)
     - `Worker._pre_bid_price_check` - At T-60s before auction end
   - Frequency: Up to once per stale auction per request

2. **Trading API - PlaceBid** (`place_bid`)
   - Used for: Placing bids on auctions
   - Called from: `Worker._execute_bid` (with retry logic, max 4 attempts)
   - Frequency: Once per auction at T-3s (with retries)

3. **Offer API - getBidding** (`get_auction_outcome`)
   - Used for: Checking if auction was won/lost
   - Called from: `Worker._check_auction_outcomes` (after auction ends)
   - Frequency: Once per ended auction with BidPlaced status

4. **Trading API - GetItem** (`get_final_price_from_trading_api`)
   - Used for: Getting final price for ended auctions
   - Called from: `Worker._check_auction_outcomes` (for ended auctions without final price)
   - Frequency: Once per ended auction without final price

5. **OAuth Token Endpoints** (`refresh_app_token`, `refresh_user_token`)
   - Used for: Refreshing access tokens
   - Called from: Various places when tokens expire
   - Frequency: As needed when tokens expire

### Current Call Patterns by Request Path

#### POST /sniper/add
- 1x `get_auction_details` (always)

#### POST /sniper/bulk
- Nx `get_auction_details` (one per item, sequentially)

#### GET /sniper/list
- For each auction with `last_price_refresh_utc` older than 60s:
  - 1x `get_auction_details`
- **Issue**: If list has 20 stale auctions, makes 20 sequential API calls

#### GET /sniper/{id}/status
- 1x `get_auction_details` (if cache expired >60s)
- **Issue**: Multiple concurrent requests for same listing could trigger duplicate calls

#### Worker Loop
- `_pre_bid_price_check`: 1x `get_auction_details` at T-60s per auction
- `_execute_bid`: 1-4x `place_bid` at T-3s per auction (with retries)
- `_check_auction_outcomes`: 1x `get_auction_outcome` + optionally 1x `get_final_price_from_trading_api` per ended auction

### Identified Issues

1. **No Request Coalescing**: Multiple concurrent requests for same listing_number trigger duplicate eBay calls
2. **Sequential Refresh Calls**: `list` endpoint refreshes stale auctions sequentially (slow)
3. **No Rate Limit Handling**: 429 errors cause request to fail instead of returning cached data
4. **Redundant Calls for Terminal States**: Auctions in terminal states (Cancelled, Failed, BidPlaced, Skipped) still get refreshed in list/status
5. **Worker Loop Potential Issues**: Worker might make unnecessary calls if scheduling logic isn't strict
6. **Token Refresh Optimization**: Token refresh might happen multiple times unnecessarily

## Optimization Plan

### Phase 2A: Consolidate Auction Detail Fetches
- ✅ Already consolidated via `get_auction_details` method
- Need to ensure all callers use it consistently

### Phase 2B: Strengthen Cache Semantics
1. **Request Coalescing**: Add in-memory lock per listing_number to prevent duplicate concurrent calls
2. **Rate Limit Handling**: Return cached data with warning when 429 occurs
3. **Cache Key Structure**: Already exists in DB (listing_number, last_price_refresh_utc)

### Phase 2C: Batch/Parallelize Refresh Calls
- Parallelize refresh calls in `list` endpoint with concurrency limit (e.g., 5)
- Use ThreadPoolExecutor or asyncio if server becomes async

### Phase 2D: Skip Terminal State Refreshes
- Skip refresh for auctions with status: Cancelled, Failed, BidPlaced (if ended), Skipped
- Only refresh Scheduled, Executing, and BidPlaced (if not ended)

### Phase 2E: Worker Loop Call Minimization
- ✅ Already correct: Worker only calls eBay at T-60s and T-3s
- Verify no unnecessary calls in scheduling logic

### Phase 2F: Token Refresh Optimization
- Cache token refresh results briefly to avoid duplicate refresh calls
- Use expiry timestamps to avoid unnecessary refreshes

### Phase 3: Speed Optimizations
- ✅ Added DB index on last_price_refresh_utc (was missing)
- ✅ Already has indexes on status, auction_end_time_utc, listing_number
- ✅ add-bulk already uses single request
- ✅ Parallelized refresh calls in list endpoint (max 5 concurrent)

## Implementation Summary

### Completed Optimizations

1. **Request Coalescing (Phase 2B)**
   - Implemented `RequestCoalescer` class in `server/cache.py`
   - Prevents duplicate concurrent eBay API calls for same listing_number
   - Used in `_refresh_auction_price()` for status and list endpoints

2. **Rate Limit Handling (Phase 2B)**
   - Modified `_refresh_auction_price()` to handle 429 (rate limit) errors
   - Returns cached data with warning when rate-limited
   - Doesn't update last_price_refresh_utc so retry happens on next request

3. **Terminal State Skipping (Phase 2D)**
   - Modified `_should_refresh_price()` to skip refresh for:
     - Cancelled auctions
     - Failed auctions
     - Skipped auctions
     - BidPlaced auctions that have ended
   - Only refreshes active auctions (Scheduled, Executing, BidPlaced if not ended)

4. **Parallel Refresh Calls (Phase 2C)**
   - Modified `list_snipers()` to refresh stale auctions in parallel
   - Uses ThreadPoolExecutor with max_workers=5 to limit concurrency
   - Each refresh uses its own DB session for thread safety

5. **Database Index (Phase 3)**
   - Added index on `last_price_refresh_utc` column
   - Improves query performance for refresh-on-read checks

6. **Worker Loop Verification (Phase 2E)**
   - Verified worker only calls eBay API at:
     - T-60s: Pre-bid price check (`_pre_bid_price_check`)
     - T-3s: Bid execution (`place_bid`)
     - After auction ends: Outcome check and final price fetch
   - No unnecessary calls identified

7. **Token Refresh (Phase 2F)**
   - Already optimized: `_ensure_token_valid()` checks expiration before refreshing
   - Token refresh is idempotent and relatively fast

### Before/After Call Count Estimates

**Before:**
- `GET /sniper/list` with 20 stale auctions: 20 sequential eBay calls (could be ~10-20 seconds)
- `GET /sniper/{id}/status` concurrent requests: N calls for same listing (duplicate work)
- Rate limit (429): Request fails, no cached data returned

**After:**
- `GET /sniper/list` with 20 stale auctions: 5 parallel batches = ~4-8 seconds (faster, respects rate limits)
- `GET /sniper/{id}/status` concurrent requests: 1 call for same listing (coalesced)
- Rate limit (429): Cached data returned with warning
- Terminal state auctions: 0 calls (skipped)

### Tests Added

1. `test_cache_coalescing.py`: Unit tests for request coalescing
   - Concurrent requests coalesce to single execution
   - Different keys execute separately
   - Errors propagate to all waiters
   - clear_key functionality

2. `test_api_optimizations.py`: Unit tests for refresh logic
   - Terminal states skip refresh
   - Active states refresh if stale
   - TTL behavior (60s cache)

3. `test_api_call_counts.py`: Integration test structure
   - Call count verification (structure provided)

### Remaining Risks / Follow-ups

1. **DB Migration Required**: The index on `last_price_refresh_utc` needs a migration
   - Can be done via: `CREATE INDEX IF NOT EXISTS idx_auctions_last_price_refresh_utc ON auctions(last_price_refresh_utc);`

2. **Thread Safety**: RequestCoalescer uses threading.Lock and Event, tested with concurrent requests

3. **Memory Leaks**: RequestCoalescer cleans up completed requests to prevent memory leaks

4. **Worker Loop**: Verified correct behavior, no changes needed

5. **Token Refresh**: Already optimized, no further work needed

