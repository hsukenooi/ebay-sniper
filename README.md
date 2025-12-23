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

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Get eBay API Credentials

You need to register your application with eBay to get API credentials:

1. Go to [eBay Developers Program](https://developer.ebay.com/)
2. Sign in or create an account
3. Go to "My Account" → "Keys & Tokens"
4. Create a new app to get:
   - **App ID (Client ID)**
   - **Cert ID (Client Secret)**
   - **Dev ID**
5. For OAuth token, you'll need to obtain a **User OAuth token** (not Application token) because placing bids requires user authorization. Complete eBay's OAuth authorization code flow to get a user access token.

### 3. Configure Environment Variables

Copy the example environment file and fill in your actual values:

```bash
cp .env.example .env
```

Then edit `.env` and replace the placeholders with your actual eBay API credentials and configuration:

```bash
# eBay API Configuration
EBAY_APP_ID=your_ebay_app_id              # Replace with your actual App ID
EBAY_CERT_ID=your_ebay_cert_id            # Replace with your actual Cert ID
EBAY_DEV_ID=your_ebay_dev_id              # Replace with your actual Dev ID
EBAY_ENV=sandbox                          # Use 'sandbox' for testing, 'production' for live
EBAY_OAUTH_TOKEN=your_oauth_token_here    # User OAuth token (required for placing bids)

# Server Configuration
SECRET_KEY=your-generated-secret-key      # Generate with: openssl rand -hex 32
DATABASE_URL=sqlite:///./sniper.db        # For local development (SQLite)

# Optional: Server URL (for CLI to connect to remote server)
SNIPER_SERVER_URL=http://localhost:8000
```

**Important Notes:**
- `SECRET_KEY`: Generate a random secret key for JWT token signing (e.g., use `openssl rand -hex 32`)
- `EBAY_ENV`: Use `sandbox` for testing, `production` for live auctions
- `DATABASE_URL`: Defaults to SQLite. For Railway deployment, this is automatically set by Railway's PostgreSQL service
- `EBAY_OAUTH_TOKEN`: **User OAuth token** (not Application token). This is required because the system needs to place bids on your behalf, which requires user authorization. Obtain this through eBay's OAuth authorization code flow. The token must be refreshed periodically (typically expires after 18 months for user tokens).

### 4. Initialize Database

**For Local Development (SQLite):**
The database is automatically initialized when you first run the server. The default SQLite database will be created at `./sniper.db`.

**For Railway Deployment (PostgreSQL):**
The database schema will be automatically created on first deployment. Railway's PostgreSQL service handles this automatically when `DATABASE_URL` is set.

### 5. Run the Server

Start the server (runs on `http://localhost:8000` by default):

```bash
python3 -m server
```

The server will:
- Initialize the database schema automatically
- Start the FastAPI API server on port 8000
- Start the worker loop in a background thread to execute bids

**Running in Production:**

For production use, consider using a process manager like `systemd` or running with `gunicorn`:

```bash
# Using gunicorn (install: pip install gunicorn)
gunicorn -w 1 -k uvicorn.workers.UvicornWorker server.api:app --bind 0.0.0.0:8000
```

**Background Execution (Local):**

To run in the background on Linux/macOS:
```bash
nohup python3 -m server > server.log 2>&1 &
```

### 7. Deploy to Railway with PostgreSQL

For production use, deploy the server to Railway so it runs 24/7 and can execute bids even when your local machine is off. Railway provides easy deployment with managed PostgreSQL databases.

#### Prerequisites

1. Sign up for a Railway account at [railway.app](https://railway.app) (free tier available)
2. Have your GitHub repository ready (or deploy from local files)
3. Have your eBay API credentials ready (from Step 2)

#### Step 1: Create a Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click "New Project"
3. Choose "Deploy from GitHub repo" (recommended) or "Empty Project"

#### Step 2: Add PostgreSQL Database

1. In your Railway project dashboard, click "+ New"
2. Select "Database" → "Add PostgreSQL"
3. Railway will create a PostgreSQL database instance
4. Once created, click on the PostgreSQL service
5. Go to the "Variables" tab
6. Copy the `DATABASE_URL` value (you'll need this in the next step)

**Note:** Railway automatically sets `DATABASE_URL` as an environment variable, so you don't need to manually add it. However, if you want to verify, you can see it in the "Variables" tab.

#### Step 3: Deploy Your Application

**Option A: Deploy from GitHub (Recommended)**

1. In your Railway project, click "+ New" → "GitHub Repo"
2. Select your `ebay-sniper` repository
3. Railway will automatically detect Python and start building
4. The deployment will fail initially (missing environment variables) - this is expected

**Option B: Deploy from Local Files**

1. Install Railway CLI:
   ```bash
   npm i -g @railway/cli
   railway login
   ```
2. In your project directory:
   ```bash
   railway init
   railway up
   ```

#### Step 4: Configure Environment Variables

1. In Railway dashboard, click on your application service (not the database)
2. Go to the "Variables" tab
3. Add the following environment variables (use the values from your `.env.example` file as a template, but replace placeholders with your actual values):

   **Required Variables:**
   ```
   EBAY_APP_ID=your_ebay_app_id
   EBAY_CERT_ID=your_ebay_cert_id
   EBAY_DEV_ID=your_ebay_dev_id
   EBAY_OAUTH_TOKEN=your_oauth_token
   EBAY_ENV=production
   SECRET_KEY=your-generated-secret-key
   ```

   **For reference, here's what each variable means:**
   - `EBAY_APP_ID`, `EBAY_CERT_ID`, `EBAY_DEV_ID`: Your eBay API credentials from [eBay Developers](https://developer.ebay.com/)
   - `EBAY_OAUTH_TOKEN`: Your eBay **User OAuth access token** (required for placing bids - must be obtained through eBay's OAuth authorization code flow, not an Application token)
   - `EBAY_ENV`: Set to `sandbox` for testing, `production` for live auctions
   - `SECRET_KEY`: A random secret key for JWT token signing (generate with `openssl rand -hex 32`)

   **Database Variable (Already Set):**
   - `DATABASE_URL` is automatically provided by Railway's PostgreSQL service
   - You don't need to add this manually - Railway connects services automatically
   - If you need to reference it, it will be in the format: `postgresql://postgres:password@hostname:5432/railway`

4. To generate a secure `SECRET_KEY`, run:
   ```bash
   openssl rand -hex 32
   ```

**Note:** For local development, you can copy `.env.example` to `.env` and fill in your actual values:
```bash
cp .env.example .env
# Then edit .env with your actual credentials
```

#### Step 5: Install PostgreSQL Driver

Since we're using PostgreSQL, you need to add the PostgreSQL adapter to your requirements:

1. Add to `requirements.txt`:
   ```
   psycopg2-binary==2.9.9
   ```

2. If deploying from GitHub, commit and push:
   ```bash
   git add requirements.txt
   git commit -m "Add PostgreSQL support"
   git push
   ```

3. Railway will automatically rebuild and redeploy

#### Step 6: Verify Deployment

1. After deployment completes, Railway will provide a URL like `https://your-app.up.railway.app`
2. Click on your application service → "Settings" → "Generate Domain" if you want a custom domain
3. Check the deployment logs to ensure the database initialized correctly:
   - Click on your application service
   - Go to "Deployments" tab
   - Click on the latest deployment
   - Check logs for "Database initialized" message

#### Step 7: Configure CLI to Use Remote Server

Update your local CLI to point to the Railway server:

**Option 1: Environment Variable**
```bash
export SNIPER_SERVER_URL=https://your-app.up.railway.app
```

**Option 2: Update CLI Config File**
```bash
# Edit ~/.ebay-sniper/config.json
{
  "timezone": "America/New_York",
  "server_url": "https://your-app.up.railway.app"
}
```

**Option 3: Update CLI Code**
Edit `cli/config.py` and change:
```python
SERVER_URL = os.getenv("SNIPER_SERVER_URL", "https://your-app.up.railway.app")
```

Then test the connection:
```bash
python3 -m cli auth
python3 -m cli list
```

#### Step 8: Monitor Your Deployment

1. **View Logs:** Click on your application service → "Deployments" → Latest deployment → View logs
2. **Check Database:** Railway provides a database GUI - click on PostgreSQL service → "Data" tab
3. **Metrics:** View resource usage in the "Metrics" tab

#### Troubleshooting Railway Deployment

**Database Connection Issues:**
- Ensure `psycopg2-binary` is in `requirements.txt`
- Verify PostgreSQL service is running in Railway dashboard
- Check that `DATABASE_URL` is automatically available (Railway connects services automatically)

**Application Not Starting:**
- Check deployment logs for errors
- Verify all required environment variables are set
- Ensure Python version is compatible (Railway auto-detects from your code)

**Environment Variables Not Working:**
- Make sure variables are set on the application service, not the database service
- Restart the deployment after adding variables
- Check variable names match exactly (case-sensitive)

#### Railway Pricing

- **Free Tier:** $5/month credit (usually enough for small deployments)
- **Pay-as-you-go:** Charges for actual usage
- PostgreSQL: ~$5/month for starter database
- Application hosting: Minimal charges for low-traffic apps

For a personal bid sniping system, the free tier credits are usually sufficient.

### 6. Use the CLI

In another terminal, authenticate and use the CLI:

```bash
# Authenticate (any username/password works with default auth)
python3 -m cli auth

# Add a sniper for an auction
python3 -m cli add 123456789 150.00

# List all active snipers
python3 -m cli list

# Check status of a specific auction
python3 -m cli status 1

# Remove (cancel) a sniper
python3 -m cli remove 1

# View bid attempt logs
python3 -m cli logs 1
```

### Troubleshooting

**Database Issues:**
- If you see database errors, ensure the directory is writable
- For SQLite: check file permissions on `sniper.db`
- For PostgreSQL: ensure the database exists and connection string is correct

**eBay API Issues:**
- Verify your API credentials are correct
- Check that `EBAY_OAUTH_TOKEN` is valid and not expired
- For sandbox: ensure `EBAY_ENV=sandbox`
- Check eBay API status and rate limits

**Server Not Starting:**
- Verify all dependencies are installed: `pip3 install -r requirements.txt`
- Check port 8000 is not already in use
- Review server logs for error messages

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

