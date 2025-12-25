# Running Migration on Railway

## Method 1: Using Railway CLI (Recommended)

1. **Install Railway CLI** (if not already installed):
   ```bash
   npm i -g @railway/cli
   ```

2. **Login to Railway**:
   ```bash
   railway login
   ```

3. **Link to your project**:
   ```bash
   railway link
   ```
   Select your project (creative-manifestation) when prompted.

4. **Run the migration script**:
   ```bash
   railway run python migrations/migrate_add_index_last_price_refresh.py
   ```

   OR run the SQL file directly:
   ```bash
   railway run psql $DATABASE_URL -f migrations/add_index_last_price_refresh_utc.sql
   ```

## Method 2: Using Railway Dashboard

1. **Get DATABASE_URL from Railway**:
   - Go to Railway dashboard
   - Select your project → PostgreSQL service
   - Copy the `DATABASE_URL` connection string

2. **Run migration locally with Railway DATABASE_URL**:
   ```bash
   # Set DATABASE_URL to Railway's connection string
   export DATABASE_URL="postgresql://postgres:password@hostname:port/railway"
   
   # Run migration
   python migrations/migrate_add_index_last_price_refresh.py
   ```

   OR use psql directly:
   ```bash
   psql $DATABASE_URL -f migrations/add_index_last_price_refresh_utc.sql
   ```

## Method 3: Using Railway Database Dashboard

1. **Open Railway Database Dashboard**:
   - Go to Railway dashboard
   - Select your project → PostgreSQL service
   - Click on "Query" or "Connect" tab

2. **Run the SQL**:
   Copy and paste the contents of `migrations/add_index_last_price_refresh_utc.sql`:
   ```sql
   DO $$ 
   BEGIN
       IF NOT EXISTS (
           SELECT 1 FROM pg_indexes 
           WHERE tablename = 'auctions' 
           AND indexname = 'idx_auctions_last_price_refresh_utc'
       ) THEN
           CREATE INDEX idx_auctions_last_price_refresh_utc 
           ON auctions(last_price_refresh_utc);
           RAISE NOTICE 'Index idx_auctions_last_price_refresh_utc created successfully';
       ELSE
           RAISE NOTICE 'Index idx_auctions_last_price_refresh_utc already exists';
       END IF;
   END $$;
   ```

## Verify Migration

After running the migration, verify it was created:

```sql
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'auctions' 
AND indexname = 'idx_auctions_last_price_refresh_utc';
```

You should see the index listed.

