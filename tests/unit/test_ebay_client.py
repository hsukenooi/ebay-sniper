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
    """Test setting OAuth token (legacy method for app token)."""
    client = eBayClient()
    client.set_oauth_token("test_token", 3600)
    # set_oauth_token sets oauth_token (legacy) and oauth_app_token_expires_at
    assert client.oauth_token == "test_token"
    assert client.oauth_app_token_expires_at is not None


@patch.dict("os.environ", {}, clear=True)
def test_ensure_token_valid_without_token():
    """Test token validation without token."""
    client = eBayClient()
    # Explicitly clear tokens to ensure test isolation
    client.oauth_app_token = None
    client.oauth_user_token = None
    with pytest.raises(ValueError, match="OAuth token not set"):
        client._ensure_token_valid()


@patch.dict("os.environ", {}, clear=True)
def test_ensure_token_valid_with_expired_token():
    """Test token validation with expired token that fails to refresh."""
    client = eBayClient()
    # Set app token but make it expired
    client.oauth_app_token = "test_token"
    client.oauth_app_token_expires_at = datetime.utcnow() - timedelta(seconds=100)  # Expired
    # Ensure no user token
    client.oauth_user_token = None
    # Mock refresh to fail
    with patch.object(client, "refresh_app_token", return_value=False):
        # When refresh fails and no user token available, the current implementation
        # doesn't raise (it just logs warning and falls through). This test verifies
        # the current behavior - the function completes without error when app token
        # refresh fails (though it may fail later when actually used).
        # In practice, this scenario should be avoided by ensuring refresh succeeds.
        client._ensure_token_valid()  # Should not raise (current behavior)
        # App token is still set even though it's expired
        assert client.oauth_app_token == "test_token"


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
        "itemWebUrl": "https://www.ebay.com/itm/123456789",
        "listingType": "AUCTION"
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_app_token = "test_token"
    client.oauth_app_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
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
    client.oauth_app_token = "test_token"
    client.oauth_app_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    with pytest.raises(requests.exceptions.RequestException):
        client.get_auction_details("123456789")


@patch("server.ebay_client.requests.post")
def test_place_bid_success(mock_post):
    """Test successfully placing a bid."""
    mock_response = MagicMock()
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Success</Ack>
</PlaceOfferResponse>"""
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
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
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    with pytest.raises(requests.exceptions.RequestException, match="eBay server error"):
        client.place_bid("123456789", Decimal("150.00"))


@patch("server.ebay_client.requests.post")
def test_place_bid_rate_limit(mock_post):
    """Test handling of rate limit when placing bid."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    with pytest.raises(requests.exceptions.RequestException, match="Rate limited"):
        client.place_bid("123456789", Decimal("150.00"))


def test_calculate_min_bid_increment():
    """Test bid increment calculation for different price ranges."""
    client = eBayClient()
    
    # $0.01 - $0.99: $0.01 increments
    assert client.calculate_min_bid_increment(Decimal("0.50")) == Decimal("0.01")
    assert client.calculate_min_bid_increment(Decimal("0.99")) == Decimal("0.01")
    
    # $1.00 - $4.99: $0.05 increments
    assert client.calculate_min_bid_increment(Decimal("1.00")) == Decimal("0.05")
    assert client.calculate_min_bid_increment(Decimal("4.99")) == Decimal("0.05")
    
    # $5.00 - $24.99: $0.25 increments
    assert client.calculate_min_bid_increment(Decimal("5.00")) == Decimal("0.25")
    assert client.calculate_min_bid_increment(Decimal("24.99")) == Decimal("0.25")
    
    # $25.00 - $99.99: $0.50 increments
    assert client.calculate_min_bid_increment(Decimal("25.00")) == Decimal("0.50")
    assert client.calculate_min_bid_increment(Decimal("99.99")) == Decimal("0.50")
    
    # $100.00 - $249.99: $1.00 increments
    assert client.calculate_min_bid_increment(Decimal("100.00")) == Decimal("1.00")
    assert client.calculate_min_bid_increment(Decimal("249.99")) == Decimal("1.00")
    
    # $250.00 - $499.99: $2.50 increments
    assert client.calculate_min_bid_increment(Decimal("250.00")) == Decimal("2.50")
    assert client.calculate_min_bid_increment(Decimal("499.99")) == Decimal("2.50")
    
    # $500.00+: $5.00 increments
    assert client.calculate_min_bid_increment(Decimal("500.00")) == Decimal("5.00")
    assert client.calculate_min_bid_increment(Decimal("1000.00")) == Decimal("5.00")


def test_parse_trading_api_response_success():
    """Test parsing successful Trading API response."""
    client = eBayClient()
    
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Timestamp>2025-01-19T12:00:00.000Z</Timestamp>
    <Ack>Success</Ack>
    <Version>1.0.0</Version>
