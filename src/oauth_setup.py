"""
OAuth2 Setup Script for YouTube API

This script handles the initial OAuth2 authentication flow.
Run this OUTSIDE Docker on your local machine (with a browser).

Usage:
    pip install google-auth-oauthlib requests
    python oauth_setup.py
"""

import os
import sys
import json
import argparse
import socket
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
import threading
import requests

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to receive OAuth callback."""
    
    def log_message(self, format, *args):
        pass  # Suppress logging
    
    def do_GET(self):
        """Handle the OAuth callback."""
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            response = """
            <html>
            <head><title>Xác thực thành công!</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: green;">✓ Xác thực thành công!</h1>
                <p>Bạn có thể đóng tab này và quay lại terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(response.encode())
        elif 'error' in params:
            self.server.auth_code = None
            self.server.error = params.get('error', ['Unknown'])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            response = f"""
            <html>
            <head><title>Lỗi xác thực</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">✗ Lỗi xác thực</h1>
                <p>{self.server.error}</p>
            </body>
            </html>
            """
            self.wfile.write(response.encode())


def find_free_port():
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def run_local_oauth_flow(client_id: str, client_secret: str, token_output: str):
    """
    Run OAuth2 flow using local HTTP server for callback.
    
    Args:
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret
        token_output: Path to save the token file
    """
    print("=" * 70)
    print("YouTube OAuth2 Setup")
    print("=" * 70)
    print()
    
    # Find a free port
    port = find_free_port()
    redirect_uri = f"http://localhost:{port}/"
    
    # Create local server
    server = HTTPServer(('localhost', port), OAuthCallbackHandler)
    server.auth_code = None
    server.error = None
    server.timeout = 120  # 2 minutes timeout
    
    # Build authorization URL
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"{AUTH_URI}?{urlencode(auth_params)}"
    
    print(f"Đang mở trình duyệt để xác thực...")
    print(f"Nếu trình duyệt không tự động mở, hãy truy cập URL sau:")
    print()
    print(auth_url)
    print()
    
    # Try to open browser
    try:
        webbrowser.open(auth_url)
        print("✓ Đã mở trình duyệt")
    except Exception:
        print("⚠ Không thể mở trình duyệt tự động. Hãy copy URL ở trên.")
    
    print()
    print("Đang chờ xác thực... (timeout: 2 phút)")
    
    # Wait for callback
    server.handle_request()
    
    if server.error:
        print(f"\n✗ Lỗi: {server.error}")
        return False
    
    if not server.auth_code:
        print("\n✗ Không nhận được authorization code")
        return False
    
    print("\n✓ Đã nhận authorization code")
    print("Đang trao đổi lấy access token...")
    
    # Exchange authorization code for tokens
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": server.auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri
    }
    
    try:
        response = requests.post(TOKEN_URI, data=token_data)
        response.raise_for_status()
        tokens = response.json()
    except requests.exceptions.RequestException as e:
        print(f"✗ Lỗi khi lấy token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False
    
    if "error" in tokens:
        print(f"✗ Lỗi từ Google: {tokens.get('error_description', tokens['error'])}")
        return False
    
    # Save tokens
    token_file_data = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": TOKEN_URI,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES
    }
    
    os.makedirs(os.path.dirname(token_output) if os.path.dirname(token_output) else ".", exist_ok=True)
    with open(token_output, 'w') as f:
        json.dump(token_file_data, f, indent=2)
    
    print()
    print("=" * 70)
    print("✓ THÀNH CÔNG! Đã hoàn tất OAuth setup.")
    print("=" * 70)
    print()
    print(f"Token đã lưu tại: {token_output}")
    print()
    print("Refresh Token của bạn:")
    print("-" * 70)
    print(tokens.get("refresh_token"))
    print("-" * 70)
    print()
    print("BƯỚC TIẾP THEO:")
    print("1. Copy file token.json vào thư mục data/ của project")
    print("2. Hoặc set YOUTUBE_REFRESH_TOKEN trong file .env")
    print("3. Chạy: docker compose up -d")
    print()
    
    return True


def refresh_existing_token(token_path: str):
    """Refresh an existing token."""
    print("=" * 70)
    print("Làm mới Token hiện tại")
    print("=" * 70)
    print()
    
    if not os.path.exists(token_path):
        print(f"✗ Không tìm thấy file token: {token_path}")
        return False
    
    with open(token_path, 'r') as f:
        token_data = json.load(f)
    
    refresh_data = {
        "client_id": token_data.get("client_id"),
        "client_secret": token_data.get("client_secret"),
        "refresh_token": token_data.get("refresh_token"),
        "grant_type": "refresh_token"
    }
    
    try:
        response = requests.post(TOKEN_URI, data=refresh_data)
        response.raise_for_status()
        new_tokens = response.json()
    except requests.exceptions.RequestException as e:
        print(f"✗ Lỗi khi làm mới token: {e}")
        return False
    
    # Update token file
    token_data["token"] = new_tokens.get("access_token")
    with open(token_path, 'w') as f:
        json.dump(token_data, f, indent=2)
    
    print("✓ Token đã được làm mới thành công!")
    print()
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="YouTube OAuth2 Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
QUAN TRỌNG: Chạy script này TRÊN MÁY TÍNH CÓ TRÌNH DUYỆT, không trong Docker!

Ví dụ:
  # Cài đặt dependencies (chạy 1 lần)
  pip install google-auth-oauthlib requests
  
  # Setup OAuth
  python src/oauth_setup.py --client-id YOUR_ID --client-secret YOUR_SECRET
  
  # Hoặc dùng biến môi trường
  export YOUTUBE_CLIENT_ID=your_id
  export YOUTUBE_CLIENT_SECRET=your_secret
  python src/oauth_setup.py
  
  # Sau đó copy token vào thư mục data/
  # Rồi chạy: docker compose up -d
"""
    )
    
    parser.add_argument(
        "--client-id",
        default=os.getenv("YOUTUBE_CLIENT_ID"),
        help="Google OAuth Client ID"
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("YOUTUBE_CLIENT_SECRET"),
        help="Google OAuth Client Secret"
    )
    parser.add_argument(
        "--token-path",
        default="./data/token.json",
        help="Đường dẫn lưu file token (mặc định: ./data/token.json)"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Làm mới token hiện tại"
    )
    
    args = parser.parse_args()
    
    if args.refresh:
        success = refresh_existing_token(args.token_path)
    else:
        if not args.client_id or not args.client_secret:
            print("=" * 70)
            print("LỖI: Thiếu thông tin xác thực")
            print("=" * 70)
            print()
            print("Cần có --client-id và --client-secret")
            print("Hoặc set YOUTUBE_CLIENT_ID và YOUTUBE_CLIENT_SECRET")
            print()
            parser.print_help()
            sys.exit(1)
        
        success = run_local_oauth_flow(args.client_id, args.client_secret, args.token_path)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
