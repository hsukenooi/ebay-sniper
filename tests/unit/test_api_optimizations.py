"""Tests for API optimizations: caching, coalescing, and terminal state skipping."""
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
import pytest
from server.api import _should_refresh_price
from database.models import Auction, AuctionStatus


def test_should_refresh_price_skips_terminal_states():
    """Test that terminal state auctions don't trigger refresh."""
    now = datetime.utcnow()
    
    # Cancelled auction - should not refresh
    auction_cancelled = Mock(spec=Auction)
    auction_cancelled.status = AuctionStatus.CANCELLED.value
    auction_cancelled.last_price_refresh_utc = now - timedelta(seconds=120)  # Stale
    assert _should_refresh_price(auction_cancelled) == False
    
    # Failed auction - should not refresh
    auction_failed = Mock(spec=Auction)
    auction_failed.status = AuctionStatus.FAILED.value
    auction_failed.last_price_refresh_utc = now - timedelta(seconds=120)
    assert _should_refresh_price(auction_failed) == False
    
    # Skipped auction - should not refresh
    auction_skipped = Mock(spec=Auction)
    auction_skipped.status = AuctionStatus.SKIPPED.value
    auction_skipped.last_price_refresh_utc = now - timedelta(seconds=120)
    assert _should_refresh_price(auction_skipped) == False
    
    # BidPlaced but ended - should not refresh
    auction_bid_placed_ended = Mock(spec=Auction)
    auction_bid_placed_ended.status = AuctionStatus.BID_PLACED.value
    auction_bid_placed_ended.auction_end_time_utc = now - timedelta(seconds=60)
    auction_bid_placed_ended.last_price_refresh_utc = now - timedelta(seconds=120)
    assert _should_refresh_price(auction_bid_placed_ended) == False


def test_should_refresh_price_allows_active_states():
    """Test that active auctions can be refreshed if stale."""
    now = datetime.utcnow()
    
    # Scheduled auction with stale cache - should refresh
    auction_scheduled_stale = Mock(spec=Auction)
    auction_scheduled_stale.status = AuctionStatus.SCHEDULED.value
    auction_scheduled_stale.last_price_refresh_utc = now - timedelta(seconds=120)  # Stale (>60s)
    auction_scheduled_stale.auction_end_time_utc = now + timedelta(hours=1)
    assert _should_refresh_price(auction_scheduled_stale) == True
    
    # Scheduled auction with fresh cache - should not refresh
    auction_scheduled_fresh = Mock(spec=Auction)
    auction_scheduled_fresh.status = AuctionStatus.SCHEDULED.value
    auction_scheduled_fresh.last_price_refresh_utc = now - timedelta(seconds=30)  # Fresh (<60s)
    auction_scheduled_fresh.auction_end_time_utc = now + timedelta(hours=1)
    assert _should_refresh_price(auction_scheduled_fresh) == False
    
    # BidPlaced but not ended - should refresh if stale
    auction_bid_placed_active = Mock(spec=Auction)
    auction_bid_placed_active.status = AuctionStatus.BID_PLACED.value
    auction_bid_placed_active.auction_end_time_utc = now + timedelta(minutes=30)
    auction_bid_placed_active.last_price_refresh_utc = now - timedelta(seconds=120)
    assert _should_refresh_price(auction_bid_placed_active) == True


def test_should_refresh_price_handles_none_last_refresh():
    """Test that auctions without last_price_refresh_utc are refreshed."""
    now = datetime.utcnow()
    
    auction_no_refresh = Mock(spec=Auction)
    auction_no_refresh.status = AuctionStatus.SCHEDULED.value
    auction_no_refresh.last_price_refresh_utc = None
    auction_no_refresh.auction_end_time_utc = now + timedelta(hours=1)
    assert _should_refresh_price(auction_no_refresh) == True

