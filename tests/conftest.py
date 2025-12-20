import pytest
import os
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Auction, BidAttempt, AuctionStatus, BidResult
import jwt

# Use file-based SQLite for testing (more reliable than :memory:)
import tempfile
import atexit
import os as os_module

# Create a temporary database file
_test_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
_test_db_file.close()
TEST_DATABASE_URL = f"sqlite:///{_test_db_file.name}"

# Clean up temp file on exit
def _cleanup_test_db():
    try:
        if os_module.path.exists(_test_db_file.name):
            os_module.unlink(_test_db_file.name)
    except:
        pass

atexit.register(_cleanup_test_db)

# Set test secret key before any imports
os.environ["SECRET_KEY"] = "test-secret-key"


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine."""
    # Use a unique database file per test to avoid conflicts
    import tempfile
    import os as os_module
    test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    test_db.close()
    test_db_url = f"sqlite:///{test_db.name}"
    
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os_module.unlink(test_db.name)
    except:
        pass


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a test database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture(scope="function")
def override_get_db(db_engine, db_session):
    """Override get_db dependency for FastAPI tests."""
    # Ensure tables are created on the engine
    from database.models import Base
    Base.metadata.create_all(bind=db_engine)
    
    import os
    os.environ["SECRET_KEY"] = "test-secret-key"
    from server.api import app
    from database.session import get_db
    
    def _get_test_db():
        try:
            yield db_session
        finally:
            pass
    
    # Clear any existing overrides first
    if hasattr(app, "dependency_overrides"):
        app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def sample_auction(db_session):
    """Create a sample auction for testing."""
    auction = Auction(
        listing_number="123456789",
        listing_url="https://www.ebay.com/itm/123456789",
        item_title="Test Item",
        current_price=Decimal("100.00"),
        max_bid=Decimal("150.00"),
        currency="USD",
        auction_end_time_utc=datetime.utcnow() + timedelta(hours=1),
        last_price_refresh_utc=datetime.utcnow(),
        status=AuctionStatus.SCHEDULED.value,
    )
    db_session.add(auction)
    db_session.commit()
    db_session.refresh(auction)
    return auction


@pytest.fixture
def auth_token():
    """Generate a test JWT token."""
    secret_key = os.getenv("SECRET_KEY", "test-secret-key")
    payload = {"sub": "testuser", "exp": datetime.utcnow() + timedelta(days=30)}
    return jwt.encode(payload, secret_key, algorithm="HS256")


@pytest.fixture
def auth_headers(auth_token):
    """Get authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def client(override_get_db):
    """Create a test client with database override."""
    from fastapi.testclient import TestClient
    from server.api import app
    return TestClient(app)
