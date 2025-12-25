-- Migration: Add outcome and final_price fields to auctions table
-- Run this script on your Railway PostgreSQL database

-- Add outcome column (nullable, defaults to 'Pending')
ALTER TABLE auctions ADD COLUMN IF NOT EXISTS outcome VARCHAR(20) DEFAULT 'Pending';

-- Add final_price column (nullable)
ALTER TABLE auctions ADD COLUMN IF NOT EXISTS final_price NUMERIC(10, 2);

-- Create index on outcome for faster queries
CREATE INDEX IF NOT EXISTS idx_auctions_outcome ON auctions(outcome);

-- Update existing records to have 'Pending' outcome if they don't have one
UPDATE auctions SET outcome = 'Pending' WHERE outcome IS NULL;

