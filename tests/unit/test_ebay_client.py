import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import datetime, timedelta
from server.ebay_client import eBayClient
import requests


def test_ebay_client_init():
    """Test eBay client initialization."""
    with patch.dict("os.environ", {
        "EBAY_APP_ID": "test_app_id",
        "EBAY_CERT_ID": "test_cert_id",
        "EBAY_DEV_ID": "test_dev_id",
    }):
        client = eBayClient()
        assert client.app_id == "test_app_id"
        assert client.cert_id == "test_cert_id"
        assert client.dev_id == "test_dev_id"


def test_set_oauth_token():
    """Test setting OAuth token."""
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    assert client.oauth_token == "test_token"
    assert client.oauth_token_expires_at is not None


def test_ensure_token_valid_without_token():
    """Test token validation without token."""
    client = eBayClient()
    with pytest.raises(ValueError, match="OAuth token expired or not set"):
        client._ensure_token_valid()


def test_ensure_token_valid_with_expired_token():
    """Test token validation with expired token."""
    client = eBayClient()
    client.set_oauth_token("test_token", -100)  # Expired
    with pytest.raises(ValueError, match="OAuth token expired or not set"):
        client._ensure_token_valid()


@patch("server.ebay_client.requests.get")
def test_get_auction_details_success(mock_get):
    """Test successfully fetching auction details."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "itemEndDate": "2025-01-20T12:00:00.000Z",
        "price": {
            "value": "125.50",
            "currency": "USD"
        },
        "title": "Test Item",
        "itemWebUrl": "https://www.ebay.com/itm/123456789"
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    
    details = client.get_auction_details("123456789")
    
    assert details["item_title"] == "Test Item"
    assert details["current_price"] == Decimal("125.50")
    assert details["currency"] == "USD"
    assert "listing_url" in details
    assert "auction_end_time_utc" in details


@patch("server.ebay_client.requests.get")
def test_get_auction_details_failure(mock_get):
    """Test handling of failed auction details fetch."""
    mock_get.side_effect = requests.exceptions.RequestException("Network error")
    
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    
    with pytest.raises(requests.exceptions.RequestException):
        client.get_auction_details("123456789")


@patch("server.ebay_client.requests.post")
def test_place_bid_success(mock_post):
    """Test successfully placing a bid."""
    mock_response = MagicMock()
    mock_response.text = "<Ack>Success</Ack>"
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    
    result = client.place_bid("123456789", Decimal("150.00"))
    
    assert result["success"] is True
    mock_post.assert_called_once()


@patch("server.ebay_client.requests.post")
def test_place_bid_server_error(mock_post):
    """Test handling of server error when placing bid."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    
    with pytest.raises(requests.exceptions.RequestException, match="eBay server error"):
        client.place_bid("123456789", Decimal("150.00"))


@patch("server.ebay_client.requests.post")
def test_place_bid_rate_limit(mock_post):
    """Test handling of rate limit when placing bid."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    
    with pytest.raises(requests.exceptions.RequestException, match="Rate limited"):
        client.place_bid("123456789", Decimal("150.00"))

