-- Migration: Add index on last_price_refresh_utc column
-- This improves query performance when checking if auction prices need refreshing

-- Add index on last_price_refresh_utc if it doesn't exist
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

