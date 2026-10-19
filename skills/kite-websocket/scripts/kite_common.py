"""Minimal Kite bootstrap shared by the kite-options, kite-backtest and kite-websocket skills.

UNOFFICIAL — not affiliated with Zerodha.

This file is intentionally duplicated (byte-identical) in each skill so every
skill installs and runs on its own. CI checks the copies stay in sync. The full
helper set lives in the kite-connect skill.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
HOME = Path(os.environ.get("KITE_SKILLS_HOME", Path.home() / ".kite-skills"))

# F&O underlying (dump `name`) -> spot quote key
UNDERLYING_SPOT = {
    "NIFTY": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "FINNIFTY": "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NSE:NIFTY MID SELECT",
    "NIFTYNXT50": "NSE:NIFTY NEXT 50",
    "SENSEX": "BSE:SENSEX",
    "BANKEX": "BSE:BANKEX",
}
BSE_DERIVATIVES = {"SENSEX", "BANKEX", "SENSEX50"}


def today_ist() -> date:
    return datetime.now(IST).date()


def get_client():
    """Authenticated KiteConnect from KITE_API_KEY + KITE_ACCESS_TOKEN (or the kite-connect login cache)."""
    from kiteconnect import KiteConnect

    api_key = os.environ.get("KITE_API_KEY")
    token = os.environ.get("KITE_ACCESS_TOKEN")
    session = HOME / "session.json"
    if not token and session.exists():
        data = json.loads(session.read_text(encoding="utf-8"))
        now = datetime.now(IST)
        cutoff = datetime.combine(now.date(), time(6, 0), IST)
        if now < cutoff:
            cutoff -= timedelta(days=1)
        if datetime.fromisoformat(data["created_at"]) >= cutoff:
            token = data["access_token"]
            api_key = api_key or data.get("api_key")
    if not api_key or not token:
        raise RuntimeError("Set KITE_API_KEY and KITE_ACCESS_TOKEN (or run kite-connect/scripts/login.py).")
    kite = KiteConnect(api_key=api_key, timeout=10)
    kite.set_access_token(token)
    return kite


def load_instruments(kite, exchange: str) -> list[dict[str, Any]]:
    """Instruments dump for one exchange, cached per IST day (same cache as kite-connect)."""
    exchange = exchange.upper()
    cache = HOME / "cache" / f"instruments_{exchange}_{today_ist().isoformat()}.json"
    if cache.exists():
        rows = json.loads(cache.read_text(encoding="utf-8"))
        for r in rows:
            e = r.get("expiry")
            r["expiry"] = date.fromisoformat(e) if isinstance(e, str) and len(e) == 10 else None
        return rows
    rows = kite.instruments(exchange)
    for r in rows:
        if not isinstance(r.get("expiry"), date):
            r["expiry"] = None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps([{**r, "expiry": r["expiry"].isoformat() if r["expiry"] else None}
                                 for r in rows]), encoding="utf-8")
    return rows


def derivative_exchange(underlying: str) -> str:
    return "BFO" if underlying.upper() in BSE_DERIVATIVES else "NFO"


def spot_key(underlying: str) -> str:
    u = underlying.upper()
    return UNDERLYING_SPOT.get(u, f"NSE:{u}")


def find_equity_token(kite, symbol: str, exchange: str = "NSE") -> int:
    symbol = symbol.upper()
    for r in load_instruments(kite, exchange):
        if r["tradingsymbol"] == symbol:
            return r["instrument_token"]
    raise LookupError(f"{exchange}:{symbol} not in instruments dump")


def resolve_instrument(kite, spec: str) -> dict[str, Any]:
    """'NSE:INFY', 'INFY' (NSE), 'NFO:NIFTY26OCTFUT', 'BSE:SENSEX' or a numeric token -> instrument row."""
    spec = spec.strip()
    if spec.isdigit():
        token = int(spec)
        for exch in ("NSE", "BSE", "NFO", "BFO", "MCX", "CDS", "BCD"):
            for r in load_instruments(kite, exch):
                if r["instrument_token"] == token:
                    return r
        raise LookupError(f"instrument_token {token} not found")
    exchange, _, symbol = spec.rpartition(":")
    exchange, symbol = (exchange or "NSE").upper(), symbol.upper()
    for r in load_instruments(kite, exchange):
        if r["tradingsymbol"] == symbol:
            return r
    raise LookupError(f"{exchange}:{symbol} not in instruments dump")
