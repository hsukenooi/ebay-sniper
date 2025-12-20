import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from freezegun import freeze_time

from database.models import AuctionStatus, BidResult, BidAttempt
from server.worker import Worker


def test_add_and_list_workflow(client, auth_headers, db_session):
    """Test the complete workflow of adding and listing snipers."""
    test_client = client
    
    # Add a sniper
    with patch("server.api.ebay_client.get_auction_details") as mock_get:
        mock_get.return_value = {
            "listing_url": "https://www.ebay.com/itm/111111111",
            "item_title": "Integration Test Item",
            "current_price": Decimal("50.00"),
            "currency": "USD",
            "auction_end_time_utc": datetime.utcnow() + timedelta(hours=2),
        }
        
        add_response = test_client.post(
            "/sniper/add",
            json={"listing_number": "111111111", "max_bid": 100.0},
            headers=auth_headers,
        )
        
        assert add_response.status_code == 200
        auction_id = add_response.json()["id"]
        
        # List snipers
        list_response = test_client.get("/sniper/list", headers=auth_headers)
        assert list_response.status_code == 200
        auctions = list_response.json()
        assert len(auctions) == 1
        assert auctions[0]["id"] == auction_id
        assert auctions[0]["listing_number"] == "111111111"


def test_add_cancel_workflow(client, auth_headers, db_session):
    """Test adding and cancelling a sniper."""
    test_client = client
    
    # Add a sniper
    with patch("server.api.ebay_client.get_auction_details") as mock_get:
        mock_get.return_value = {
            "listing_url": "https://www.ebay.com/itm/222222222",
            "item_title": "Cancellation Test Item",
            "current_price": Decimal("75.00"),
            "currency": "USD",
            "auction_end_time_utc": datetime.utcnow() + timedelta(hours=1),
        }
        
        add_response = test_client.post(
            "/sniper/add",
            json={"listing_number": "222222222", "max_bid": 120.0},
            headers=auth_headers,
        )
        
        auction_id = add_response.json()["id"]
        
        # Cancel the sniper
        cancel_response = test_client.delete(
            f"/sniper/{auction_id}",
            headers=auth_headers,
        )
        
        assert cancel_response.status_code == 200
        
        # Verify status changed
        status_response = test_client.get(
            f"/sniper/{auction_id}/status",
            headers=auth_headers,
        )
        assert status_response.json()["status"] == AuctionStatus.CANCELLED.value


def test_worker_pre_check_and_skip(db_session):
    """Integration test: Worker pre-check skips auction when price too high."""
    from database.models import Auction
    
    # Create auction with end time 65 seconds away
    now = datetime.utcnow()
    auction_end_time = now + timedelta(seconds=65)
    
    auction = Auction(
        listing_number="333333333",
        listing_url="https://www.ebay.com/itm/333333333",
        item_title="Skip Test Item",
        current_price=Decimal("80.00"),
        max_bid=Decimal("100.00"),
        currency="USD",
        auction_end_time_utc=auction_end_time,
        status=AuctionStatus.SCHEDULED.value,
    )
    db_session.add(auction)
    db_session.commit()
    
    worker = Worker()
    
    # Mock eBay to return price higher than max_bid
    with patch.object(worker.ebay_client, "get_auction_details") as mock_get:
        mock_get.return_value = {
            "current_price": Decimal("150.00"),  # Higher than max_bid
            "currency": "USD",
            "listing_url": auction.listing_url,
            "item_title": auction.item_title,
            "auction_end_time_utc": auction_end_time,
        }
        
        # Process auction at T-60s (should trigger pre-check)
        # Auction ends at now + 65s, so T-60s is at now + 5s
        # Worker checks if 0 <= time_until_pre_check < 1 (within 1 second before pre-check)
        # Pre-check time is at now + 5s, so freeze at now + 4.5s (0.5s before pre-check)
        frozen_time = now + timedelta(seconds=4.5)
        with freeze_time(frozen_time):
            db_session.refresh(auction)
            worker._process_auction(db_session, auction)
            db_session.commit()  # Commit the changes
    
    db_session.refresh(auction)
    assert auction.status == AuctionStatus.SKIPPED.value
    assert auction.skip_reason is not None


