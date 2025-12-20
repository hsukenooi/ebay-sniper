# eBay Bid Sniping System

A server-backed eBay bid sniping system with CLI interface.

## Prerequisites

This project requires Python 3.8 or higher.

### Installing Python and pip

**macOS:**
```bash
# Using Homebrew (recommended)
brew install python3

# Verify installation
python3 --version
pip3 --version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3 python3-pip

# Verify installation
python3 --version
pip3 --version
```

**Linux (Fedora/RHEL/CentOS):**
```bash
sudo dnf install python3 python3-pip

# Verify installation
python3 --version
pip3 --version
```

**Windows:**
1. Download Python from [python.org](https://www.python.org/downloads/)
2. Run the installer and check "Add Python to PATH"
3. Verify installation:
```cmd
python --version
pip --version
```

**Note:** On some systems, use `python3` and `pip3` instead of `python` and `pip`.

## Setup

1. Install dependencies:
```bash
pip3 install -r requirements.txt
```

2. Configure environment variables (create `.env` file):
```
EBAY_APP_ID=your_ebay_app_id
EBAY_CERT_ID=your_ebay_cert_id
EBAY_DEV_ID=your_ebay_dev_id
EBAY_REDIRECT_URI=your_redirect_uri
SECRET_KEY=your_secret_key_for_jwt
```

3. Configure eBay OAuth token (set `EBAY_OAUTH_TOKEN` in `.env` or environment)

4. Run the server:
```bash
python -m server
```

5. Use the CLI (in another terminal):
```bash
python -m cli auth
python -m cli add <listing_number> <max_bid>
python -m cli list
python -m cli status <auction_id>
python -m cli remove <auction_id>
python -m cli logs <auction_id>
```

## Architecture

- **Server**: FastAPI server with single-worker bid execution loop
- **CLI**: Click-based CLI that communicates with server via HTTPS
- **Database**: SQLite (single-tenant, can be changed via DATABASE_URL)
- **Worker**: Long-running loop that checks auctions and executes bids at T-3 seconds

## Key Features

- Idempotent bid execution (atomic DB updates)
- Price refresh on read only (60s cache TTL)
- Pre-bid price check at T-60s (skips if price > max bid)
- Retry logic for bid execution (4 attempts with exponential backoff)
- Terminal state management (no duplicate bids)
- Timezone-aware CLI (converts UTC to local time)

## Testing

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=. --cov-report=html
```

Run specific test suites:
```bash
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only
```

See `tests/README.md` for more testing details.

