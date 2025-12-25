import requests
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import math
import pytz
from .config import SERVER_URL, get_token, get_timezone


class SniperClient:
    """Client for communicating with the sniper server."""
    
    def __init__(self):
        self.server_url = SERVER_URL
        self.token: Optional[str] = get_token()
        self.timezone = pytz.timezone(get_timezone())
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication."""
        if not self.token:
            raise ValueError("Not authenticated. Run 'sniper auth' first.")
        return {"Authorization": f"Bearer {self.token}"}
    
    def authenticate(self, username: str, password: str) -> str:
        """Authenticate and return token."""
        response = requests.post(
            f"{self.server_url}/auth",
            json={"username": username, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["token"]
        return self.token
    
    def add_sniper(self, listing_number: str, max_bid: Decimal) -> Dict[str, Any]:
        """Add a new listing."""
        response = requests.post(
            f"{self.server_url}/sniper/add",
            json={"listing_number": listing_number, "max_bid": float(max_bid)},
            headers=self._get_headers()
        )
        if not response.ok:
            # Try to extract error detail from response
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", response.text)
                raise requests.exceptions.HTTPError(f"{response.status_code} {response.reason}: {error_msg}")
            except (ValueError, KeyError):
                response.raise_for_status()
        return response.json()
    
    def list_snipers(self) -> List[Dict[str, Any]]:
        """List all listings."""
        response = requests.get(
            f"{self.server_url}/sniper/list",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def get_status(self, auction_id: int) -> Dict[str, Any]:
        """Get status of a listing."""
        response = requests.get(
            f"{self.server_url}/sniper/{auction_id}/status",
            headers=self._get_headers()
        )
        if not response.ok:
            # Try to extract error detail from response
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", response.text)
                raise requests.exceptions.HTTPError(f"{response.status_code} {response.reason}: {error_msg}")
            except (ValueError, KeyError):
                response.raise_for_status()
        return response.json()
    
    def remove_sniper(self, auction_id: int):
        """Remove a listing."""
        response = requests.delete(
            f"{self.server_url}/sniper/{auction_id}",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def get_logs(self, auction_id: int) -> Optional[Dict[str, Any]]:
        """Get bid attempt logs."""
        response = requests.get(
            f"{self.server_url}/sniper/{auction_id}/logs",
            headers=self._get_headers()
        )
        response.raise_for_status()
        data = response.json()
        return data if data else None
    
    def to_local_time(self, utc_time_str: str) -> str:
        """Convert UTC time string to local timezone string."""
        # Parse UTC datetime
        dt_utc = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = pytz.UTC.localize(dt_utc)
        
        # Convert to local timezone
        dt_local = dt_utc.astimezone(self.timezone)
        return dt_local.strftime("%Y-%m-%d %H:%M:%S")
    
    def to_local_time_no_seconds(self, utc_time_str: str) -> str:
        """Convert UTC time string to local timezone string without seconds."""
        # Parse UTC datetime
        dt_utc = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = pytz.UTC.localize(dt_utc)
        
        # Convert to local timezone
        dt_local = dt_utc.astimezone(self.timezone)
        return dt_local.strftime("%Y-%m-%d %H:%M")
    
    def to_local_time_no_year(self, utc_time_str: str) -> str:
        """Convert UTC time string to local timezone string without year and seconds."""
        # Parse UTC datetime
        dt_utc = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = pytz.UTC.localize(dt_utc)
        
        # Convert to local timezone
        dt_local = dt_utc.astimezone(self.timezone)
        return dt_local.strftime("%m-%d %H:%M")
    
    def time_until_auction_end(self, auction_end_time_utc: str) -> str:
        """Calculate and format time remaining until auction ends.
        
        Returns:
            - Minutes (e.g., "45m") if less than 1 hour remaining
            - Hours (e.g., "5h") if 1-36 hours remaining
            - Days (e.g., "3d") if 36 hours or more remaining
            - "Ended" if the auction has already ended
        """
        # Parse UTC datetime
        dt_end = datetime.fromisoformat(auction_end_time_utc.replace("Z", "+00:00"))
        if dt_end.tzinfo is None:
            dt_end = pytz.UTC.localize(dt_end)
        
        # Get current time in UTC
        now_utc = datetime.now(pytz.UTC)
        
        # Calculate time difference
        time_diff = dt_end - now_utc
        
        # If auction has ended
        if time_diff.total_seconds() <= 0:
            return "Ended"
        
        # Calculate total seconds
        total_seconds = time_diff.total_seconds()
        total_minutes = total_seconds / 60
        total_hours = total_seconds / 3600
        
        # Show minutes if less than 1 hour, hours if 1-36 hours, otherwise show days
        if total_hours < 1:
            minutes = int(total_minutes)
            return f"{minutes}m"
        elif total_hours < 36:
            hours = int(total_hours)
            return f"{hours}h"
        else:
            # Calculate days from total hours, rounding up to nearest day
            # e.g., 36.5 hours = 1.52 days -> 2 days, 48.1 hours = 2.00 days -> 2 days
            days = math.ceil(total_hours / 24)
            return f"{days}d"

