# Railway Migration Instructions

## ✅ Local Migration Complete

The index has been successfully added to your local database.

## Railway Migration

The migration needs to be run on Railway. Here are the recommended methods:

### Method 1: Railway Database Dashboard (Easiest)

1. Go to [Railway Dashboard](https://railway.app)
2. Select your project **creative-manifestation**
3. Click on your **PostgreSQL** service
4. Click on the **"Query"** or **"Connect"** tab (usually in the top menu)
5. Copy and paste this SQL:

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

6. Click **"Run"** or **"Execute"**

### Method 2: Railway CLI (If you have psycopg2 installed in Railway environment)

If your Railway service has psycopg2 installed, you can run:

```bash
railway run python migrations/migrate_add_index_last_price_refresh.py
```

However, if you get import errors, use Method 1 instead.

### Method 3: One-Liner SQL (Alternative)

If the DO block doesn't work in Railway's interface, try this simpler version:

```sql
CREATE INDEX IF NOT EXISTS idx_auctions_last_price_refresh_utc 
ON auctions(last_price_refresh_utc);
```

Note: `CREATE INDEX IF NOT EXISTS` is available in PostgreSQL 9.5+. Railway uses a recent version so this should work.

## Verify Migration

After running the migration, verify it was created by running this query in Railway's database dashboard:

```sql
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'auctions' 
AND indexname = 'idx_auctions_last_price_refresh_utc';
```

You should see one row with the index definition.

