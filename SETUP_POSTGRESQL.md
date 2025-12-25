# Setting Up PostgreSQL for Local Development

This guide will help you set up PostgreSQL locally to match your production environment on Railway.

## macOS Setup (Your System)

### Step 1: Install PostgreSQL

```bash
# Using Homebrew (recommended)
brew install postgresql@16

# Start PostgreSQL service
brew services start postgresql@16
```

### Step 2: Create Database and User

```bash
# Connect to PostgreSQL
psql postgres

# In psql, run:
CREATE DATABASE ebay_sniper;
CREATE USER postgres WITH PASSWORD 'postgres';
ALTER USER postgres CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE ebay_sniper TO postgres;
\q
```

**Or use the default postgres user:**
```bash
# If postgres user already exists, just create the database
createdb ebay_sniper
```

### Step 3: Update .env File

Update your `.env` file:
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ebay_sniper
```

**⚠️ Important:** Replace `postgres:postgres` with your actual PostgreSQL username:password if different.

### Step 4: Verify Connection

```bash
# Test connection
psql -d ebay_sniper -c "SELECT version();"

# Or using the connection string
psql "postgresql://postgres:postgres@localhost:5432/ebay_sniper" -c "SELECT 1;"
```

### Step 5: Initialize Database Schema

When you first run the server, it will automatically create the tables:

```bash
python3 -m server
```

Or manually initialize:
```bash
python3 -c "from database import init_db; init_db()"
```

## Troubleshooting

### PostgreSQL not running
```bash
# Check status
brew services list

# Start if stopped
brew services start postgresql@16
```

### Connection refused
- Ensure PostgreSQL is running: `brew services start postgresql@16`
- Check if port 5432 is in use: `lsof -i :5432`
- Verify connection string in `.env`

### Permission denied
- Check user permissions: `psql -U postgres -l`
- Ensure user has CREATEDB privilege

### Database already exists
If you need to start fresh:
```bash
dropdb ebay_sniper
createdb ebay_sniper
```

## Migrating from SQLite

If you have existing data in SQLite (`sniper.db`), you'll need to export and import:

1. **Export from SQLite:**
   ```bash
   sqlite3 sniper.db .dump > dump.sql
   ```

2. **Import to PostgreSQL:**
   ```bash
   # Convert SQLite syntax to PostgreSQL (may need manual adjustments)
   psql -d ebay_sniper < dump.sql
   ```

   **Note:** SQLite and PostgreSQL have different syntax, so you may need to manually adjust the SQL file.

3. **Alternative: Start fresh**
   - Simply delete `sniper.db`
   - Start server with PostgreSQL - it will create empty tables
   - Add your listings again via CLI

