import requests
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
import logging
import base64

logger = logging.getLogger(__name__)


class eBayClient:
    """Client for eBay API interactions."""
    
    SANDBOX_BASE = "https://api.sandbox.ebay.com"
    PRODUCTION_BASE = "https://api.ebay.com"
    # eBay marketplace IDs: EBAY_US = 0
    MARKETPLACE_ID_US = "EBAY_US"
    
    def __init__(self):
        self.app_id = os.getenv("EBAY_APP_ID")
        self.cert_id = os.getenv("EBAY_CERT_ID")
        self.dev_id = os.getenv("EBAY_DEV_ID")
        self.base_url = self.PRODUCTION_BASE if os.getenv("EBAY_ENV") == "production" else self.SANDBOX_BASE
        # OAuth tokens: Use Application token for Browse API, User token for Trading API
        # If EBAY_OAUTH_APP_TOKEN is set, use it for Browse API (reading auction details)
        # Otherwise fall back to EBAY_OAUTH_TOKEN
        self.oauth_app_token: Optional[str] = os.getenv("EBAY_OAUTH_APP_TOKEN")
        self.oauth_user_token: Optional[str] = os.getenv("EBAY_OAUTH_TOKEN")
        self.oauth_user_refresh_token: Optional[str] = os.getenv("EBAY_OAUTH_REFRESH_TOKEN")
        # For backwards compatibility, if no app token, use user token for both
        self.oauth_token: Optional[str] = self.oauth_app_token or self.oauth_user_token
        # Track expiration times separately for app and user tokens
        self.oauth_app_token_expires_at: Optional[datetime] = None
        self.oauth_user_token_expires_at: Optional[datetime] = None
        # Set marketplace to US for production to avoid regional restrictions
        self.marketplace_id = self.MARKETPLACE_ID_US if os.getenv("EBAY_ENV") == "production" else None
        # OAuth token endpoint
        self.oauth_token_url = f"{self.base_url}/identity/v1/oauth2/token"
        
    def set_oauth_token(self, token: str, expires_in: int):
        """Set OAuth token with expiration (legacy method - use set_app_token/set_user_token instead)."""
        self.oauth_token = token
        self.oauth_app_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # Refresh 5 min early
    
    def refresh_app_token(self) -> bool:
        """
        Refresh Application OAuth token using client credentials grant flow.
        
        Returns:
            True if refresh was successful, False otherwise
        """
        if not self.app_id or not self.cert_id:
            logger.error("Cannot refresh app token: App ID or Cert ID not set")
            return False
        
        try:
            # Encode credentials for Basic Auth
            credentials = f"{self.app_id}:{self.cert_id}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }
            
            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope"
            }
            
            response = requests.post(self.oauth_token_url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            self.oauth_app_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)  # Default to 2 hours
            self.oauth_app_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # Refresh 5 min early
            
            logger.info(f"Successfully refreshed Application OAuth token (expires in {expires_in}s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh Application OAuth token: {e}")
            return False
    
    def refresh_user_token(self) -> bool:
        """
        Refresh User OAuth token using refresh token grant flow.
        
        Returns:
            True if refresh was successful, False otherwise
        """
        if not self.app_id or not self.cert_id:
            logger.error("Cannot refresh user token: App ID or Cert ID not set")
            return False
        
        if not self.oauth_user_refresh_token:
            logger.error("Cannot refresh user token: Refresh token not set (EBAY_OAUTH_REFRESH_TOKEN)")
            return False
        
        try:
            # Encode credentials for Basic Auth
            credentials = f"{self.app_id}:{self.cert_id}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.oauth_user_refresh_token,
                "scope": "https://api.ebay.com/oauth/api_scope"
            }
            
            response = requests.post(self.oauth_token_url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            self.oauth_user_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)  # Default to 2 hours
            self.oauth_user_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # Refresh 5 min early
            
            # Update refresh token if provided (eBay may return a new refresh token)
            if "refresh_token" in token_data:
                self.oauth_user_refresh_token = token_data["refresh_token"]
            
            logger.info(f"Successfully refreshed User OAuth token (expires in {expires_in}s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh User OAuth token: {e}")
            return False
        
    def _ensure_token_valid(self, use_user_token: bool = False):
        """Ensure OAuth token is valid, automatically refresh if needed.
        
        Args:
            use_user_token: If True, check/refresh User token. If False, check/refresh App/User token.
        """
        if use_user_token:
            # Check User token
            if not self.oauth_user_token:
                raise ValueError("User OAuth token not set. Please set EBAY_OAUTH_TOKEN.")
            
            # Check if token is expired or about to expire (within 5 minutes)
            if (self.oauth_user_token_expires_at and 
                datetime.utcnow() >= self.oauth_user_token_expires_at):
                logger.info("User OAuth token expired or about to expire, refreshing...")
                if not self.refresh_user_token():
                    raise ValueError("User OAuth token expired and refresh failed. Please check EBAY_OAUTH_REFRESH_TOKEN.")
        else:
            # Check App token first, fall back to User token
            if self.oauth_app_token:
                # Check if App token is expired or about to expire
                if (self.oauth_app_token_expires_at and 
                    datetime.utcnow() >= self.oauth_app_token_expires_at):
                    logger.info("Application OAuth token expired or about to expire, refreshing...")
                    if not self.refresh_app_token():
                        logger.warning("Failed to refresh App token, falling back to User token")
                        # Fall through to check user token
            elif not self.oauth_user_token:
                raise ValueError("OAuth token not set. Please set EBAY_OAUTH_APP_TOKEN or EBAY_OAUTH_TOKEN.")
            
            # If no app token or refresh failed, check user token
            if not self.oauth_app_token and self.oauth_user_token:
                if (self.oauth_user_token_expires_at and 
                    datetime.utcnow() >= self.oauth_user_token_expires_at):
                    logger.info("User OAuth token expired or about to expire, refreshing...")
                    if not self.refresh_user_token():
                        raise ValueError("OAuth token expired and refresh failed.")
    
    def _get_headers(self, use_user_token: bool = False, include_appname: bool = False) -> Dict[str, str]:
        """Get headers for API requests.
        
        Args:
            use_user_token: If True, use User OAuth token (for Trading API/bidding).
                          If False, use Application token for Browse API (reading).
            include_appname: Whether to include X-EBAY-SOA-SECURITY-APPNAME header.
                            Browse API doesn't need it, but Trading API does.
        """
        # Select appropriate token: User token for bidding, App token for reading
        if use_user_token:
            token = self.oauth_user_token
            if not token:
                raise ValueError("User OAuth token not set. Please set EBAY_OAUTH_TOKEN environment variable for bidding.")
        else:
            # Prefer app token for Browse API, fall back to user token
            token = self.oauth_app_token or self.oauth_user_token
            if not token:
                raise ValueError("OAuth token not set. Please set EBAY_OAUTH_APP_TOKEN or EBAY_OAUTH_TOKEN.")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # Add marketplace ID header for production to ensure US site
        if self.marketplace_id:
            headers["X-EBAY-C-MARKETPLACE-ID"] = self.marketplace_id
        if include_appname:
            headers["X-EBAY-SOA-SECURITY-APPNAME"] = self.app_id
        return headers
    
    def _parse_browse_api_response(self, data: Dict[str, Any], listing_number: str) -> Dict[str, Any]:
        """Parse Browse API response into standardized format."""
        # Extract auction end time
        end_time_str = data.get("itemEndDate", "")
        if not end_time_str:
            raise ValueError("No end date found for auction")
        
        auction_end_time_utc = datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).replace(tzinfo=None)
        
        # Extract current price
        price_info = data.get("price", {})
        current_price = Decimal(str(price_info.get("value", 0)))
        currency = price_info.get("currency", "USD")
        
        # Extract title and URL
        item_title = data.get("title", "Unknown Item")
        listing_url = data.get("itemWebUrl", f"https://www.ebay.com/itm/{listing_number}")
        
        return {
            "listing_url": listing_url,
            "item_title": item_title,
            "current_price": current_price,
            "currency": currency,
            "auction_end_time_utc": auction_end_time_utc,
        }
    
    def _get_item_via_trading_api(self, listing_number: str) -> Dict[str, Any]:
        """Fallback: Get item details via Trading API GetItem call."""
        try:
            # Trading API uses XML and different endpoint structure
            # For now, this is a placeholder - Trading API requires more complex XML handling
            # and may not work with OAuth tokens the same way
            raise NotImplementedError("Trading API fallback not yet implemented")
        except Exception as e:
            logger.debug(f"Trading API fallback failed: {e}")
            raise
    
    def get_auction_details(self, listing_number: str) -> Dict[str, Any]:
        """
        Fetch auction details including current price, end time, title, URL.
        Uses Application OAuth token (if available) or falls back to User token.
        Tries multiple methods:
        1. Browse API getItem (standard endpoint)
        2. Browse API getItemByLegacyId (fallback for legacy item IDs)
        
        Returns dict with:
        - listing_url
        - item_title
        - current_price (Decimal)
        - currency
        - auction_end_time_utc (datetime)
        """
        self._ensure_token_valid(use_user_token=False)  # Use App token for reading
        
        # Method 1: Try standard Browse API endpoint
        try:
            url = f"{self.base_url}/buy/browse/v1/item/{listing_number}"
            params = {"fieldgroups": "FULL"}
            
            response = requests.get(url, headers=self._get_headers(use_user_token=False), params=params, timeout=5)
            # Handle 401 errors by attempting token refresh
            if response.status_code == 401:
                logger.warning("Received 401 error, attempting token refresh...")
                if self.refresh_app_token() or (not self.oauth_app_token and self.refresh_user_token()):
                    # Retry the request with new token
                    response = requests.get(url, headers=self._get_headers(use_user_token=False), params=params, timeout=5)
            
            response.raise_for_status()
            data = response.json()
            return self._parse_browse_api_response(data, listing_number)
        except requests.exceptions.HTTPError as e:
            # Check if it's a 404 error - if so, try fallback method
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                logger.info(f"Standard Browse API returned 404 for {listing_number}, trying getItemByLegacyId...")
                # Continue to fallback method below - don't re-raise
            else:
                # For non-404 HTTP errors, re-raise immediately
                raise
        except requests.exceptions.RequestException:
            # For other request exceptions, re-raise immediately
            raise
        
        # Method 2: Try getItemByLegacyId endpoint (fallback for legacy item IDs)
        # Note: getItemByLegacyId doesn't support "FULL" fieldgroups, so we omit it
        try:
            url = f"{self.base_url}/buy/browse/v1/item/get_item_by_legacy_id"
            params = {
                "legacy_item_id": listing_number
            }
            
            response = requests.get(url, headers=self._get_headers(use_user_token=False), params=params, timeout=5)
            # Handle 401 errors by attempting token refresh
            if response.status_code == 401:
                logger.warning("Received 401 error in fallback, attempting token refresh...")
                if self.refresh_app_token() or (not self.oauth_app_token and self.refresh_user_token()):
                    # Retry the request with new token
                    response = requests.get(url, headers=self._get_headers(use_user_token=False), params=params, timeout=5)
            
            response.raise_for_status()
            data = response.json()
            return self._parse_browse_api_response(data, listing_number)
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                logger.warning(f"Both Browse API methods returned 404 for {listing_number}")
                raise requests.exceptions.RequestException(
                    f"Listing {listing_number} not found via Browse API. "
                    "This listing may not be accessible through the API."
                )
            raise
        except Exception as e:
            logger.error(f"Error in getItemByLegacyId fallback for {listing_number}: {e}")
            raise
    
    def place_bid(self, listing_number: str, bid_amount: Decimal) -> Dict[str, Any]:
        """
        Place a bid on an auction.
        
        NOTE: eBay Trading API requires XML format. This is a placeholder implementation.
        In production, properly format XML request according to eBay Trading API docs.
        
        Returns dict with result information.
        """
        try:
            self._ensure_token_valid(use_user_token=True)  # Must use User token for bidding
            
            # eBay Trading API - PlaceOffer requires XML
            # This is a simplified placeholder - production needs proper XML formatting
            url = f"{self.base_url}/ws/api.dll"
            
            # Construct XML payload (simplified - see eBay API docs for full structure)
            # Use User token for Trading API
            user_token = self.oauth_user_token
            if not user_token:
                raise ValueError("User OAuth token required for placing bids. Set EBAY_OAUTH_TOKEN.")
            xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<PlaceOfferRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{user_token}</eBayAuthToken>
    </RequesterCredentials>
    <ItemID>{listing_number}</ItemID>
    <Offer>
        <MaxBid>{float(bid_amount)}</MaxBid>
        <Quantity>1</Quantity>
    </Offer>
