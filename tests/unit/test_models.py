import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from database.models import Auction, BidAttempt, AuctionStatus, BidResult


def test_auction_creation(db_session):
    """Test creating an auction."""
    auction = Auction(
        listing_number="123456789",
        listing_url="https://www.ebay.com/itm/123456789",
        item_title="Test Item",
        current_price=Decimal("100.00"),
        max_bid=Decimal("150.00"),
        currency="USD",
        auction_end_time_utc=datetime.utcnow() + timedelta(hours=1),
        status=AuctionStatus.SCHEDULED.value,
    )
    db_session.add(auction)
    db_session.commit()
    
    assert auction.id is not None
    assert auction.listing_number == "123456789"
    assert auction.status == AuctionStatus.SCHEDULED.value
    assert auction.max_bid == Decimal("150.00")


def test_bid_attempt_creation(db_session, sample_auction):
    """Test creating a bid attempt."""
    bid_attempt = BidAttempt(
        auction_id=sample_auction.id,
        attempt_time_utc=datetime.utcnow(),
        result=BidResult.SUCCESS.value,
    )
    db_session.add(bid_attempt)
    db_session.commit()
    
    assert bid_attempt.auction_id == sample_auction.id
    assert bid_attempt.result == BidResult.SUCCESS.value


def test_auction_bid_attempt_relationship(db_session, sample_auction):
    """Test the relationship between Auction and BidAttempt."""
    bid_attempt = BidAttempt(
        auction_id=sample_auction.id,
        attempt_time_utc=datetime.utcnow(),
        result=BidResult.SUCCESS.value,
    )
    db_session.add(bid_attempt)
    db_session.commit()
    
    # Test relationship
    assert sample_auction.bid_attempt is not None
    assert sample_auction.bid_attempt.auction_id == sample_auction.id
    assert bid_attempt.auction.id == sample_auction.id


def test_auction_status_enum():
    """Test auction status enum values."""
    assert AuctionStatus.SCHEDULED.value == "Scheduled"
    assert AuctionStatus.EXECUTING.value == "Executing"
    assert AuctionStatus.BID_PLACED.value == "BidPlaced"
    assert AuctionStatus.FAILED.value == "Failed"
    assert AuctionStatus.CANCELLED.value == "Cancelled"
    assert AuctionStatus.SKIPPED.value == "Skipped"


def test_bid_result_enum():
    """Test bid result enum values."""
    assert BidResult.SUCCESS.value == "success"
    assert BidResult.FAILED.value == "failed"

