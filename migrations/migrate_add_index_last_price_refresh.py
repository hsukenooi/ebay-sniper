#!/usr/bin/env python3
"""
Migration script to add index on last_price_refresh_utc column.

Usage:
    python migrations/migrate_add_index_last_price_refresh.py

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
    """Add index on last_price_refresh_utc column to auctions table."""
    print("Starting migration: Adding index on last_price_refresh_utc...")
    
    # PostgreSQL-specific migration SQL
    migration_sql = """
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
        END IF;
    END $$;
    """
    
    db = SessionLocal()
    try:
        # Execute migration
        db.execute(text(migration_sql))
        db.commit()
        print("✅ Migration completed successfully!")
        print("   - Added index 'idx_auctions_last_price_refresh_utc' on auctions.last_price_refresh_utc")
        
        # Verify the index was created
        verify_sql = """
        SELECT indexname FROM pg_indexes 
        WHERE tablename = 'auctions' 
        AND indexname = 'idx_auctions_last_price_refresh_utc'
        """
        result = db.execute(text(verify_sql))
        if result.fetchone():
            print("   ✓ Index verified and exists")
        else:
            print("   ⚠️  Warning: Index verification failed (but migration completed)")
            
    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

