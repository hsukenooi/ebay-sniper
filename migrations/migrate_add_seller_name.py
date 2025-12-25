#!/usr/bin/env python3
"""
Migration script to add seller_name column to auctions table.

Usage:
    python migrations/migrate_add_seller_name.py

This script can be run locally (against local database) or on Railway.
Make sure DATABASE_URL environment variable is set.
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.session import SessionLocal


def migrate():
    """Add seller_name column to auctions table."""
    print("Starting migration: Adding seller_name field...")
    
    migration_sql = """
    -- Add seller_name column if it doesn't exist
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'auctions' AND column_name = 'seller_name'
        ) THEN
            ALTER TABLE auctions ADD COLUMN seller_name VARCHAR;
        END IF;
    END $$;
    """
    
    db = SessionLocal()
    try:
        # Execute migration
        db.execute(text(migration_sql))
        db.commit()
        print("✅ Migration completed successfully!")
        print("   - Added 'seller_name' column to auctions table")
    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

