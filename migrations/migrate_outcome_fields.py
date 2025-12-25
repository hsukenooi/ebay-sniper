#!/usr/bin/env python3
"""
Migration script to add outcome and final_price fields to auctions table.

Usage:
    python migrations/migrate_outcome_fields.py

This script can be run locally (against local database) or on Railway.
Make sure DATABASE_URL environment variable is set.
"""

import os
import sys
from sqlalchemy import text
from database.session import engine, SessionLocal

def migrate():
    """Add outcome and final_price columns to auctions table."""
    print("Starting migration: Adding outcome and final_price fields...")
    
    migration_sql = """
    -- Add outcome column if it doesn't exist
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'auctions' AND column_name = 'outcome'
        ) THEN
            ALTER TABLE auctions ADD COLUMN outcome VARCHAR(20) DEFAULT 'Pending';
        END IF;
    END $$;
    
    -- Add final_price column if it doesn't exist
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'auctions' AND column_name = 'final_price'
        ) THEN
            ALTER TABLE auctions ADD COLUMN final_price NUMERIC(10, 2);
        END IF;
    END $$;
    
    -- Create index on outcome if it doesn't exist
    CREATE INDEX IF NOT EXISTS idx_auctions_outcome ON auctions(outcome);
    
    -- Update existing records to have 'Pending' outcome if NULL
    UPDATE auctions SET outcome = 'Pending' WHERE outcome IS NULL;
    """
    
    db = SessionLocal()
    try:
        # Execute migration
        db.execute(text(migration_sql))
        db.commit()
        print("✅ Migration completed successfully!")
        print("   - Added 'outcome' column (defaults to 'Pending')")
        print("   - Added 'final_price' column")
        print("   - Created index on 'outcome'")
        print("   - Updated existing records with 'Pending' outcome")
    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    migrate()