def test_worker_bid_execution_workflow(db_session):
    """Integration test: Worker executes bid successfully."""
    from database.models import Auction
    
    # Create auction with end time 5 seconds away
    now = datetime.utcnow()
    auction_end_time = now + timedelta(seconds=5)
    
    auction = Auction(
        listing_number="444444444",
        listing_url="https://www.ebay.com/itm/444444444",
        item_title="Bid Test Item",
        current_price=Decimal("90.00"),
        max_bid=Decimal("120.00"),
        currency="USD",
        auction_end_time_utc=auction_end_time,
        status=AuctionStatus.SCHEDULED.value,
    )
    db_session.add(auction)
    db_session.commit()
    
    worker = Worker()
    
    # Mock successful bid placement
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        # Process auction at bid execution time (T-3s = 2 seconds from now)
        # Worker checks if 0 <= time_until_bid < 1 (within 1 second before bid time)
        # Bid time is at now + 2s, so freeze at now + 1.5s (0.5s before bid time)
        frozen_time = now + timedelta(seconds=1.5)
        with freeze_time(frozen_time):
            db_session.refresh(auction)
            worker._process_auction(db_session, auction)
            db_session.commit()  # Commit the changes
    
    db_session.refresh(auction)
    assert auction.status == AuctionStatus.BID_PLACED.value
    
    # Verify bid attempt was created
    bid_attempt = db_session.query(BidAttempt).filter_by(auction_id=auction.id).first()
    assert bid_attempt is not None
    assert bid_attempt.result == BidResult.SUCCESS.value


def test_price_refresh_on_list(client, auth_headers, db_session):
    """Integration test: Price refreshes when listing if cache expired."""
    from database.models import Auction
    test_client = client
    
    # Create auction with old price refresh time
    auction = Auction(
        listing_number="555555555",
        listing_url="https://www.ebay.com/itm/555555555",
        item_title="Price Refresh Test",
        current_price=Decimal("100.00"),
        max_bid=Decimal("150.00"),
        currency="USD",
        auction_end_time_utc=datetime.utcnow() + timedelta(hours=1),
        last_price_refresh_utc=datetime.utcnow() - timedelta(seconds=70),  # Older than 60s
        status=AuctionStatus.SCHEDULED.value,
    )
    db_session.add(auction)
    db_session.commit()
    
    # Mock price refresh
    with patch("server.api.ebay_client.get_auction_details") as mock_get:
        mock_get.return_value = {
            "listing_url": auction.listing_url,
            "item_title": auction.item_title,
            "current_price": Decimal("110.00"),  # New price
            "currency": "USD",
            "auction_end_time_utc": auction.auction_end_time_utc,
        }
        
        # List should trigger price refresh
        list_response = test_client.get("/sniper/list", headers=auth_headers)
        assert list_response.status_code == 200
        
        # Verify price was updated
        db_session.refresh(auction)
        assert auction.current_price == Decimal("110.00")
        assert auction.last_price_refresh_utc is not None


def test_idempotent_bid_execution(db_session):
    """Integration test: Only one bid attempt per auction (idempotency)."""
    from database.models import Auction
    
    auction = Auction(
        listing_number="666666666",
        listing_url="https://www.ebay.com/itm/666666666",
        item_title="Idempotency Test",
        current_price=Decimal("50.00"),
        max_bid=Decimal("100.00"),
        currency="USD",
        auction_end_time_utc=datetime.utcnow() + timedelta(seconds=5),
        status=AuctionStatus.SCHEDULED.value,
    )
    db_session.add(auction)
    db_session.commit()
    
    worker = Worker()
    
    with patch.object(worker.ebay_client, "place_bid") as mock_bid:
        mock_bid.return_value = {"success": True}
        
        # First execution should succeed
        result1 = worker._execute_bid(db_session, auction)
        assert result1 is True
        
        # Verify only one bid attempt exists
        attempts = db_session.query(BidAttempt).filter_by(auction_id=auction.id).all()
        assert len(attempts) == 1
        
        # Try to execute again (should fail due to idempotency check)
        # The auction status is now BidPlaced, so the atomic update will find 0 rows
        # Create a new auction object pointing to the same record
        db_session.refresh(auction)
        # The status in DB is BidPlaced, so atomic update in _execute_bid will find 0 rows
        # and return False immediately
        result2 = worker._execute_bid(db_session, auction)
        assert result2 is False  # Atomic update finds 0 rows (status is BidPlaced, not Scheduled)
        
        # Verify still only one bid attempt exists
        attempts = db_session.query(BidAttempt).filter_by(auction_id=auction.id).all()
        assert len(attempts) == 1

