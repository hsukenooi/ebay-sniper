import os
import json
from pathlib import Path
from typing import Optional

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
    """Get user timezone from config."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
        return config.get("timezone", "UTC")
    return "UTC"


def save_timezone(timezone: str):
    """Save user timezone."""
    ensure_config_dir()
    config = {}
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
    config["timezone"] = timezone
    CONFIG_FILE.write_text(json.dumps(config, indent=2))

