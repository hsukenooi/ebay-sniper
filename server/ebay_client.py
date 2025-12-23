import requests
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
import logging

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
        # OAuth token can be set via environment variable or set_oauth_token()
        token_from_env = os.getenv("EBAY_OAUTH_TOKEN")
        self.oauth_token: Optional[str] = token_from_env
        self.oauth_token_expires_at: Optional[datetime] = None
        # Set marketplace to US for production to avoid regional restrictions
        self.marketplace_id = self.MARKETPLACE_ID_US if os.getenv("EBAY_ENV") == "production" else None
        
    def set_oauth_token(self, token: str, expires_in: int):
        """Set OAuth token with expiration."""
        self.oauth_token = token
        self.oauth_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # Refresh 5 min early
        
    def _ensure_token_valid(self):
        """Ensure OAuth token is valid, refresh if needed."""
        if not self.oauth_token:
            raise ValueError("OAuth token not set. Please set EBAY_OAUTH_TOKEN environment variable.")
        # Only check expiration if expires_at is set (tokens from API will have this, env tokens may not)
        if self.oauth_token_expires_at and datetime.utcnow() >= self.oauth_token_expires_at:
            raise ValueError("OAuth token expired. Please refresh your token.")
    
    def _get_headers(self, include_appname: bool = False) -> Dict[str, str]:
        """Get headers for API requests.
        
        Args:
            include_appname: Whether to include X-EBAY-SOA-SECURITY-APPNAME header.
                            Browse API doesn't need it, but Trading API does.
        """
        self._ensure_token_valid()
        headers = {
            "Authorization": f"Bearer {self.oauth_token}",
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
        self._ensure_token_valid()
        
        # Method 1: Try standard Browse API endpoint
        try:
            url = f"{self.base_url}/buy/browse/v1/item/{listing_number}"
            params = {"fieldgroups": "FULL"}
            
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=5)
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
            
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=5)
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
            self._ensure_token_valid()
            
            # eBay Trading API - PlaceOffer requires XML
            # This is a simplified placeholder - production needs proper XML formatting
            url = f"{self.base_url}/ws/api.dll"
            
            # Construct XML payload (simplified - see eBay API docs for full structure)
            xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<PlaceOfferRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{self.oauth_token}</eBayAuthToken>
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

