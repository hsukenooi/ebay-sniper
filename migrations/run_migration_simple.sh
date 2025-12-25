#!/bin/bash
# Simple migration script to add index - can be run via Railway CLI
# Usage: railway run bash migrations/run_migration_simple.sh

psql "$DATABASE_URL" <<EOF
CREATE INDEX IF NOT EXISTS idx_auctions_last_price_refresh_utc 
ON auctions(last_price_refresh_utc);
EOF

echo "Migration complete. Verifying index..."
psql "$DATABASE_URL" -c "SELECT indexname FROM pg_indexes WHERE tablename = 'auctions' AND indexname = 'idx_auctions_last_price_refresh_utc';"

