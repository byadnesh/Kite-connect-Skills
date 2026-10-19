#!/usr/bin/env python3
"""Interactive Kite Connect login -> daily access token.

UNOFFICIAL — not affiliated with Zerodha.

The user logs in themselves in the browser (password + 2FA). This script never
sees or asks for the Zerodha password, PIN or TOTP.

Two modes:

  Local callback (recommended)
    Set your app's Redirect URL in https://developers.kite.trade to
    http://127.0.0.1:5678/kite/callback  (or pass --port). Then:
        python scripts/login.py

  Paste mode (any redirect URL)
        python scripts/login.py --paste
    Log in, copy the full URL you were redirected to (it contains
    request_token=...), paste it back here.

Needs KITE_API_KEY and KITE_API_SECRET in the environment.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.kite_client import mask, save_session  # noqa: E402


def extract_request_token(url_or_token: str) -> str | None:
    text = url_or_token.strip()
    if "request_token=" not in text:
        return text or None
    qs = parse_qs(urlparse(text).query)
    if qs.get("status", ["success"])[0] != "success":
        return None
    return qs.get("request_token", [None])[0]


def wait_for_callback(port: int) -> str | None:
    captured: dict[str, str | None] = {"token": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            token = extract_request_token(f"http://127.0.0.1{self.path}")
            captured["token"] = token
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Login captured. You can close this tab." if token else "Login failed or was cancelled."
            self.wfile.write(f"<h3>{msg}</h3>".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 300
    server.handle_request()
    server.server_close()
    return captured["token"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Kite Connect access token")
    parser.add_argument("--paste", action="store_true", help="paste the redirect URL instead of a local callback")
    parser.add_argument("--port", type=int, default=5678)
    parser.add_argument("--no-save", action="store_true", help="print export line only, don't cache the token")
    args = parser.parse_args()

    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key or not api_secret:
        print("Set KITE_API_KEY and KITE_API_SECRET first.", file=sys.stderr)
        return 2

    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=api_key)
    url = kite.login_url()
    print(f"Opening Kite login: {url}")
    webbrowser.open(url)

    if args.paste:
        token = extract_request_token(input("Paste the redirect URL (or request_token): "))
    else:
        print(f"Waiting for redirect on http://127.0.0.1:{args.port}/ (5 min timeout)…")
        token = wait_for_callback(args.port)

    if not token:
        print("No request_token received.", file=sys.stderr)
        return 1

    session = kite.generate_session(token, api_secret=api_secret)
    access_token = session["access_token"]
    print(f"Logged in as {session.get('user_id')} — access token {mask(access_token)}")

    if not args.no_save:
        path = save_session(api_key, session)
        print(f"Cached at {path} (valid until ~06:00 IST tomorrow).")
    print("Or export it for this shell:")
    print("  export KITE_ACCESS_TOKEN=<token>    # bash/zsh")
    print("  $env:KITE_ACCESS_TOKEN='<token>'    # PowerShell")
    if args.no_save:
        print(f"\nToken: {access_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