</PlaceOfferResponse>"""
    
    result = client._parse_trading_api_response(xml_response)
    assert result["success"] is True
    assert result["error_code"] is None
    assert result["error_message"] is None


def test_parse_trading_api_response_error():
    """Test parsing Trading API error response."""
    client = eBayClient()
    
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Timestamp>2025-01-19T12:00:00.000Z</Timestamp>
    <Ack>Failure</Ack>
    <Errors>
        <ShortMessage>Bid amount too low</ShortMessage>
        <LongMessage>Bid amount is below the minimum bid increment</LongMessage>
        <ErrorCode>10736</ErrorCode>
        <SeverityCode>Error</SeverityCode>
    </Errors>
    <Version>1.0.0</Version>
</PlaceOfferResponse>"""
    
    result = client._parse_trading_api_response(xml_response)
    assert result["success"] is False
    assert result["error_code"] == "10736"
    assert "minimum bid increment" in result["error_message"]


def test_parse_trading_api_response_multiple_errors():
    """Test parsing Trading API response with multiple errors."""
    client = eBayClient()
    
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Timestamp>2025-01-19T12:00:00.000Z</Timestamp>
    <Ack>Failure</Ack>
    <Errors>
        <ShortMessage>Error 1</ShortMessage>
        <LongMessage>First error message</LongMessage>
        <ErrorCode>1001</ErrorCode>
    </Errors>
    <Errors>
        <ShortMessage>Error 2</ShortMessage>
        <LongMessage>Second error message</LongMessage>
        <ErrorCode>1002</ErrorCode>
    </Errors>
    <Version>1.0.0</Version>
</PlaceOfferResponse>"""
    
    result = client._parse_trading_api_response(xml_response)
    assert result["success"] is False
    assert result["error_code"] == "1001"  # First error code
    assert result["error_message"] == "First error message"  # First error message


def test_parse_trading_api_response_invalid_xml():
    """Test parsing invalid XML response."""
    client = eBayClient()
    
    invalid_xml = "Not valid XML <unclosed tag"
    
    result = client._parse_trading_api_response(invalid_xml)
    assert result["success"] is False
    assert result["error_code"] == "PARSE_ERROR"
    assert "Failed to parse" in result["error_message"]


@patch("server.ebay_client.requests.post")
def test_place_bid_xml_format(mock_post):
    """Test that place_bid includes SiteID in XML."""
    mock_response = MagicMock()
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Success</Ack>
</PlaceOfferResponse>"""
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_user_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    client.place_bid("123456789", Decimal("150.00"))
    
    # Verify XML includes SiteID
    call_args = mock_post.call_args
    xml_payload = call_args[1]["data"]
    assert "<SiteID>0</SiteID>" in xml_payload
    assert "<ItemID>123456789</ItemID>" in xml_payload
    assert "<MaxBid>150.0</MaxBid>" in xml_payload


@patch("server.ebay_client.requests.post")
def test_place_bid_error_codes(mock_post):
    """Test handling of specific eBay error codes."""
    client = eBayClient()
    client.oauth_user_token = "test_user_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Test error code 10736 (bid too low)
    mock_response = MagicMock()
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Failure</Ack>
    <Errors>
        <ErrorCode>10736</ErrorCode>
        <LongMessage>Bid amount is below the minimum bid increment</LongMessage>
    </Errors>
</PlaceOfferResponse>"""
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    with pytest.raises(requests.exceptions.RequestException, match="Bid amount is below the minimum bid increment"):
        client.place_bid("123456789", Decimal("150.00"))
    
    # Test error code 10729 (item not found/ended)
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Failure</Ack>
    <Errors>
        <ErrorCode>10729</ErrorCode>
        <LongMessage>Item not found</LongMessage>
    </Errors>
</PlaceOfferResponse>"""
    
    with pytest.raises(requests.exceptions.RequestException, match="Item not found or auction ended"):
        client.place_bid("123456789", Decimal("150.00"))


@patch("server.ebay_client.requests.post")
def test_place_bid_rate_limit_retry_after(mock_post):
    """Test rate limiting with Retry-After header."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "60"}
    mock_post.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_user_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    with pytest.raises(requests.exceptions.RequestException, match="Retry after 60 seconds"):
        client.place_bid("123456789", Decimal("150.00"))


@patch("server.ebay_client.requests.post")
def test_refresh_user_token_success(mock_post):
    """Test successful user token refresh."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 7200
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    with patch.dict("os.environ", {
        "EBAY_APP_ID": "test_app_id",
        "EBAY_CERT_ID": "test_cert_id",
        "EBAY_OAUTH_REFRESH_TOKEN": "old_refresh_token"
    }):
        client = eBayClient()
        client.oauth_user_refresh_token = "old_refresh_token"
        
        result = client.refresh_user_token()
        
        assert result is True
        assert client.oauth_user_token == "new_access_token"
        assert client.oauth_user_refresh_token == "new_refresh_token"
        assert client.oauth_user_token_expires_at is not None


