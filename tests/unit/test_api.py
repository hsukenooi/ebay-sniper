import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import jwt
import os

# Set test secret key before importing app
os.environ["SECRET_KEY"] = "test-secret-key"

from server.api import app
from database.models import AuctionStatus


def test_auth_endpoint(client):
    """Test authentication endpoint."""
    response = client.post("/auth", json={"username": "testuser", "password": "testpass"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["token"] is not None


def test_add_sniper_without_auth(client):
    """Test adding sniper without authentication."""
    response = client.post("/sniper/add", json={"listing_number": "123", "max_bid": 100.0})
    assert response.status_code == 401


@patch("server.api.ebay_client.get_auction_details")
def test_add_sniper_success(mock_get_details, client, auth_headers, db_session):
    """Test successfully adding a sniper."""
    # Mock eBay client response
    mock_get_details.return_value = {
        "listing_url": "https://www.ebay.com/itm/123456789",
        "item_title": "Test Item",
        "current_price": Decimal("100.00"),
        "currency": "USD",
        "auction_end_time_utc": datetime.utcnow() + timedelta(hours=1),
    }
    
    response = client.post(
        "/sniper/add",
        json={"listing_number": "123456789", "max_bid": 150.0},
        headers=auth_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["listing_number"] == "123456789"
    assert float(data["max_bid"]) == 150.0
    assert data["status"] == AuctionStatus.SCHEDULED.value


@patch("server.api.ebay_client")
def test_add_sniper_duplicate(mock_ebay_client, client, auth_headers, db_session, sample_auction):
    """Test adding duplicate sniper."""
    response = client.post(
        "/sniper/add",
        json={"listing_number": "123456789", "max_bid": 150.0},
        headers=auth_headers,
    )
    
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_list_snipers_without_auth(client):
    """Test listing snipers without authentication."""
    response = client.get("/sniper/list")
    assert response.status_code == 401


def test_list_snipers_empty(client, auth_headers, db_session):
    """Test listing snipers when none exist."""
    response = client.get("/sniper/list", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_snipers_with_data(client, auth_headers, db_session, sample_auction):
    """Test listing snipers with existing data."""
    response = client.get("/sniper/list", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == sample_auction.id


def test_get_status_without_auth(client):
    """Test getting status without authentication."""
    response = client.get("/sniper/1/status")
    assert response.status_code == 401


def test_get_status_not_found(client, auth_headers, db_session):
    """Test getting status for non-existent auction."""
    response = client.get("/sniper/999/status", headers=auth_headers)
    assert response.status_code == 404


def test_get_status_success(client, auth_headers, db_session, sample_auction):
    """Test successfully getting auction status."""
    response = client.get(f"/sniper/{sample_auction.id}/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_auction.id
    assert data["status"] == sample_auction.status


def test_remove_sniper_without_auth(client):
    """Test removing sniper without authentication."""
    response = client.delete("/sniper/1")
    assert response.status_code == 401


def test_remove_sniper_not_found(client, auth_headers, db_session):
    """Test removing non-existent sniper."""
    response = client.delete("/sniper/999", headers=auth_headers)
    assert response.status_code == 404


def test_remove_sniper_wrong_status(client, auth_headers, db_session, sample_auction):
    """Test removing sniper with wrong status."""
    # Change status to Executing
    sample_auction.status = AuctionStatus.EXECUTING.value
    db_session.commit()
    
    response = client.delete(f"/sniper/{sample_auction.id}", headers=auth_headers)
    assert response.status_code == 400


def test_remove_sniper_success(client, auth_headers, db_session, sample_auction):
    """Test successfully removing a sniper."""
    response = client.delete(f"/sniper/{sample_auction.id}", headers=auth_headers)
    assert response.status_code == 200
    
    # Verify status changed
    db_session.refresh(sample_auction)
    assert sample_auction.status == AuctionStatus.CANCELLED.value


def test_get_logs_without_auth(client):
    """Test getting logs without authentication."""
    response = client.get("/sniper/1/logs")
    assert response.status_code == 401


def test_get_logs_not_found(client, auth_headers, db_session):
    """Test getting logs for non-existent auction."""
    response = client.get("/sniper/999/logs", headers=auth_headers)
    assert response.status_code == 404


def test_get_logs_no_attempts(client, auth_headers, db_session, sample_auction):
    """Test getting logs when no bid attempts exist."""
    response = client.get(f"/sniper/{sample_auction.id}/logs", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() is None


def test_get_logs_with_attempts(client, auth_headers, db_session, sample_auction):
    """Test getting logs when bid attempts exist."""
    from database.models import BidAttempt, BidResult
    
    bid_attempt = BidAttempt(
        auction_id=sample_auction.id,
        attempt_time_utc=datetime.utcnow(),
        result=BidResult.SUCCESS.value,
    )
    db_session.add(bid_attempt)
    db_session.commit()
    
    response = client.get(f"/sniper/{sample_auction.id}/logs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["auction_id"] == sample_auction.id
    assert data["result"] == BidResult.SUCCESS.value

