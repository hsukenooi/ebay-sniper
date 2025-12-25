#!/usr/bin/env python3
"""
Migration script to add seller_name column to auctions table.
Run this script after deploying the code changes.
"""
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.session import engine
from sqlalchemy import text

load_dotenv()


def migrate():
    """Add seller_name column to auctions table."""
    print("Starting migration: add seller_name column...")
    
    migration_sql = """
    ALTER TABLE auctions ADD COLUMN IF NOT EXISTS seller_name VARCHAR;
    """
    
    try:
        with engine.connect() as conn:
            # Check if column already exists (PostgreSQL specific)
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='auctions' AND column_name='seller_name'
            """))
            
            if result.fetchone():
                print("✓ Column 'seller_name' already exists, skipping migration")
                return
            
            # Add the column
            conn.execute(text(migration_sql))
            conn.commit()
            print("✓ Successfully added seller_name column to auctions table")
            
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate()

