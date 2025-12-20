import requests
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
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
        """Add a new sniper."""
        response = requests.post(
            f"{self.server_url}/sniper/add",
            json={"listing_number": listing_number, "max_bid": float(max_bid)},
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def list_snipers(self) -> List[Dict[str, Any]]:
        """List all snipers."""
        response = requests.get(
            f"{self.server_url}/sniper/list",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def get_status(self, auction_id: int) -> Dict[str, Any]:
        """Get status of a sniper."""
        response = requests.get(
            f"{self.server_url}/sniper/{auction_id}/status",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def remove_sniper(self, auction_id: int):
        """Remove a sniper."""
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

