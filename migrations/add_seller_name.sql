-- Migration: Add seller_name column to auctions table
-- Date: 2025-01-XX
-- Description: Adds seller_name column to store the eBay seller's username or userId

ALTER TABLE auctions ADD COLUMN IF NOT EXISTS seller_name VARCHAR;

-- The column is nullable to handle existing rows and cases where seller info might not be available

