"""
OAuth2 Setup Script for YouTube API

This script handles the initial OAuth2 authentication flow.
Run this once to generate the refresh token, then use the token
for automated streaming.
"""

import os
import sys
import json
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]


def create_client_secrets_file(client_id: str, client_secret: str, output_path: str):
    """Create a client_secrets.json file for OAuth flow."""
    secrets = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/", "urn:ietf:wg:oauth:2.0:oob"]
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(secrets, f, indent=2)
    
    return output_path


def run_oauth_flow(client_id: str, client_secret: str, token_output: str):
    """
    Run the OAuth2 flow to get credentials.
    
    Args:
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret
        token_output: Path to save the token file
    """
    print("=" * 60)
    print("YouTube OAuth2 Setup")
    print("=" * 60)
    print()
    
    # Create temporary client secrets file
    secrets_path = "/tmp/client_secrets.json"
    create_client_secrets_file(client_id, client_secret, secrets_path)
    
    try:
        # Run OAuth flow
        print("Starting OAuth flow...")
        print("A browser window will open for authentication.")
        print("If it doesn't open automatically, follow the URL printed below.")
        print()
        
        flow = InstalledAppFlow.from_client_secrets_file(
            secrets_path,
            scopes=SCOPES
        )
        
        # Try to use local server first, fall back to console if fails
        try:
            credentials = flow.run_local_server(
                port=8080,
                prompt="consent",
                authorization_prompt_message="Opening browser for authorization..."
            )
        except Exception as e:
            print(f"Local server failed: {e}")
            print("Falling back to console-based flow...")
            credentials = flow.run_console()
        
        # Save credentials
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes)
        }
        
        os.makedirs(os.path.dirname(token_output) if os.path.dirname(token_output) else ".", exist_ok=True)
        with open(token_output, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print()
        print("=" * 60)
        print("SUCCESS! OAuth setup complete.")
        print("=" * 60)
        print()
        print(f"Token saved to: {token_output}")
        print()
        print("Your refresh token (save this!):")
        print("-" * 60)
        print(credentials.refresh_token)
        print("-" * 60)
        print()
        print("You can now set YOUTUBE_REFRESH_TOKEN in your .env file")
        print("or mount the token file to /app/data/token.json")
        print()
        
        return True
        
    except Exception as e:
        print(f"OAuth flow failed: {e}")
        return False
        
    finally:
        # Clean up secrets file
        if os.path.exists(secrets_path):
            os.remove(secrets_path)


def refresh_existing_token(token_path: str):
    """
    Refresh an existing token and display info.
    
    Args:
        token_path: Path to existing token file
    """
    print("=" * 60)
    print("Refreshing Existing Token")
    print("=" * 60)
    print()
    
    if not os.path.exists(token_path):
        print(f"Token file not found: {token_path}")
        return False
    
    with open(token_path, 'r') as f:
        token_data = json.load(f)
    
    credentials = Credentials(
        token=token_data.get('token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=token_data.get('client_id'),
        client_secret=token_data.get('client_secret'),
        scopes=token_data.get('scopes', SCOPES)
    )
    
    if credentials.expired or not credentials.valid:
        print("Token is expired, refreshing...")
        credentials.refresh(Request())
        
        # Save updated token
        token_data['token'] = credentials.token
        with open(token_path, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print("Token refreshed successfully!")
    else:
        print("Token is still valid.")
    
    print()
    print(f"Access Token: {credentials.token[:20]}...")
    print(f"Refresh Token: {credentials.refresh_token[:20]}...")
    print()
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="YouTube OAuth2 Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initial setup with client credentials
  python oauth_setup.py --client-id YOUR_ID --client-secret YOUR_SECRET
  
  # Refresh existing token
  python oauth_setup.py --refresh --token-path ./data/token.json
  
  # Use environment variables
  export YOUTUBE_CLIENT_ID=your_id
  export YOUTUBE_CLIENT_SECRET=your_secret
  python oauth_setup.py
"""
    )
    
    parser.add_argument(
        "--client-id",
        default=os.getenv("YOUTUBE_CLIENT_ID"),
        help="Google OAuth Client ID (or set YOUTUBE_CLIENT_ID env var)"
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("YOUTUBE_CLIENT_SECRET"),
        help="Google OAuth Client Secret (or set YOUTUBE_CLIENT_SECRET env var)"
    )
    parser.add_argument(
        "--token-path",
        default="./data/token.json",
        help="Path to save/load token file (default: ./data/token.json)"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh existing token instead of running new OAuth flow"
    )
    
    args = parser.parse_args()
    
    if args.refresh:
        success = refresh_existing_token(args.token_path)
    else:
        if not args.client_id or not args.client_secret:
            print("Error: --client-id and --client-secret are required")
            print("       (or set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET env vars)")
            parser.print_help()
            sys.exit(1)
        
        success = run_oauth_flow(args.client_id, args.client_secret, args.token_path)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
