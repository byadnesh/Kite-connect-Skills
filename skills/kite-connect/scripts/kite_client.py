#!/usr/bin/env python3
"""Kite Connect client bootstrap for the kite-connect skill.

UNOFFICIAL — not affiliated with Zerodha.

Credential lookup order for the access token:
  1. KITE_ACCESS_TOKEN environment variable
  2. ~/.kite-skills/session.json written by scripts/login.py (only if created today
     after 06:00 IST, since Kite tokens expire around 06:00 IST every day)

The API key always comes from KITE_API_KEY. The API secret is never needed here.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
SESSION_FILE = Path(os.environ.get("KITE_SKILLS_HOME", Path.home() / ".kite-skills")) / "session.json"
API_ROOT = "https://api.kite.trade"


class KiteSetupError(RuntimeError):
    """Raised when credentials are missing or obviously stale."""


def mask(secret: str | None) -> str:
    """Return a printable, masked version of a token or key."""
    if not secret:
        return "<missing>"
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}…{secret[-4:]}"


def _token_cutoff(now: datetime | None = None) -> datetime:
    """Most recent 06:00 IST — tokens created before this are expired."""
    now = (now or datetime.now(IST)).astimezone(IST)
    cutoff = datetime.combine(now.date(), time(6, 0), IST)
    return cutoff if now >= cutoff else cutoff - timedelta(days=1)


def load_cached_session(now: datetime | None = None) -> dict[str, Any] | None:
    """Return the cached session written by login.py if it is still valid."""
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        created = datetime.fromisoformat(data["created_at"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    if created < _token_cutoff(now):
        return None
    return data


def save_session(api_key: str, session: dict[str, Any]) -> Path:
    """Persist the access token locally with owner-only permissions."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_key": api_key,
        "access_token": session["access_token"],
        "user_id": session.get("user_id"),
        "user_name": session.get("user_name"),
        "created_at": datetime.now(IST).isoformat(),
    }
    SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(SESSION_FILE, 0o600)
    except OSError:
        pass  # Windows: rely on the user profile ACLs
    return SESSION_FILE


def get_credentials() -> tuple[str, str]:
    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")
    if not access_token:
        cached = load_cached_session()
        if cached:
            access_token = cached["access_token"]
            api_key = api_key or cached.get("api_key")
    if not api_key:
        raise KiteSetupError("KITE_API_KEY is not set. Export it from your Kite developer console app.")
    if not access_token:
        raise KiteSetupError(
            "No valid access token. Run `python scripts/login.py` (tokens expire ~06:00 IST daily) "
            "or export KITE_ACCESS_TOKEN."
        )
    return api_key, access_token


def get_client(timeout: int = 10):
    """Return an authenticated KiteConnect instance."""
    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise KiteSetupError("kiteconnect is not installed. Run: pip install --upgrade kiteconnect") from exc

    api_key, access_token = get_credentials()
    kite = KiteConnect(api_key=api_key, timeout=timeout)
    kite.set_access_token(access_token)

    def _expired():
        raise KiteSetupError("Kite session expired or was invalidated. Run `python scripts/login.py` again.")

    kite.set_session_expiry_hook(_expired)
    return kite


def session_summary(kite) -> dict[str, Any]:
    """Small, non-sensitive health check: who is logged in and what is enabled."""
    profile = kite.profile()
    summary = {
        "user_id": profile.get("user_id"),
        "user_name": profile.get("user_name"),
        "broker": profile.get("broker"),
        "exchanges": profile.get("exchanges"),
        "products": profile.get("products"),
        "order_types": profile.get("order_types"),
    }
    try:
        eq = kite.margins("equity")
        summary["equity_available"] = eq.get("net")
    except Exception as exc:  # margins can fail outside trading days; not fatal
        summary["equity_available"] = f"unavailable ({exc})"
    return summary


def alerts_request(kite, method: str, path: str = "", params: dict | None = None) -> Any:
    """Call the Alerts REST API (not wrapped by pykiteconnect).

    method: GET | POST | PUT | DELETE
    path:   "" for /alerts, "/{uuid}", "/{uuid}/history"
    """
    import requests

    url = f"{API_ROOT}/alerts{path}"
    headers = {
        "X-Kite-Version": "3",
        "Authorization": f"token {kite.api_key}:{kite.access_token}",
    }
    method = method.upper()
    if method in ("GET", "DELETE"):
        resp = requests.request(method, url, headers=headers, params=params, timeout=10)
    else:
        resp = requests.request(method, url, headers=headers, data=params, timeout=10)
    body = resp.json()
    if resp.status_code >= 400 or body.get("status") == "error":
        raise RuntimeError(f"Alerts API {resp.status_code}: {body.get('message', body)}")
    return body.get("data")


if __name__ == "__main__":
    k = get_client()
    print(json.dumps(session_summary(k), indent=2, default=str))
