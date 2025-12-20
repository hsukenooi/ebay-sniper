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
    
    def __init__(self):
        self.app_id = os.getenv("EBAY_APP_ID")
        self.cert_id = os.getenv("EBAY_CERT_ID")
        self.dev_id = os.getenv("EBAY_DEV_ID")
        self.base_url = self.PRODUCTION_BASE if os.getenv("EBAY_ENV") == "production" else self.SANDBOX_BASE
        # OAuth token can be set via environment variable or set_oauth_token()
        token_from_env = os.getenv("EBAY_OAUTH_TOKEN")
        self.oauth_token: Optional[str] = token_from_env
        self.oauth_token_expires_at: Optional[datetime] = None
        
    def set_oauth_token(self, token: str, expires_in: int):
        """Set OAuth token with expiration."""
        self.oauth_token = token
        self.oauth_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)  # Refresh 5 min early
        
    def _ensure_token_valid(self):
        """Ensure OAuth token is valid, refresh if needed."""
        if not self.oauth_token or (self.oauth_token_expires_at and datetime.utcnow() >= self.oauth_token_expires_at):
            raise ValueError("OAuth token expired or not set. Please authenticate.")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        self._ensure_token_valid()
        return {
            "Authorization": f"Bearer {self.oauth_token}",
            "Content-Type": "application/json",
            "X-EBAY-SOA-SECURITY-APPNAME": self.app_id,
        }
    
    def get_auction_details(self, listing_number: str) -> Dict[str, Any]:
        """
        Fetch auction details including current price, end time, title, URL.
        
        Returns dict with:
        - listing_url
        - item_title
        - current_price (Decimal)
        - currency
        - auction_end_time_utc (datetime)
        """
        try:
            self._ensure_token_valid()
            
            # eBay Browse API - Get Item
            url = f"{self.base_url}/buy/browse/v1/item/{listing_number}"
            params = {
                "fieldgroups": "FULL"
            }
            
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
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
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching auction details for {listing_number}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching auction details: {e}")
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

