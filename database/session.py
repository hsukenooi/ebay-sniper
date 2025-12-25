from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
import os

# Default to PostgreSQL for local development
# Format: postgresql://username:password@host:port/database
# On macOS Homebrew, PostgreSQL uses your macOS username (no password by default)
# You can override this by setting DATABASE_URL environment variable
import getpass
_default_user = getpass.getuser()  # Get current macOS username
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    f"postgresql://{_default_user}@localhost:5432/ebay_sniper"
)

# Configure connection pool for PostgreSQL
# pool_size: number of connections to maintain persistently
# max_overflow: additional connections that can be created on demand
# pool_pre_ping: verify connections are alive before using them (helps with connection drops)
# pool_recycle: recycle connections after this many seconds (helps with stale connections)
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,           # Number of connections to keep in pool
        max_overflow=10,       # Additional connections allowed beyond pool_size
        pool_pre_ping=True,    # Verify connections before using (helps with connection drops)
        pool_recycle=3600,     # Recycle connections after 1 hour (prevents stale connections)
        echo=False             # Set to True for SQL query logging
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database schema."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

