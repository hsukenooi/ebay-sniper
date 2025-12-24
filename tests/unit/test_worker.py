import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal
from freezegun import freeze_time

from server.worker import Worker, BID_OFFSET_SECONDS, PRE_BID_CHECK_SECONDS
from database.models import AuctionStatus, BidResult, BidAttempt


def test_pre_bid_price_check_skip(db_session, sample_auction):
    """Test pre-bid price check when price exceeds max bid."""
    worker = Worker()
    
    # Mock eBay client to return price higher than max_bid
    with patch.object(worker.ebay_client, "get_auction_details") as mock_get:
        mock_get.return_value = {
            "current_price": Decimal("200.00"),  # Higher than max_bid (150.00)
            "currency": "USD",
            "listing_url": sample_auction.listing_url,
            "item_title": sample_auction.item_title,
            "auction_end_time_utc": sample_auction.auction_end_time_utc,
        }
        
        result = worker._pre_bid_price_check(db_session, sample_auction)
        
        assert result is False
        db_session.refresh(sample_auction)
        assert sample_auction.status == AuctionStatus.SKIPPED.value
        assert sample_auction.skip_reason is not None


def test_pre_bid_price_check_proceed(db_session, sample_auction):
    """Test pre-bid price check when price is within max bid."""
    worker = Worker()
    
    # Mock eBay client to return price lower than max_bid
    with patch.object(worker.ebay_client, "get_auction_details") as mock_get:
        mock_get.return_value = {
            "current_price": Decimal("100.00"),  # Lower than max_bid (150.00)
            "currency": "USD",
            "listing_url": sample_auction.listing_url,
            "item_title": sample_auction.item_title,
            "auction_end_time_utc": sample_auction.auction_end_time_utc,
        }
        
        result = worker._pre_bid_price_check(db_session, sample_auction)
        
        assert result is True
        db_session.refresh(sample_auction)
        assert sample_auction.status != AuctionStatus.SKIPPED.value


def test_pre_bid_price_check_error_continues(db_session, sample_auction):
    """Test pre-bid price check continues on error."""
    worker = Worker()
    
    # Mock eBay client to raise error
    with patch.object(worker.ebay_client, "get_auction_details") as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        result = worker._pre_bid_price_check(db_session, sample_auction)
        
        # Should continue (return True) on error
        assert result is True


def test_execute_bid_idempotency(db_session, sample_auction):
    """Test bid execution idempotency - only one execution succeeds."""
    worker = Worker()
    
    # First execution should succeed
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        result1 = worker._execute_bid(db_session, sample_auction)
        assert result1 is True
        
        # Verify status changed
        db_session.refresh(sample_auction)
        assert sample_auction.status == AuctionStatus.BID_PLACED.value
        
        # Second execution should fail (idempotency) - atomic update returns 0 rows
        # The atomic update checks for Scheduled status, but status is now BidPlaced
        # So the update will affect 0 rows and return False
        from database.models import Auction as AuctionModel
        new_auction = db_session.query(AuctionModel).filter_by(id=sample_auction.id).first()
        # The status in DB is BidPlaced, so atomic update will find 0 rows
        result2 = worker._execute_bid(db_session, new_auction)
        # Should return False because atomic update finds 0 rows (status is BidPlaced, not Scheduled)
        assert result2 is False


def test_execute_bid_success(db_session, sample_auction):
    """Test successful bid execution."""
    worker = Worker()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        result = worker._execute_bid(db_session, sample_auction)
        
        assert result is True
        db_session.refresh(sample_auction)
        assert sample_auction.status == AuctionStatus.BID_PLACED.value
        
        # Check bid attempt was created
        bid_attempt = db_session.query(BidAttempt).filter_by(auction_id=sample_auction.id).first()
        assert bid_attempt is not None
        assert bid_attempt.result == BidResult.SUCCESS.value


def test_execute_bid_failure(db_session, sample_auction):
    """Test bid execution failure."""
    worker = Worker()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        import requests
        mock_bid.side_effect = requests.exceptions.RequestException("Bid failed")
        
        result = worker._execute_bid(db_session, sample_auction)
        
        assert result is False
        db_session.refresh(sample_auction)
        assert sample_auction.status == AuctionStatus.FAILED.value
        
        # Check bid attempt was created with failure
        bid_attempt = db_session.query(BidAttempt).filter_by(auction_id=sample_auction.id).first()
        assert bid_attempt is not None
        assert bid_attempt.result == BidResult.FAILED.value


def test_execute_bid_timeout_retry(db_session, sample_auction):
    """Test bid execution retries on timeout."""
    worker = Worker()
    
    import requests
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        # First call times out, second succeeds
        mock_bid.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            {"success": True},
        ]
        
        result = worker._execute_bid(db_session, sample_auction)
        
        # Should succeed after retry
        assert result is True
        assert mock_bid.call_count == 2