</PlaceOfferRequest>"""
            
            headers = {
                "X-EBAY-SOA-OPERATION-NAME": "PlaceOffer",
                "X-EBAY-SOA-SERVICE-VERSION": "1.0.0",
                "X-EBAY-SOA-SECURITY-APPNAME": self.app_id,
                "Content-Type": "text/xml",
            }
            
            response = requests.post(url, headers=headers, data=xml_payload, timeout=0.6)
            
            status_code = response.status_code
            
            # Handle 401 errors by attempting token refresh
            if status_code == 401:
                logger.warning("Received 401 error when placing bid, attempting token refresh...")
                if self.refresh_user_token():
                    # Update token in XML payload and retry
                    user_token = self.oauth_user_token
                    xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<PlaceOfferRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{user_token}</eBayAuthToken>
    </RequesterCredentials>
    <ItemID>{listing_number}</ItemID>
    <Offer>
        <MaxBid>{float(bid_amount)}</MaxBid>
        <Quantity>1</Quantity>
    </Offer>
</PlaceOfferRequest>"""
                    response = requests.post(url, headers=headers, data=xml_payload, timeout=0.6)
                    status_code = response.status_code
            
            if status_code in [500, 502, 503, 504]:
                raise requests.exceptions.RequestException(f"eBay server error: {status_code}")
            
            if status_code == 429:
                raise requests.exceptions.RequestException("Rate limited (429)")
            
            response.raise_for_status()
            
            # Parse XML response (simplified - in production, parse XML properly)
            # Check for error codes in response
            if "Error" in response.text or "Ack" not in response.text:
                raise requests.exceptions.RequestException("Bid placement failed - check response")
            
            return {"success": True}
            
        except requests.exceptions.Timeout:
            raise
        except requests.exceptions.RequestException as e:
            # Re-raise to trigger retry logic in worker
            raise
        except Exception as e:
            logger.error(f"Unexpected error placing bid: {e}")
            raise

