#!/usr/bin/env python3
"""Instrument resolution on top of the daily Kite instruments dump.

UNOFFICIAL — not affiliated with Zerodha.

Kite regenerates the dump every morning (~08:30 IST). We cache one JSON file per
exchange per day under ~/.kite-skills/cache so repeated lookups cost no API calls.

Never build F&O tradingsymbols by hand — use these helpers.

CLI:
    python scripts/instruments.py search "hdfc bank"
    python scripts/instruments.py option NIFTY 25000 CE          # nearest expiry
    python scripts/instruments.py expiries BANKNIFTY
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = Path(os.environ.get("KITE_SKILLS_HOME", Path.home() / ".kite-skills")) / "cache"

# Stable index tokens / quote keys (indices are not tradable).
INDEX_TOKENS = {
    "NIFTY 50": 256265,
    "NIFTY BANK": 260105,
    "NIFTY FIN SERVICE": 257801,
    "NIFTY MID SELECT": 288009,
    "INDIA VIX": 264969,
    "SENSEX": 265,
}

# F&O underlying name (as in the dump's `name` column) -> spot quote key
UNDERLYING_SPOT = {
    "NIFTY": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "FINNIFTY": "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NSE:NIFTY MID SELECT",
    "NIFTYNXT50": "NSE:NIFTY NEXT 50",
    "SENSEX": "BSE:SENSEX",
    "BANKEX": "BSE:BANKEX",
}

BSE_DERIVATIVE_UNDERLYINGS = {"SENSEX", "BANKEX", "SENSEX50"}

_memory: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _today_ist() -> date:
    return datetime.now(IST).date()


def _to_jsonable(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if isinstance(out.get("expiry"), date):
        out["expiry"] = out["expiry"].isoformat()
    return out


def _from_jsonable(row: dict[str, Any]) -> dict[str, Any]:
    exp = row.get("expiry")
    row["expiry"] = date.fromisoformat(exp) if isinstance(exp, str) and len(exp) == 10 else None
    return row


def load_instruments(kite, exchange: str = "NSE", refresh: bool = False) -> list[dict[str, Any]]:
    """Return the instruments dump for one exchange (cached per IST day)."""
    exchange = exchange.upper()
    key = (exchange, _today_ist().isoformat())
    if not refresh and key in _memory:
        return _memory[key]

    path = CACHE_DIR / f"instruments_{exchange}_{key[1]}.json"
    if not refresh and path.exists():
        rows = [_from_jsonable(r) for r in json.loads(path.read_text(encoding="utf-8"))]
    else:
        rows = kite.instruments(exchange)
        for r in rows:
            if not isinstance(r.get("expiry"), date):
                r["expiry"] = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([_to_jsonable(r) for r in rows]), encoding="utf-8")
        for old in CACHE_DIR.glob(f"instruments_{exchange}_*.json"):
            if old != path:
                old.unlink(missing_ok=True)
    _memory[key] = rows
    return rows


def derivative_exchange(underlying: str) -> str:
    return "BFO" if underlying.upper() in BSE_DERIVATIVE_UNDERLYINGS else "NFO"


def _one(rows: Iterable[dict[str, Any]], what: str) -> dict[str, Any]:
    rows = list(rows)
    if not rows:
        raise LookupError(f"No instrument found for {what}")
    if len(rows) > 1:
        syms = ", ".join(r["tradingsymbol"] for r in rows[:5])
        raise LookupError(f"Ambiguous {what}: {syms}{'…' if len(rows) > 5 else ''}")
    return rows[0]


def find_equity(kite, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    """Exact cash-market match by tradingsymbol (e.g. 'RELIANCE', 'M&M')."""
    symbol = symbol.upper().strip()
    rows = load_instruments(kite, exchange)
    return _one(
        (r for r in rows if r["tradingsymbol"] == symbol and r["segment"] in (exchange, "INDICES")),
        f"{exchange}:{symbol}",
    )


def search(kite, query: str, exchange: str = "NSE", limit: int = 10) -> list[dict[str, Any]]:
    """Fuzzy search by tradingsymbol or company name (case-insensitive substring, all words)."""
    words = query.upper().split()
    rows = load_instruments(kite, exchange)
    hits = [
        r for r in rows
        if all(w in f"{r['tradingsymbol']} {r.get('name') or ''}".upper() for w in words)
    ]
    hits.sort(key=lambda r: (r["tradingsymbol"] != query.upper(), len(r["tradingsymbol"])))
    return hits[:limit]


def _derivatives(kite, underlying: str, exchange: str | None, instrument_type: str | Iterable[str]):
    underlying = underlying.upper()
    exchange = (exchange or derivative_exchange(underlying)).upper()
    types = {instrument_type} if isinstance(instrument_type, str) else set(instrument_type)
    today = _today_ist()
    return [
        r for r in load_instruments(kite, exchange)
        if r.get("name") == underlying and r["instrument_type"] in types
        and r["expiry"] and r["expiry"] >= today
    ]


def list_expiries(kite, underlying: str, exchange: str | None = None, kind: str = "options") -> list[date]:
    """Sorted upcoming expiries. kind: 'options' or 'futures'."""
    types = ("CE", "PE") if kind == "options" else ("FUT",)
    return sorted({r["expiry"] for r in _derivatives(kite, underlying, exchange, types)})


def find_future(kite, underlying: str, expiry: date | None = None, exchange: str | None = None) -> dict[str, Any]:
    futs = _derivatives(kite, underlying, exchange, "FUT")
    if not futs:
        raise LookupError(f"No live futures for {underlying}")
    if expiry is None:
        expiry = min(r["expiry"] for r in futs)
    return _one((r for r in futs if r["expiry"] == expiry), f"{underlying} FUT {expiry}")


def find_option(kite, underlying: str, expiry: date | None, strike: float, option_type: str,
                exchange: str | None = None) -> dict[str, Any]:
    """Resolve one option contract. expiry=None picks the nearest expiry."""
    option_type = option_type.upper()
    opts = _derivatives(kite, underlying, exchange, option_type)
    if not opts:
        raise LookupError(f"No live {option_type} options for {underlying}")
    if expiry is None:
        expiry = min(r["expiry"] for r in opts)
    matches = [r for r in opts if r["expiry"] == expiry and abs(r["strike"] - float(strike)) < 1e-6]
    if not matches:
        strikes = sorted({r["strike"] for r in opts if r["expiry"] == expiry})
        nearest = min(strikes, key=lambda s: abs(s - float(strike))) if strikes else None
        raise LookupError(f"{underlying} {expiry} {strike}{option_type} not listed; nearest strike {nearest}")
    return _one(matches, f"{underlying} {expiry} {strike}{option_type}")


def option_strikes(kite, underlying: str, expiry: date, exchange: str | None = None) -> list[float]:
    return sorted({r["strike"] for r in _derivatives(kite, underlying, exchange, ("CE", "PE")) if r["expiry"] == expiry})


def quote_key(inst: dict[str, Any]) -> str:
    """'EXCHANGE:TRADINGSYMBOL' key for ltp/ohlc/quote."""
    return f"{inst['exchange']}:{inst['tradingsymbol']}"


def _print(rows):
    for r in rows:
        exp = r["expiry"].isoformat() if r.get("expiry") else ""
        print(f"{r['exchange']:4} {r['tradingsymbol']:28} token={r['instrument_token']:<9} "
              f"lot={r['lot_size']:<5} tick={r['tick_size']:<5} {r['instrument_type']:3} {exp} {r.get('name') or ''}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.kite_client import get_client

    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    k = get_client()
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "search":
        _print(search(k, " ".join(args)))
    elif cmd == "expiries":
        print([d.isoformat() for d in list_expiries(k, args[0])])
    elif cmd == "option":
        _print([find_option(k, args[0], None, float(args[1]), args[2])])
    elif cmd == "future":
        _print([find_future(k, args[0])])
    else:
        print(__doc__)
