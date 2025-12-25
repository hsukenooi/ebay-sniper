# Migration Status

## Local Database ✅

The index migration has been successfully run on the local database.

**Index created**: `idx_auctions_last_price_refresh_utc` on `auctions.last_price_refresh_utc`

## Railway Database ⏳

The migration needs to be run on Railway. See `RUN_MIGRATION_RAILWAY.md` for instructions.

### Quick Command (if Railway CLI is installed):

```bash
railway run python migrations/migrate_add_index_last_price_refresh.py
```

Or:

```bash
railway run psql \$DATABASE_URL -f migrations/add_index_last_price_refresh_utc.sql
```

## Migration Files

- `migrations/migrate_add_index_last_price_refresh.py` - Python migration script
- `migrations/add_index_last_price_refresh_utc.sql` - SQL migration file
- `migrations/RUN_MIGRATION_RAILWAY.md` - Railway migration instructions

