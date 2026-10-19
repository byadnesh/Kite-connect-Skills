"""Small, pure helpers for KiteTicker ticks.

UNOFFICIAL — not affiliated with Zerodha. Standard library only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))


def to_ist(ts: datetime | None) -> datetime | None:
    """Convert a KiteTicker timestamp to aware IST.

    pykiteconnect builds timestamps with `datetime.fromtimestamp()`, i.e. naive datetimes in the
    *host's* local timezone. `astimezone()` on a naive datetime interprets it as host-local, which is
    exactly right; aware datetimes are simply converted.
    """
    if ts is None:
        return None
    return ts.astimezone(IST)


def now_ist() -> datetime:
    return datetime.now(IST)


def tick_time(tick: dict[str, Any], received_at: datetime | None = None) -> datetime:
    """Best available time for a tick: exchange_timestamp → last_trade_time → receive time (IST)."""
    for key in ("exchange_timestamp", "last_trade_time"):
        ts = tick.get(key)
        if isinstance(ts, datetime):
            return to_ist(ts)
    return to_ist(received_at) if received_at else now_ist()


def best_bid_ask(tick: dict[str, Any]) -> tuple[float | None, float | None]:
    """Top-of-book prices from a full-mode tick (None when the side is empty or depth missing)."""
    depth = tick.get("depth") or {}
    buy = depth.get("buy") or []
    sell = depth.get("sell") or []
    bid = buy[0]["price"] if buy and buy[0].get("price") else None
    ask = sell[0]["price"] if sell and sell[0].get("price") else None
    return bid, ask


def mid(tick: dict[str, Any]) -> float | None:
    bid, ask = best_bid_ask(tick)
    if bid and ask:
        return (bid + ask) / 2
    return tick.get("last_price")


def spread_bps(tick: dict[str, Any]) -> float | None:
    bid, ask = best_bid_ask(tick)
    if not (bid and ask):
        return None
    return (ask - bid) / ((ask + bid) / 2) * 10_000


def book_imbalance(tick: dict[str, Any], levels: int = 5) -> float | None:
    """(bid qty − ask qty) / (bid qty + ask qty) over the top `levels`; +1 = all bids, −1 = all asks."""
    depth = tick.get("depth") or {}
    b = sum(level.get("quantity", 0) for level in (depth.get("buy") or [])[:levels])
    a = sum(level.get("quantity", 0) for level in (depth.get("sell") or [])[:levels])
    return (b - a) / (b + a) if (a + b) else None


def flatten(tick: dict[str, Any], received_at: datetime | None = None) -> dict[str, Any]:
    """Compact, JSON-friendly row for logging/recording."""
    bid, ask = best_bid_ask(tick)
    depth = tick.get("depth") or {}
    buy0 = (depth.get("buy") or [{}])[0]
    sell0 = (depth.get("sell") or [{}])[0]
    ts = tick.get("exchange_timestamp")
    return {
        "token": tick.get("instrument_token"),
        "ts": to_ist(ts).isoformat() if isinstance(ts, datetime) else None,
        "recv": to_ist(received_at).isoformat() if received_at else None,
        "ltp": tick.get("last_price"),
        "ltq": tick.get("last_traded_quantity"),
        "atp": tick.get("average_traded_price"),
        "volume": tick.get("volume_traded"),
        "oi": tick.get("oi"),
        "bid": bid,
        "ask": ask,
        "bid_qty": buy0.get("quantity"),
        "ask_qty": sell0.get("quantity"),
        "buy_qty": tick.get("total_buy_quantity"),
        "sell_qty": tick.get("total_sell_quantity"),
    }
