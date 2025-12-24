#!/usr/bin/env python3
"""
Helper script to obtain eBay OAuth tokens (access token and refresh token).

This script automates the OAuth authorization code flow to get both:
- User OAuth access token (EBAY_OAUTH_TOKEN)
- User OAuth refresh token (EBAY_OAUTH_REFRESH_TOKEN)

Usage:
    python3 scripts/get_ebay_tokens.py
"""

import requests
import base64
import os
import sys
from urllib.parse import urlencode, parse_qs, urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OAuth endpoints
SANDBOX_AUTH_URL = "https://auth.sandbox.ebay.com/oauth2/authorize"
PRODUCTION_AUTH_URL = "https://auth.ebay.com/oauth2/authorize"
SANDBOX_TOKEN_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
PRODUCTION_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"


def get_authorization_url(app_id: str, redirect_uri: str, env: str = "production") -> str:
    """Generate the authorization URL for user to visit."""
    base_url = PRODUCTION_AUTH_URL if env == "production" else SANDBOX_AUTH_URL
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    return f"{base_url}?{urlencode(params)}"


def exchange_code_for_tokens(
    app_id: str, 
    cert_id: str, 
    redirect_uri: str, 
    auth_code: str,
    env: str = "production"
) -> dict:
    """Exchange authorization code for access and refresh tokens."""
    token_url = PRODUCTION_TOKEN_URL if env == "production" else SANDBOX_TOKEN_URL
    
    # Encode credentials for Basic Auth
    credentials = f"{app_id}:{cert_id}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}"
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri
    }
    
    response = requests.post(token_url, headers=headers, data=data, timeout=10)
    response.raise_for_status()
    
    return response.json()


def extract_code_from_url(url: str) -> str:
    """Extract authorization code from redirect URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    
    if "code" not in params:
        raise ValueError("No 'code' parameter found in URL. Make sure you copied the full redirect URL.")
    
    return params["code"][0]


def main():
    print("=" * 70)
    print("eBay OAuth Token Generator")
    print("=" * 70)
    print()
    
    # Get credentials from environment or prompt
    app_id = os.getenv("EBAY_APP_ID") or input("Enter your eBay App ID (Client ID): ").strip()
    cert_id = os.getenv("EBAY_CERT_ID") or input("Enter your eBay Cert ID (Client Secret): ").strip()
    
    if not app_id or not cert_id:
        print("Error: App ID and Cert ID are required.", file=sys.stderr)
        sys.exit(1)
    
    # Get environment
    env = os.getenv("EBAY_ENV", "production").lower()
    if env not in ["production", "sandbox"]:
        env = input("Environment (production/sandbox) [production]: ").strip().lower() or "production"
    
    # Get redirect URI
    redirect_uri = input("Enter your Redirect URI (RuName): ").strip()
    if not redirect_uri:
        print("Error: Redirect URI is required.", file=sys.stderr)
        sys.exit(1)
    
    print()
    print("=" * 70)
    print("Step 1: Authorize Application")
    print("=" * 70)
    print()
    print("1. Open this URL in your browser:")
    print()
    
    auth_url = get_authorization_url(app_id, redirect_uri, env)
    print(f"   {auth_url}")
    print()
    print("2. Log in and authorize the application")
    print("3. eBay will redirect you to your redirect URI")
    print("4. Copy the ENTIRE redirect URL (including the code parameter)")
    print()
    
    redirect_url = input("Paste the full redirect URL here: ").strip()
    
    if not redirect_url:
        print("Error: Redirect URL is required.", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Extract authorization code
        print()
        print("Extracting authorization code...")
        auth_code = extract_code_from_url(redirect_url)
        
        # Exchange code for tokens
        print("Exchanging authorization code for tokens...")
        token_data = exchange_code_for_tokens(app_id, cert_id, redirect_uri, auth_code, env)
        
        # Extract tokens
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 7200)
        
        print()
        print("=" * 70)
        print("✅ Success! Your tokens:")
        print("=" * 70)
        print()
        print("Access Token (EBAY_OAUTH_TOKEN):")
        print(f"  {access_token}")
        print()
        
        if refresh_token:
            print("Refresh Token (EBAY_OAUTH_REFRESH_TOKEN):")
            print(f"  {refresh_token}")
        else:
            print("⚠️  Warning: No refresh token received. You may need to re-authenticate when the access token expires.")
        
        print()
        print(f"Expires in: {expires_in} seconds ({expires_in // 3600} hours)")
        print()
        
        # Save to .env file?
        save_to_env = input("Save these tokens to your .env file? (y/n) [y]: ").strip().lower()
        if save_to_env != "n":
            env_file = ".env"
            if not os.path.exists(env_file):
                # Try to copy from .env.example if it exists
                if os.path.exists(".env.example"):
                    import shutil
                    shutil.copy(".env.example", env_file)
                    print(f"Created {env_file} from .env.example")
                else:
                    print(f"Creating new {env_file} file")
            
            # Read existing .env file
            env_lines = []
            if os.path.exists(env_file):
                with open(env_file, "r") as f:
                    env_lines = f.readlines()
            
            # Update or add tokens
            updated = False
            new_lines = []
            for line in env_lines:
                if line.startswith("EBAY_OAUTH_TOKEN="):
                    new_lines.append(f"EBAY_OAUTH_TOKEN={access_token}\n")
                    updated = True
                elif line.startswith("EBAY_OAUTH_REFRESH_TOKEN="):
                    if refresh_token:
                        new_lines.append(f"EBAY_OAUTH_REFRESH_TOKEN={refresh_token}\n")
                    updated = True
                else:
                    new_lines.append(line)
            
            # Add tokens if they weren't found
            if not any("EBAY_OAUTH_TOKEN=" in line for line in new_lines):
                new_lines.append(f"\n# eBay OAuth Tokens\n")
                new_lines.append(f"EBAY_OAUTH_TOKEN={access_token}\n")
            if refresh_token and not any("EBAY_OAUTH_REFRESH_TOKEN=" in line for line in new_lines):
                new_lines.append(f"EBAY_OAUTH_REFRESH_TOKEN={refresh_token}\n")
            
            # Write back to file
            with open(env_file, "w") as f:
                f.writelines(new_lines)
            
            print(f"✅ Tokens saved to {env_file}")
        
        print()
        print("=" * 70)
        print("Next Steps:")
        print("=" * 70)
        print("1. Add these tokens to your environment variables")
        print("2. For Railway deployment, add them in Settings → Variables")
        print("3. The system will automatically refresh tokens when they expire")
        print()
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"Response: {error_data}", file=sys.stderr)
            except:
                print(f"Response text: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

