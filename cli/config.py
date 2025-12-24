import os
import json
from pathlib import Path
from typing import Optional
import datetime

CONFIG_DIR = Path.home() / ".ebay-sniper"
CONFIG_FILE = CONFIG_DIR / "config.json"
TOKEN_FILE = CONFIG_DIR / "token.txt"
SERVER_URL = os.getenv("SNIPER_SERVER_URL", "http://localhost:8000")


def ensure_config_dir():
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(exist_ok=True)


def get_token() -> Optional[str]:
    """Get stored API token."""
    ensure_config_dir()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def save_token(token: str):
    """Save API token."""
    ensure_config_dir()
    TOKEN_FILE.write_text(token)


def get_timezone() -> str:
    """Get user timezone from config, or use system local timezone."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
        configured_tz = config.get("timezone")
        if configured_tz:
            return configured_tz
    
    # Use system's local timezone by reading the system timezone file
    try:
        # macOS: /etc/localtime is a symlink to /var/db/timezone/zoneinfo/Asia/Tokyo
        # Linux: /etc/localtime is a symlink to /usr/share/zoneinfo/Europe/London
        localtime_path = Path("/etc/localtime")
        if localtime_path.exists():
            # Resolve the symlink
            real_path = localtime_path.resolve()
            # Extract IANA timezone name from path
            # e.g., /var/db/timezone/zoneinfo/Asia/Tokyo -> Asia/Tokyo
            # e.g., /usr/share/zoneinfo/America/New_York -> America/New_York
            # e.g., /usr/share/zoneinfo.default/Asia/Tokyo -> Asia/Tokyo
            parts = real_path.parts
            # Find the zoneinfo directory (or zoneinfo.default) and get everything after it
            for zoneinfo_name in ["zoneinfo", "zoneinfo.default"]:
                try:
                    zoneinfo_idx = parts.index(zoneinfo_name)
                    tz_name = "/".join(parts[zoneinfo_idx + 1:])
                    if tz_name:
                        return tz_name
                except ValueError:
                    continue
        
        # Alternative: Try using Python's zoneinfo if available (Python 3.9+)
        try:
            from zoneinfo import ZoneInfo
            local_tz = datetime.datetime.now().astimezone().tzinfo
            if isinstance(local_tz, ZoneInfo):
                return local_tz.key
        except (ImportError, AttributeError):
            pass
    except Exception:
        pass
    
    # Ultimate fallback to UTC
    return "UTC"



