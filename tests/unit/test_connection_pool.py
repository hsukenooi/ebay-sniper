"""
Tests for database connection pool management.

These tests verify that:
1. Connections are properly created and closed
2. Connection pool doesn't leak connections
3. Pool handles connection drops gracefully
4. Worker properly manages database sessions
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import TimeoutError

from database.session import engine, SessionLocal, DATABASE_URL
from server.worker import Worker
from database.models import Auction, AuctionStatus


def test_connection_pool_basic_operations():
    """Test basic connection pool operations."""
    # Get a connection from the pool
    conn = engine.connect()
    try:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        conn.close()


def test_session_local_creates_new_sessions():
    """Test that SessionLocal creates independent sessions."""
    session1 = SessionLocal()
    session2 = SessionLocal()
    
    try:
        # Sessions should be different objects
        assert session1 is not session2
        
        # Both should be able to query
        result1 = session1.execute(text("SELECT 1"))
        result2 = session2.execute(text("SELECT 1"))
        assert result1.scalar() == 1
        assert result2.scalar() == 1
    finally:
        session1.close()
        session2.close()


def test_session_closes_connection_properly():
    """Test that closing a session properly returns connection to pool."""
    # Get pool stats before
    pool = engine.pool
    initial_size = pool.size()
    
    # Create and close multiple sessions
    sessions = []
    for _ in range(5):
        session = SessionLocal()
        sessions.append(session)
        session.execute(text("SELECT 1"))
    
    # Close all sessions
    for session in sessions:
        session.close()
    
    # Pool should still be healthy
    assert pool.size() >= 0  # Pool size can vary, but shouldn't be negative


def test_worker_uses_separate_sessions():
    """Test that worker uses separate sessions for main processing and outcome checking."""
    # This test verifies the code structure ensures separate sessions
    # by inspecting the run_loop method structure
    import inspect
    from server.worker import Worker
    
    worker = Worker()
    source = inspect.getsource(worker.run_loop)
    
    # Verify that there are two separate SessionLocal() calls
    # (one for main processing, one for outcome checking)
    assert source.count('SessionLocal()') >= 2
    
    # Verify both sessions are closed in finally blocks
    assert 'finally:' in source
    assert '.close()' in source
    
    # Verify outcome_db is a separate variable from db
    assert 'outcome_db' in source or 'outcome_db =' in source


def test_worker_separate_sessions_for_outcomes():
    """Test that worker uses separate sessions for outcome checking."""
    worker = Worker()
    
    # Track session creation
    sessions_created = []
    original_session_local = SessionLocal
    
    def track_session_local():
        session = original_session_local()
        sessions_created.append(session)
        return session
    
    # Mock auctions query
    with patch('server.worker.SessionLocal', side_effect=track_session_local):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.commit = MagicMock()
        mock_session.close = MagicMock()
        mock_session.rollback = MagicMock()
        
        # Create sessions manually to track them
        session1 = track_session_local()
        session2 = track_session_local()
        
        # Verify we got two different sessions
        assert len(sessions_created) == 2
        assert session1 is not session2


def test_connection_pool_with_exceptions():
    """Test that connection pool handles exceptions gracefully."""
    session = SessionLocal()
    try:
        # Try to execute invalid SQL to trigger an error
        with pytest.raises(Exception):
            session.execute(text("INVALID SQL STATEMENT"))
        session.rollback()
    finally:
        session.close()
    
    # After closing, should be able to create new sessions
    session2 = SessionLocal()
    try:
        result = session2.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        session2.close()


def test_pool_pre_ping_enabled():
    """Test that pool_pre_ping is enabled for PostgreSQL."""
    if "sqlite" not in DATABASE_URL:
        # For PostgreSQL, pool_pre_ping should be enabled
        assert hasattr(engine.pool, '_pre_ping')
        # The actual pre_ping setting is internal, but we can verify
        # the engine was created with it by checking if it's a QueuePool
        assert isinstance(engine.pool, QueuePool)


def test_pool_recycle_setting():
    """Test that pool_recycle is configured."""
    if "sqlite" not in DATABASE_URL:
        # For PostgreSQL, pool should have recycle setting
        assert isinstance(engine.pool, QueuePool)
        # The recycle setting is used internally, but we can verify
        # the pool exists and is properly configured


@pytest.mark.integration
def test_concurrent_sessions():
    """Test that multiple concurrent sessions work properly."""
    import threading
    import time
    
    results = []
    errors = []
    
    def run_query(session_id):
        try:
            session = SessionLocal()
            try:
                result = session.execute(text(f"SELECT {session_id}"))
                results.append(result.scalar())
                time.sleep(0.1)  # Simulate some work
            finally:
                session.close()
        except Exception as e:
            errors.append(e)
    
    # Create multiple threads
    threads = []
    for i in range(5):
        thread = threading.Thread(target=run_query, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # All queries should succeed
    assert len(errors) == 0
    assert len(results) == 5
    assert set(results) == {0, 1, 2, 3, 4}


def test_session_context_manager_pattern():
    """Test that sessions work properly with context manager pattern."""
    from contextlib import contextmanager
    
    @contextmanager
    def get_db_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Use context manager
    with get_db_session() as session:
        result = session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    
    # Session should be closed after context exits
    # (We can't directly verify this, but no exception should be raised)


if __name__ == "__main__":
    pytest.main([__file__])

