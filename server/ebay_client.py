import requests
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
import logging
import base64
import xml.etree.ElementTree as ET

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
        # Dev ID is not required for OAuth 2.0 but kept for backwards compatibility
        self.dev_id = os.getenv("EBAY_DEV_ID")
        self.base_url = self.PRODUCTION_BASE if os.getenv("EBAY_ENV") == "production" else self.SANDBOX_BASE
        # OAuth tokens: Use Application token for Browse API, User token for Trading API
        # If EBAY_OAUTH_APP_TOKEN is set, use it for Browse API (reading auction details)
        # Otherwise fall back to EBAY_OAUTH_TOKEN
        self.oauth_app_token: Optional[str] = os.getenv("EBAY_OAUTH_APP_TOKEN")
        self.oauth_user_token: Optional[str] = os.getenv("EBAY_OAUTH_TOKEN")
        self.oauth_user_refresh_token: Optional[str] = os.getenv("EBAY_OAUTH_REFRESH_TOKEN")
        # Legacy attribute for backwards compatibility (deprecated - use oauth_app_token or oauth_user_token)
        self.oauth_token: Optional[str] = self.oauth_app_token or self.oauth_user_token
        # Track expiration times separately for app and user tokens
        self.oauth_app_token_expires_at: Optional[datetime] = None
        self.oauth_user_token_expires_at: Optional[datetime] = None
        # Set marketplace to US for production to avoid regional restrictions
        self.marketplace_id = self.MARKETPLACE_ID_US if os.getenv("EBAY_ENV") == "production" else None
        # OAuth token endpoint
        self.oauth_token_url = f"{self.base_url}/identity/v1/oauth2/token"
        
    def set_oauth_token(self, token: str, expires_in: int):
        """
        Set OAuth token with expiration (legacy method - deprecated).
        
        DEPRECATED: This method exists only for backwards compatibility.
        Use oauth_app_token/oauth_user_token environment variables instead.
        """
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
            
            # Handle specific error cases
            if response.status_code == 400:
                error_data = response.json()
                error = error_data.get("error", "")
                if error == "invalid_grant":
                    logger.error(
                        "Refresh token expired or revoked. User must re-authenticate using scripts/get_ebay_tokens.py"
                    )
                    return False
                elif error == "invalid_client":
                    logger.error("Invalid client credentials. Check EBAY_APP_ID and EBAY_CERT_ID")
                    return False
            
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
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to refresh User OAuth token: HTTP {e.response.status_code} - {e.response.text}")
            return False
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
                    raise ValueError(
                        "User OAuth token expired and refresh failed. "
                        "Refresh token may have expired. Please re-authenticate using scripts/get_ebay_tokens.py"
                    )
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
        
        # Extract seller name (username if available, otherwise userId)
        seller_name = None
        seller_info = data.get("seller", {})
        if seller_info:
            seller_name = seller_info.get("username") or seller_info.get("userId")
        
        # Extract listing type (validate it's an auction)
        listing_type = data.get("listingType", "")
        if listing_type and listing_type.upper() != "AUCTION":
            raise ValueError(
                f"Item {listing_number} is not an auction (type: {listing_type}). "
                "Only auction-style listings can be bid on."
            )
        
        return {
            "listing_url": listing_url,
            "item_title": item_title,
            "seller_name": seller_name,
            "current_price": current_price,
            "currency": currency,
            "auction_end_time_utc": auction_end_time_utc,
        }
    
    @staticmethod
    def calculate_min_bid_increment(current_price: Decimal) -> Decimal:
        """
        Calculate the minimum bid increment based on eBay's rules.
        
        NOTE: This method is currently unused in production code.
        eBay's proxy bidding system handles increments automatically when using max_bid.
        Kept for potential future use or reference.
        
        eBay Bid Increments:
        - $0.01 - $0.99: $0.01 increments
        - $1.00 - $4.99: $0.05 increments
        - $5.00 - $24.99: $0.25 increments
        - $25.00 - $99.99: $0.50 increments
        - $100.00 - $249.99: $1.00 increments
        - $250.00 - $499.99: $2.50 increments
        - $500.00+: $5.00 increments
        """
        price = float(current_price)
        if price < 1.00:
            return Decimal("0.01")
        elif price < 5.00:
            return Decimal("0.05")
        elif price < 25.00:
            return Decimal("0.25")
        elif price < 100.00:
            return Decimal("0.50")
        elif price < 250.00:
            return Decimal("1.00")
        elif price < 500.00:
            return Decimal("2.50")
        else:
            return Decimal("5.00")
    
    def get_auction_details(self, listing_number: str) -> Dict[str, Any]:
        """
        Fetch auction details including current price, end time, title, URL.
        Uses Application OAuth token (if available) or falls back to User token.
        Tries multiple methods:
        1. Browse API getItemByLegacyId (primary method)
        2. Browse API getItem (fallback to standard endpoint)
        
        Returns dict with:
        - listing_url
        - item_title
        - current_price (Decimal)
        - currency
        - auction_end_time_utc (datetime)
        """
        self._ensure_token_valid(use_user_token=False)  # Use App token for reading
        
        # Method 1: Try getItemByLegacyId endpoint (primary method)
        # Note: getItemByLegacyId doesn't support "FULL" fieldgroups, so we omit it
        try:
            url = f"{self.base_url}/buy/browse/v1/item/get_item_by_legacy_id"
            params = {
                "legacy_item_id": listing_number
            }
            
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
                logger.info(f"getItemByLegacyId returned 404 for {listing_number}, trying standard Browse API endpoint...")
                # Continue to fallback method below - don't re-raise
            else:
                # For non-404 HTTP errors, re-raise immediately
                raise
        except requests.exceptions.RequestException:
            # For other request exceptions, re-raise immediately
            raise
        
        # Method 2: Try standard Browse API endpoint (fallback)
        try:
            url = f"{self.base_url}/buy/browse/v1/item/{listing_number}"
            params = {"fieldgroups": "FULL"}
            
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
            logger.error(f"Error in standard Browse API fallback for {listing_number}: {e}")
            raise
    
    def _parse_trading_api_response(self, xml_response: str) -> Dict[str, Any]:
        """
        Parse Trading API XML response and extract error codes/messages.
        
        Returns dict with:
        - success: bool
        - error_code: str or None
        - error_message: str or None
        """
        try:
            root = ET.fromstring(xml_response)
            namespace = "{urn:ebay:apis:eBLBaseComponents}"
            
            # Check Ack element
            ack_elem = root.find(f".//{namespace}Ack")
            ack = ack_elem.text if ack_elem is not None else None
            
            if ack == "Success":
                return {"success": True, "error_code": None, "error_message": None}
            
            # Parse errors
            errors = root.findall(f".//{namespace}Errors")
            error_codes = []
            error_messages = []
            
            for error in errors:
                code_elem = error.find(f".//{namespace}ErrorCode")
                msg_elem = error.find(f".//{namespace}LongMessage")
                
                if code_elem is not None:
                    error_codes.append(code_elem.text)
                if msg_elem is not None:
                    error_messages.append(msg_elem.text)
            
            error_code = error_codes[0] if error_codes else "UNKNOWN"
            error_message = error_messages[0] if error_messages else "Unknown error"
            
            return {
                "success": False,
                "error_code": error_code,
                "error_message": error_message
            }
        except ET.ParseError as e:
            logger.error(f"Failed to parse Trading API XML response: {e}")
            return {
                "success": False,
                "error_code": "PARSE_ERROR",
                "error_message": f"Failed to parse XML response: {e}"
            }
    
    def get_final_price_from_trading_api(self, listing_number: str) -> Optional[Decimal]:
        """
        Get final price for an ended auction using Trading API GetItem.
        This works even if we didn't bid on the auction.
        
        Returns final price as Decimal, or None if not available or auction hasn't ended.
        """
        try:
            self._ensure_token_valid(use_user_token=True)  # Trading API requires User token
            
            # eBay Trading API - GetItem requires XML
            url = f"{self.base_url}/ws/api.dll"
            
            user_token = self.oauth_user_token
            if not user_token:
                logger.warning("User OAuth token not set, cannot get final price from Trading API")
                return None
            
            # Escape XML special characters
            def escape_xml(value):
                return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            # GetItem request to get auction details including current price
            xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{escape_xml(user_token)}</eBayAuthToken>
    </RequesterCredentials>
    <DetailLevel>ReturnAll</DetailLevel>
    <Version>1247</Version>
    <ItemID>{escape_xml(listing_number)}</ItemID>
    <SiteID>0</SiteID>