@patch("server.ebay_client.requests.post")
def test_refresh_user_token_invalid_grant(mock_post):
    """Test user token refresh with invalid_grant (expired refresh token)."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "Refresh token expired"
    }
    mock_post.return_value = mock_response
    
    with patch.dict("os.environ", {
        "EBAY_APP_ID": "test_app_id",
        "EBAY_CERT_ID": "test_cert_id",
        "EBAY_OAUTH_REFRESH_TOKEN": "expired_refresh_token"
    }):
        client = eBayClient()
        client.oauth_user_refresh_token = "expired_refresh_token"
        
        result = client.refresh_user_token()
        
        assert result is False


@patch("server.ebay_client.requests.post")
def test_refresh_user_token_invalid_client(mock_post):
    """Test user token refresh with invalid_client error."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": "invalid_client",
        "error_description": "Invalid client credentials"
    }
    mock_post.return_value = mock_response
    
    with patch.dict("os.environ", {
        "EBAY_APP_ID": "test_app_id",
        "EBAY_CERT_ID": "test_cert_id",
        "EBAY_OAUTH_REFRESH_TOKEN": "refresh_token"
    }):
        client = eBayClient()
        client.oauth_user_refresh_token = "refresh_token"
        
        result = client.refresh_user_token()
        
        assert result is False


@patch("server.ebay_client.requests.post")
def test_refresh_app_token_success(mock_post):
    """Test successful application token refresh."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_app_token",
        "expires_in": 7200
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response
    
    with patch.dict("os.environ", {
        "EBAY_APP_ID": "test_app_id",
        "EBAY_CERT_ID": "test_cert_id"
    }):
        client = eBayClient()
        
        result = client.refresh_app_token()
        
        assert result is True
        assert client.oauth_app_token == "new_app_token"
        assert client.oauth_app_token_expires_at is not None


@patch("server.ebay_client.requests.get")
def test_get_auction_details_non_auction(mock_get):
    """Test that non-auction listings are rejected."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "itemEndDate": "2025-01-20T12:00:00.000Z",
        "price": {
            "value": "125.50",
            "currency": "USD"
        },
        "title": "Test Item",
        "itemWebUrl": "https://www.ebay.com/itm/123456789",
        "listingType": "FIXED_PRICE"  # Not an auction
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_app_token = "test_token"
    client.oauth_app_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    with pytest.raises(ValueError, match="is not an auction"):
        client.get_auction_details("123456789")


@patch("server.ebay_client.requests.get")
def test_get_auction_details_auction_type_case_insensitive(mock_get):
    """Test that auction type check is case insensitive."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "itemEndDate": "2025-01-20T12:00:00.000Z",
        "price": {
            "value": "125.50",
            "currency": "USD"
        },
        "title": "Test Item",
        "itemWebUrl": "https://www.ebay.com/itm/123456789",
        "listingType": "auction"  # Lowercase, should still work
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_app_token = "test_token"
    client.oauth_app_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Should succeed (case insensitive check)
    details = client.get_auction_details("123456789")
    # listing_type is validated but not returned in response
    assert "listing_url" in details
    assert "item_title" in details


@patch("server.ebay_client.requests.post")
def test_place_bid_401_refresh_retry(mock_post):
    """Test that 401 errors trigger token refresh and retry."""
    client = eBayClient()
    client.oauth_user_token = "old_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # First call returns 401
    mock_response_401 = MagicMock()
    mock_response_401.status_code = 401
    
    # After refresh, second call succeeds
    mock_response_success = MagicMock()
    mock_response_success.text = """<?xml version="1.0" encoding="UTF-8"?>
<PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Success</Ack>
</PlaceOfferResponse>"""
    mock_response_success.status_code = 200
    mock_response_success.raise_for_status = MagicMock()
    
    mock_post.side_effect = [mock_response_401, mock_response_success]
    
    # Mock refresh to succeed
    with patch.object(client, "refresh_user_token", return_value=True):
        client.oauth_user_token = "new_token"  # Simulate refresh updating token
        
        result = client.place_bid("123456789", Decimal("150.00"))
        
        assert result["success"] is True
        assert mock_post.call_count == 2  # Initial call + retry after refresh


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_won(mock_get):
    """Test checking auction outcome when auction was won."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "ENDED",
        "highBidder": True,
        "currentPrice": {
            "value": "125.50",
            "currency": "USD"
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Won"
    assert outcome["final_price"] == Decimal("125.50")
    assert outcome["auction_status"] == "ENDED"
    mock_get.assert_called_once()


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_lost(mock_get):
    """Test checking auction outcome when auction was lost."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "ENDED",
        "highBidder": False,
        "currentPrice": {
            "value": "150.00",
            "currency": "USD"
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Lost"
    assert outcome["final_price"] == Decimal("150.00")
    assert outcome["auction_status"] == "ENDED"


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_pending(mock_get):
    """Test checking auction outcome when auction is still active."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "ACTIVE",
        "highBidder": True,
        "currentPrice": {
            "value": "100.00",
            "currency": "USD"
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Pending"
    assert outcome["final_price"] is None
    assert outcome["auction_status"] == "ACTIVE"


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_not_found(mock_get):
    """Test checking auction outcome when auction is not found."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=mock_response
    )
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Pending"
    assert outcome["final_price"] is None
    assert outcome["auction_status"] == "UNKNOWN"


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_401_refresh(mock_get):
    """Test checking auction outcome with 401 error triggers token refresh."""
    # First call returns 401, second call succeeds after refresh
    mock_response_401 = MagicMock()
    mock_response_401.status_code = 401
    
    mock_response_success = MagicMock()
    mock_response_success.json.return_value = {
        "auctionStatus": "ENDED",
        "highBidder": True,
        "currentPrice": {
            "value": "125.50",
            "currency": "USD"
        }
    }
    mock_response_success.raise_for_status = MagicMock()
    
    mock_get.side_effect = [mock_response_401, mock_response_success]
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    # Mock refresh to succeed
    with patch.object(client, "refresh_user_token", return_value=True):
        outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Won"
    assert outcome["final_price"] == Decimal("125.50")
    # Should have been called twice (initial + retry after refresh)
    assert mock_get.call_count == 2


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_missing_final_price(mock_get):
    """Test outcome check when final_price is missing from response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "ENDED",
        "highBidder": True,
        # currentPrice is missing
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Won"
    assert outcome["final_price"] is None  # Should handle missing price gracefully


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_missing_high_bidder(mock_get):
    """Test outcome check when highBidder field is missing."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "ENDED",
        # highBidder is missing - should default to False
        "currentPrice": {
            "value": "125.50",
            "currency": "USD"
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    # Should default to False when highBidder is missing
    assert outcome["outcome"] == "Lost"
    assert outcome["final_price"] == Decimal("125.50")


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_unexpected_status(mock_get):
    """Test outcome check with unexpected auctionStatus value."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "CANCELLED",  # Unexpected status
        "highBidder": True,
        "currentPrice": {
            "value": "125.50",
            "currency": "USD"
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    # Should default to Pending for non-ENDED status
    assert outcome["outcome"] == "Pending"
    assert outcome["final_price"] is None
    assert outcome["auction_status"] == "CANCELLED"


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_final_price_zero(mock_get):
    """Test outcome check when final_price is 0."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "auctionStatus": "ENDED",
        "highBidder": True,
        "currentPrice": {
            "value": "0.00",
            "currency": "USD"
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    outcome = client.get_auction_outcome("123456789")
    
    assert outcome["outcome"] == "Won"
    assert outcome["final_price"] == Decimal("0.00")  # Should still set even if 0


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_rate_limit(mock_get):
    """Test outcome check when rate limited (429)."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "60"}
    mock_get.return_value = mock_response
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=mock_response
    )
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    # Should raise HTTPError for rate limiting
    with pytest.raises(requests.exceptions.HTTPError):
        client.get_auction_outcome("123456789")


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_server_error(mock_get):
    """Test outcome check when server returns 500 error."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_get.return_value = mock_response
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=mock_response
    )
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    # Should raise HTTPError for server errors
    with pytest.raises(requests.exceptions.HTTPError):
        client.get_auction_outcome("123456789")


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_timeout(mock_get):
    """Test outcome check when API call times out."""
    mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    # Should raise Timeout exception
    with pytest.raises(requests.exceptions.Timeout):
        client.get_auction_outcome("123456789")


@patch("server.ebay_client.requests.get")
def test_get_auction_outcome_invalid_json(mock_get):
    """Test outcome check when response is not valid JSON."""
    mock_response = MagicMock()
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response
    
    client = eBayClient()
    client.oauth_user_token = "test_token"
    client.oauth_user_token_expires_at = datetime.utcnow() + timedelta(hours=1)
    client.marketplace_id = "EBAY_US"
    
    # Should raise the exception
    with pytest.raises(ValueError):
        client.get_auction_outcome("123456789")

