# eBay Bid Sniping System

A server-backed eBay bid sniping system with CLI interface. Automatically places bids on eBay auctions at the optimal time.

## Architecture

- **Server**: FastAPI server with embedded worker loop that executes bids
- **CLI**: Command-line interface that communicates with the server via HTTP
- **Database**: PostgreSQL (used for both local development and production)
- **Worker**: Background thread that monitors auctions and places bids 3 seconds before auction end

## Requirements

- Python 3.8 or higher
- PostgreSQL (local development) or Railway PostgreSQL (production)

## Quickstart

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# eBay API Configuration
EBAY_APP_ID=your_ebay_app_id
EBAY_CERT_ID=your_ebay_cert_id
EBAY_DEV_ID=your_ebay_dev_id
EBAY_ENV=sandbox  # or 'production' for live auctions

# OAuth Tokens (required for bidding)
EBAY_OAUTH_TOKEN=your_user_access_token
EBAY_OAUTH_REFRESH_TOKEN=your_refresh_token
EBAY_OAUTH_APP_TOKEN=your_app_token  # Optional, recommended

# Server Configuration
SECRET_KEY=your-generated-secret-key  # Generate with: openssl rand -hex 32
DATABASE_URL=postgresql://username:password@localhost:5432/ebay_sniper

# CLI Configuration (optional)
SNIPER_SERVER_URL=http://localhost:8000
```

**Getting eBay Tokens:**

Use the helper script to obtain OAuth tokens:
```bash
python3 scripts/get_ebay_tokens.py
```

Or follow eBay's OAuth authorization code flow manually (see [eBay Developer Docs](https://developer.ebay.com/api-docs/static/oauth-consent-request.html)).

### 3. Setup PostgreSQL (Local Development)

**macOS:**
```bash
brew install postgresql@16
brew services start postgresql@16
createdb ebay_sniper
```

**Linux:**
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createdb ebay_sniper
```

Update `DATABASE_URL` in your `.env` file with your PostgreSQL credentials.

### 4. Start the Server

The server initializes the database schema automatically on startup:

```bash
python3 -m server
```

The server runs on `http://localhost:8000` by default (or use `PORT` env var to override).

### 5. Use the CLI

In another terminal:

```bash
# Authenticate
python3 -m cli auth

# Add a listing
python3 -m cli add 123456789012 150.00

# Bulk add listings (reads from stdin until EOF)
# Option 1: Pipe input
echo -e "123456789012 150.00\n234567890123 200.00" | python3 -m cli add-bulk

# Option 2: Paste and submit
python3 -m cli add-bulk
# Paste your listings (one per line), then press Ctrl+D (Unix/macOS) or Ctrl+Z+Enter (Windows) to submit

# List all listings
python3 -m cli list

# Show details for a specific listing
python3 -m cli show 1

# Get status
python3 -m cli status 1

# Remove a listing
python3 -m cli remove 1

# View bid attempt logs
python3 -m cli logs 1
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EBAY_APP_ID` | Yes | eBay Application ID (Client ID) |
| `EBAY_CERT_ID` | Yes | eBay Certificate ID (Client Secret) |
| `EBAY_DEV_ID` | No | eBay Developer ID (kept for compatibility) |
| `EBAY_ENV` | Yes | `sandbox` or `production` |
| `EBAY_OAUTH_TOKEN` | Yes | User OAuth access token (for bidding) |
| `EBAY_OAUTH_REFRESH_TOKEN` | Yes | User OAuth refresh token (for auto-refresh) |
| `EBAY_OAUTH_APP_TOKEN` | No | Application OAuth token (optional, recommended) |
| `SECRET_KEY` | Yes | JWT signing secret (generate with `openssl rand -hex 32`) |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SNIPER_SERVER_URL` | No | Server URL for CLI (defaults to `http://localhost:8000`) |
| `PORT` | No | Server port (defaults to `8000`) |

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Specific test suites
pytest tests/unit/
pytest tests/integration/
```

## Deployment

### Railway

1. Create a Railway project and add PostgreSQL service
2. Deploy from GitHub or using Railway CLI
3. Set environment variables in Railway dashboard (all variables listed above)
4. Railway automatically sets `DATABASE_URL` from PostgreSQL service

The `Procfile` is configured for Railway:
```
web: python -m server
```

For Railway deployments, the `PORT` environment variable is automatically set by Railway.

### Database Migrations

Migrations are manual. See `migrations/README.md` for migration scripts and instructions.

## Features

- Idempotent bid execution (atomic database updates)
- Price refresh on read (60-second cache TTL)
- Pre-bid price check at T-60s (skips if price exceeds max bid)
- Retry logic for bid execution (4 attempts with exponential backoff)
- Automatic token refresh
- Timezone-aware CLI (converts UTC to local time)