</GetItemRequest>"""
            
            headers = {
                "X-EBAY-SOA-OPERATION-NAME": "GetItem",
                "X-EBAY-SOA-SERVICE-VERSION": "1247",
                "X-EBAY-SOA-SECURITY-APPNAME": self.app_id,
                "Content-Type": "text/xml",
            }
            
            response = requests.post(url, headers=headers, data=xml_payload, timeout=5)
            
            # Handle 401 errors by attempting token refresh
            if response.status_code == 401:
                logger.warning("Received 401 error getting final price, attempting token refresh...")
                if self.refresh_user_token():
                    user_token = self.oauth_user_token
                    xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{escape_xml(user_token)}</eBayAuthToken>
    </RequesterCredentials>
    <DetailLevel>ReturnAll</DetailLevel>
    <Version>1247</Version>
    <ItemID>{escape_xml(listing_number)}</ItemID>
    <SiteID>0</SiteID>
</GetItemRequest>"""
                    response = requests.post(url, headers=headers, data=xml_payload, timeout=5)
            
            if response.status_code == 404:
                logger.info(f"Listing {listing_number} not found in Trading API")
                return None
            
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.text)
            namespace = "{urn:ebay:apis:eBLBaseComponents}"
            
            # Check for errors
            ack_elem = root.find(f".//{namespace}Ack")
            ack = ack_elem.text if ack_elem is not None else None
            
            if ack != "Success":
                # Check for error messages
                errors = root.findall(f".//{namespace}Errors")
                if errors:
                    error_code_elem = errors[0].find(f".//{namespace}ErrorCode")
                    error_msg_elem = errors[0].find(f".//{namespace}LongMessage")
                    error_code = error_code_elem.text if error_code_elem is not None else "UNKNOWN"
                    error_msg = error_msg_elem.text if error_msg_elem is not None else "Unknown error"
                    logger.warning(f"Trading API GetItem error {error_code}: {error_msg}")
                return None
            
            # Check if auction has ended
            listing_status_elem = root.find(f".//{namespace}ListingStatus")
            listing_status = listing_status_elem.text if listing_status_elem is not None else None
            
            # Get end time
            end_time_elem = root.find(f".//{namespace}EndTime")
            if end_time_elem is not None and end_time_elem.text:
                end_time_str = end_time_elem.text
                # eBay returns time in ISO format like "2025-12-25T12:00:00.000Z"
                end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).replace(tzinfo=None)
                now = datetime.utcnow()
                if now < end_time:
                    # Auction hasn't ended yet
                    return None
            
            # Get current price (which should be final price if auction ended)
            # Look for CurrentPrice element
            current_price_elem = root.find(f".//{namespace}CurrentPrice")
            if current_price_elem is not None:
                price_value = current_price_elem.text
                if price_value:
                    return Decimal(str(price_value))
            
            # Fallback: try SellingStatus/CurrentPrice
            selling_status = root.find(f".//{namespace}SellingStatus")
            if selling_status is not None:
                current_price_elem = selling_status.find(f".//{namespace}CurrentPrice")
                if current_price_elem is not None:
                    price_value = current_price_elem.text
                    if price_value:
                        return Decimal(str(price_value))
            
            logger.warning(f"Could not find current price in Trading API response for {listing_number}")
            return None
            
        except ET.ParseError as e:
            logger.warning(f"Failed to parse Trading API XML response for {listing_number}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Could not get final price from Trading API for {listing_number}: {e}")
            return None
    
    def place_bid(self, listing_number: str, bid_amount: Decimal) -> Dict[str, Any]:
        """
        Place a bid on an auction.
        
        eBay Trading API requires XML format. Includes SiteID and proper error handling.
        
        Returns dict with result information.
        """
        try:
            self._ensure_token_valid(use_user_token=True)  # Must use User token for bidding
            
            # eBay Trading API - PlaceOffer requires XML
            url = f"{self.base_url}/ws/api.dll"
            
            # Use User token for Trading API
            user_token = self.oauth_user_token
            if not user_token:
                raise ValueError("User OAuth token required for placing bids. Set EBAY_OAUTH_TOKEN.")
            
            # Construct XML payload with SiteID (0 = US site)
            # Escape XML special characters in values
            def escape_xml(value):
                return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            # Version 1247 is the current Trading API version (as of 2024)
            # DetailLevel and Version are required elements for Trading API
            xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<PlaceOfferRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{escape_xml(user_token)}</eBayAuthToken>
    </RequesterCredentials>
    <DetailLevel>ReturnAll</DetailLevel>
    <Version>1247</Version>
    <ItemID>{escape_xml(listing_number)}</ItemID>
    <Offer>
        <MaxBid>{float(bid_amount)}</MaxBid>
        <Quantity>1</Quantity>
    </Offer>
    <SiteID>0</SiteID>
