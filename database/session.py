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

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
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