def test_execute_bid_auction_ended(db_session, sample_auction):
    """Test bid execution fails if auction has ended."""
    worker = Worker()
    
    # Set auction end time in the past
    sample_auction.auction_end_time_utc = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    
    result = worker._execute_bid(db_session, sample_auction)
    
    assert result is False
    db_session.refresh(sample_auction)
    assert sample_auction.status == AuctionStatus.FAILED.value


@freeze_time("2025-01-19 12:00:00")
def test_process_auction_terminal_state(db_session, sample_auction):
    """Test processing auction in terminal state (should skip)."""
    worker = Worker()
    
    # Set to terminal state
    sample_auction.status = AuctionStatus.BID_PLACED.value
    db_session.commit()
    
    # Should not process
    worker._process_auction(db_session, sample_auction)
    
    db_session.refresh(sample_auction)
    assert sample_auction.status == AuctionStatus.BID_PLACED.value


@freeze_time("2025-01-19 12:00:00")
def test_process_auction_pre_check_time(db_session, sample_auction):
    """Test processing auction at pre-check time (T-60s)."""
    worker = Worker()
    
    # Set auction end time to 60 seconds from now
    sample_auction.auction_end_time_utc = datetime.utcnow() + timedelta(seconds=60)
    db_session.commit()
    
    with patch.object(worker, "_pre_bid_price_check") as mock_check:
        mock_check.return_value = True
        worker._process_auction(db_session, sample_auction)
        
        # Should call pre-check
        mock_check.assert_called_once()


@freeze_time("2025-01-19 12:00:00")
def test_process_auction_bid_execution_time(db_session, sample_auction):
    """Test processing auction at bid execution time (T-3s)."""
    worker = Worker()
    
    # Set auction end time to 3 seconds from now
    sample_auction.auction_end_time_utc = datetime.utcnow() + timedelta(seconds=3)
    db_session.commit()
    
    with patch.object(worker, "_execute_bid") as mock_execute:
        mock_execute.return_value = True
        worker._process_auction(db_session, sample_auction)
        
        # Should call execute
        mock_execute.assert_called_once()


def test_execute_bid_uses_max_bid(db_session, sample_auction):
    """Test that bid execution uses max_bid directly (eBay proxy bidding)."""
    worker = Worker()
    
    # Set current price to $5.00, max_bid to $10.00
    sample_auction.current_price = Decimal("5.00")
    sample_auction.max_bid = Decimal("10.00")
    db_session.commit()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        result = worker._execute_bid(db_session, sample_auction)
        
        assert result is True
        # Verify bid was placed with max_bid directly
        # eBay's proxy bidding will automatically bid incrementally up to this amount
        mock_bid.assert_called_once()
        call_args = mock_bid.call_args
        bid_amount = call_args[0][1]  # Second argument is bid_amount
        assert bid_amount == Decimal("10.00")  # Should use max_bid directly


def test_execute_bid_uses_max_bid_directly(db_session, sample_auction):
    """Test that bid uses max_bid directly regardless of current price."""
    worker = Worker()
    
    # Set current price to $4.00, max_bid to $4.99
    sample_auction.current_price = Decimal("4.00")
    sample_auction.max_bid = Decimal("4.99")
    db_session.commit()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        result = worker._execute_bid(db_session, sample_auction)
        
        assert result is True
        # Verify bid uses max_bid directly (eBay proxy bidding handles increments)
        call_args = mock_bid.call_args
        bid_amount = call_args[0][1]
        assert bid_amount == Decimal("4.99")  # Should use max_bid directly


def test_execute_bid_high_price_uses_max_bid(db_session, sample_auction):
    """Test that high price bids use max_bid directly."""
    worker = Worker()
    
    # Set current price to $250.00, max_bid to $300.00
    sample_auction.current_price = Decimal("250.00")
    sample_auction.max_bid = Decimal("300.00")
    db_session.commit()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        result = worker._execute_bid(db_session, sample_auction)
        
        assert result is True
        # Verify bid uses max_bid directly (eBay proxy bidding handles increments)
        call_args = mock_bid.call_args
        bid_amount = call_args[0][1]
        assert bid_amount == Decimal("300.00")  # Should use max_bid directly


def test_execute_bid_low_price_uses_max_bid(db_session, sample_auction):
    """Test that low price bids use max_bid directly."""
    worker = Worker()
    
    # Set current price to $0.50, max_bid to $1.00
    sample_auction.current_price = Decimal("0.50")
    sample_auction.max_bid = Decimal("1.00")
    db_session.commit()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        result = worker._execute_bid(db_session, sample_auction)
        
        assert result is True
        # Verify bid uses max_bid directly (eBay proxy bidding handles increments)
        call_args = mock_bid.call_args
        bid_amount = call_args[0][1]
        assert bid_amount == Decimal("1.00")  # Should use max_bid directly