</PlaceOfferRequest>"""
            
            headers = {
                "X-EBAY-SOA-OPERATION-NAME": "PlaceOffer",
                "X-EBAY-SOA-SERVICE-VERSION": "1247",
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
        <eBayAuthToken>{escape_xml(user_token)}</eBayAuthToken>
    </RequesterCredentials>
    <DetailLevel>ReturnAll</DetailLevel>
    <Version>1247</Version>
    <ItemID>{escape_xml(listing_number)}</ItemID>
    <Offer>
        <MaxBid>{float(bid_amount)}</MaxBid>
        <Quantity>1</Quantity>
    </Offer>
    <SiteID>0</SiteID>
</PlaceOfferRequest>"""
                    response = requests.post(url, headers=headers, data=xml_payload, timeout=0.6)
                    status_code = response.status_code
            
            if status_code in [500, 502, 503, 504]:
                raise requests.exceptions.RequestException(f"eBay server error: {status_code}")
            
            if status_code == 429:
                # Check for Retry-After header
                retry_after = response.headers.get("Retry-After")
                error_msg = "Rate limited (429)"
                if retry_after:
                    error_msg += f" - Retry after {retry_after} seconds"
                raise requests.exceptions.RequestException(error_msg)
            
            response.raise_for_status()
            
            # Parse XML response properly
            result = self._parse_trading_api_response(response.text)
            
            if not result["success"]:
                error_code = result["error_code"]
                error_message = result["error_message"]
                
                # Map common error codes to user-friendly messages
                error_code_messages = {
                    "10729": "Item not found or auction ended",
                    "10734": "Auction has ended",
                    "10736": "Bid amount is below the minimum bid increment",
                    "10735": "Bid amount exceeds maximum bid",
                    "10730": "Bid retraction not allowed",
                    "10731": "Cannot bid on your own item",
                    "10732": "Cannot bid on behalf of another user",
                    "10733": "Bidder is blocked from this auction",
                }
                
                friendly_msg = error_code_messages.get(error_code, error_message)
                raise requests.exceptions.RequestException(
                    f"eBay API error {error_code}: {friendly_msg}"
                )
            
            return {"success": True}
            
        except requests.exceptions.Timeout:
            raise
        except requests.exceptions.RequestException as e:
            # Re-raise to trigger retry logic in worker
            raise
        except Exception as e:
            logger.error(f"Unexpected error placing bid: {e}")
            raise
    
    def get_final_price_from_browse_api(self, listing_number: str) -> Optional[Decimal]:
        """
        Get final price for an ended auction using Browse API.
        This works even if we didn't bid on the auction.
        
        Returns final price as Decimal, or None if not available or auction hasn't ended.
        """
        try:
            self._ensure_token_valid(use_user_token=False)  # Browse API can use app token
            
            # Try getItemByLegacyId first (more reliable for ended auctions)
            url = f"{self.base_url}/buy/browse/v1/item/get_item_by_legacy_id"
            params = {
                "legacy_item_id": listing_number,
                "fieldgroups": "FULL"
            }
            
            headers = self._get_headers(use_user_token=False)
            if self.marketplace_id:
                headers["X-EBAY-C-MARKETPLACE-ID"] = self.marketplace_id
            
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 404:
                # Try standard Browse API endpoint as fallback
                url = f"{self.base_url}/buy/browse/v1/item/{listing_number}"
                params = {"fieldgroups": "FULL"}
                response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 404:
                logger.info(f"Listing {listing_number} not found in Browse API")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # Check if auction has ended
            item_end_date = data.get("itemEndDate")
            if item_end_date:
                # Parse end date and check if auction has ended
                # Use same pattern as _parse_browse_api_response - convert to naive UTC
                end_time = datetime.fromisoformat(item_end_date.replace("Z", "+00:00")).replace(tzinfo=None)
                now = datetime.utcnow()
                if now < end_time:
                    # Auction hasn't ended yet
                    return None
            
            # Get current price (which should be final price if auction ended)
            price_info = data.get("price", {})
            if price_info:
                value = price_info.get("value")
                if value:
                    return Decimal(str(value))
            
            # Try priceDisplay field as fallback
            price_display = data.get("priceDisplay")
            if price_display:
                # Extract numeric value from display string like "$150.00"
                import re
                match = re.search(r'[\d.]+', price_display.replace(',', ''))
                if match:
                    return Decimal(match.group())
            
            return None
            
        except Exception as e:
            logger.warning(f"Could not get final price from Browse API for {listing_number}: {e}")
            return None
    
    def get_auction_outcome(self, listing_number: str) -> Dict[str, Any]:
        """
        Check auction outcome using Offer API getBidding endpoint.
        
        Returns dict with:
        - outcome: "Won", "Lost", or "Pending" (if auction hasn't ended)
        - final_price: Final winning bid amount (None if pending)
        - auction_status: eBay's auction status (e.g., "ENDED", "ACTIVE")
        """
        try:
            self._ensure_token_valid(use_user_token=True)  # Need User token for Offer API
            
            # Offer API getBidding endpoint
            url = f"{self.base_url}/buy/offer/v1/bidding/{listing_number}"
            
            headers = self._get_headers(use_user_token=True)
            # Offer API requires marketplace ID header
            if self.marketplace_id:
                headers["X-EBAY-C-MARKETPLACE-ID"] = self.marketplace_id
            
            response = requests.get(url, headers=headers, timeout=5)
            
            # Handle 401 errors by attempting token refresh
            if response.status_code == 401:
                logger.warning("Received 401 error checking auction outcome, attempting token refresh...")
                if self.refresh_user_token():
                    headers = self._get_headers(use_user_token=True)
                    if self.marketplace_id:
                        headers["X-EBAY-C-MARKETPLACE-ID"] = self.marketplace_id
                    response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 404:
                # Auction not found or user didn't bid on it
                return {
                    "outcome": "Pending",
                    "final_price": None,
                    "auction_status": "UNKNOWN"
                }
            
            response.raise_for_status()
            data = response.json()
            
            # Parse response
            auction_status = data.get("auctionStatus", "UNKNOWN")
            is_high_bidder = data.get("highBidder", False)
            current_price = data.get("currentPrice", {})
            final_price_value = current_price.get("value") if current_price else None
            
            # Determine outcome
            if auction_status == "ENDED":
                if is_high_bidder:
                    outcome = "Won"
                else:
                    outcome = "Lost"
                final_price = Decimal(str(final_price_value)) if final_price_value else None
            else:
                # Auction still active
                outcome = "Pending"
                final_price = None
            
            return {
                "outcome": outcome,
                "final_price": final_price,
                "auction_status": auction_status
            }
            
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                # User didn't bid on this auction or it doesn't exist
                logger.info(f"Could not find bidding info for auction {listing_number}")
                return {
                    "outcome": "Pending",
                    "final_price": None,
                    "auction_status": "UNKNOWN"
                }
            logger.error(f"Error checking auction outcome for {listing_number}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error checking auction outcome: {e}")
            raise

