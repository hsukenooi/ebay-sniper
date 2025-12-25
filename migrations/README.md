# Database Migrations

This directory contains database migration scripts for updating the schema.

## Migration: Add Seller Name Field

This migration adds a new column to the `auctions` table:
- `seller_name`: Stores the eBay seller's username or userId

### Running the Migration

**Using Railway CLI:**
```bash
railway run python migrations/migrate_add_seller_name.py
```

**Using Railway Dashboard SQL Editor:**
```sql
ALTER TABLE auctions ADD COLUMN IF NOT EXISTS seller_name VARCHAR;
```

---

## Migration: Add Outcome and Final Price Fields

This migration adds two new columns to the `auctions` table:
- `outcome`: Tracks whether auction was Won/Lost/Pending
- `final_price`: Stores the final winning bid amount

## Method 1: Using Railway CLI (Recommended)

1. **Install Railway CLI** (if not already installed):
   ```bash
   npm i -g @railway/cli
   railway login
   ```

2. **Connect to your Railway project**:
   ```bash
   railway link  # Select your project when prompted
   ```

3. **Run the Python migration script**:
   ```bash
   railway run python migrations/migrate_outcome_fields.py
   ```

   This will automatically use your Railway database connection.

## Method 2: Using Railway Dashboard (SQL Editor)

1. **Open Railway Dashboard**:
   - Go to [railway.app](https://railway.app)
   - Select your project
   - Click on your PostgreSQL database service

2. **Open Query Editor**:
   - Click on the "Query" or "Data" tab
   - Or use Railway's built-in SQL editor

3. **Run the SQL migration**:
   - Copy the contents of `add_outcome_fields.sql`
   - Paste into the SQL editor
   - Execute the query

   ```sql
   -- Add outcome column (nullable, defaults to 'Pending')
   ALTER TABLE auctions ADD COLUMN IF NOT EXISTS outcome VARCHAR(20) DEFAULT 'Pending';
   
   -- Add final_price column (nullable)
   ALTER TABLE auctions ADD COLUMN IF NOT EXISTS final_price NUMERIC(10, 2);
   
   -- Create index on outcome for faster queries
   CREATE INDEX IF NOT EXISTS idx_auctions_outcome ON auctions(outcome);
   
   -- Update existing records to have 'Pending' outcome if they don't have one
   UPDATE auctions SET outcome = 'Pending' WHERE outcome IS NULL;
   ```

## Method 3: Using psql Command Line

1. **Get your database connection string** from Railway:
   - Go to Railway Dashboard
   - Click on your PostgreSQL service
   - Go to "Connect" tab
   - Copy the connection string

2. **Connect using psql**:
   ```bash
   psql <your-railway-connection-string>
   ```

3. **Run the SQL commands** from `add_outcome_fields.sql`:
   ```sql
   ALTER TABLE auctions ADD COLUMN IF NOT EXISTS outcome VARCHAR(20) DEFAULT 'Pending';
   ALTER TABLE auctions ADD COLUMN IF NOT EXISTS final_price NUMERIC(10, 2);
   CREATE INDEX IF NOT EXISTS idx_auctions_outcome ON auctions(outcome);
   UPDATE auctions SET outcome = 'Pending' WHERE outcome IS NULL;
   ```

## Verifying the Migration

After running the migration, verify it worked:

**Using Railway CLI:**
```bash
railway run python -c "from database.session import SessionLocal; from database.models import Auction; db = SessionLocal(); result = db.execute('SELECT column_name FROM information_schema.columns WHERE table_name = \'auctions\' AND column_name IN (\'outcome\', \'final_price\')'); print(list(result)); db.close()"
```

**Or check in Railway Dashboard:**
- Go to PostgreSQL service → Query tab
- Run: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'auctions' AND column_name IN ('outcome', 'final_price');`

You should see both columns listed.

## Local Development

If you're using SQLite locally, the migration will run automatically when you restart the server (since SQLite tables are recreated). For PostgreSQL locally, run:

```bash
python migrations/migrate_outcome_fields.py
```

Make sure your `DATABASE_URL` environment variable is set correctly.

