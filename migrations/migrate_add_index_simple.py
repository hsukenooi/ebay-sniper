#!/usr/bin/env python3
"""
Simple migration script to add index on last_price_refresh_utc column.
Uses psycopg2 directly to avoid SQLAlchemy dependency issues.

Usage:
    python migrations/migrate_add_index_simple.py

This script can be run locally or on Railway.
Make sure DATABASE_URL environment variable is set.
"""
import os
import sys
import urllib.parse

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)


def parse_database_url(url):
    """Parse PostgreSQL connection URL into components."""
    parsed = urllib.parse.urlparse(url)
    return {
        'dbname': parsed.path[1:],  # Remove leading '/'
        'user': parsed.username,
        'password': parsed.password,
        'host': parsed.hostname,
        'port': parsed.port or 5432
    }


def migrate():
    """Add index on last_price_refresh_utc column to auctions table."""
    print("Starting migration: Adding index on last_price_refresh_utc...")
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        sys.exit(1)
    
    try:
        # Parse connection URL
        conn_params = parse_database_url(database_url)
        
        # Connect to database
        conn = psycopg2.connect(**conn_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if index exists
        cur.execute("""
            SELECT 1 FROM pg_indexes 
            WHERE tablename = 'auctions' 
            AND indexname = 'idx_auctions_last_price_refresh_utc'
        """)
        
        if cur.fetchone():
            print("✓ Index 'idx_auctions_last_price_refresh_utc' already exists")
        else:
            # Create index
            cur.execute("""
                CREATE INDEX idx_auctions_last_price_refresh_utc 
                ON auctions(last_price_refresh_utc)
            """)
            print("✅ Migration completed successfully!")
            print("   - Created index 'idx_auctions_last_price_refresh_utc' on auctions.last_price_refresh_utc")
            
            # Verify
            cur.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'auctions' 
                AND indexname = 'idx_auctions_last_price_refresh_utc'
            """)
            if cur.fetchone():
                print("   ✓ Index verified and exists")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate()

