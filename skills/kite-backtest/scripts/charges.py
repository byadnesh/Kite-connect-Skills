#!/usr/bin/env python3
"""Offline Zerodha charges model for backtests and P&L estimates.

UNOFFICIAL — not affiliated with Zerodha. Pure standard library.

Rates are a snapshot of https://zerodha.com/charges (checked Oct 2026). Statutory
levies change with budgets/exchange circulars — update RATES when they do. For
real executed orders prefer kite.get_virtual_contract_note(), which is exact.

    >>> c = trade_charges("intraday", buy_value=100000, sell_value=100500)
    >>> c["brokerage"]
    40.0
"""

from __future__ import annotations

import sys
SEGMENTS = ("delivery", "intraday", "futures", "options")

RATES = {
    #              brokerage               stt (side, rate)         stamp (buy)  txn NSE      txn BSE
    "delivery": {"brok_pct": 0.0, "brok_cap": 0.0, "stt": ("both", 0.001), "stamp": 0.00015,
                 "txn": {"NSE": 0.0000307, "BSE": 0.0000375}},
    "intraday": {"brok_pct": 0.0003, "brok_cap": 20.0, "stt": ("sell", 0.00025), "stamp": 0.00003,
                 "txn": {"NSE": 0.0000307, "BSE": 0.0000375}},
    "futures": {"brok_pct": 0.0003, "brok_cap": 20.0, "stt": ("sell", 0.0005), "stamp": 0.00002,
                "txn": {"NSE": 0.0000183, "BSE": 0.0}},
    "options": {"brok_flat": 20.0, "stt": ("sell", 0.0015), "stamp": 0.00003,
                "txn": {"NSE": 0.0003553, "BSE": 0.000325}},
}
SEBI_RATE = 10 / 1e7          # ₹10 per crore
GST_RATE = 0.18
DP_CHARGE = 15.34             # per scrip per day with a delivery sell (incl. GST)


def _brokerage(seg: str, value: float, orders: int) -> float:
    r = RATES[seg]
    if not value or not orders:
        return 0.0
    if "brok_flat" in r:
        return r["brok_flat"] * orders
    if r["brok_cap"] == 0.0:
        return 0.0
    per_order_value = value / orders
    return min(per_order_value * r["brok_pct"], r["brok_cap"]) * orders


def trade_charges(segment: str, buy_value: float = 0.0, sell_value: float = 0.0, exchange: str = "NSE",
                  buy_orders: int = 1, sell_orders: int = 1, include_dp: bool = True) -> dict[str, float]:
    """Charges for one round trip (or one side, pass the other value as 0).

    For options, values are **premium** turnover (price × quantity).
    Returns each component and `total` in ₹, rounded to paise.
    """
    seg = segment.lower()
    if seg not in RATES:
        raise ValueError(f"segment must be one of {SEGMENTS}")
    r = RATES[seg]
    exchange = exchange.upper()
    turnover = buy_value + sell_value

    brokerage = _brokerage(seg, buy_value, buy_orders if buy_value else 0) + \
        _brokerage(seg, sell_value, sell_orders if sell_value else 0)
    side, stt_rate = r["stt"]
    stt = stt_rate * (turnover if side == "both" else sell_value)
    txn = r["txn"].get(exchange, r["txn"]["NSE"]) * turnover
    sebi = SEBI_RATE * turnover
    stamp = r["stamp"] * buy_value
    gst = GST_RATE * (brokerage + txn + sebi)
    dp = DP_CHARGE if (seg == "delivery" and sell_value and include_dp) else 0.0

    out = {"brokerage": brokerage, "stt": stt, "exchange_txn": txn, "sebi": sebi, "stamp_duty": stamp,
           "gst": gst, "dp": dp}
    out = {k: round(v, 2) for k, v in out.items()}
    out["total"] = round(sum(out.values()), 2)
    out["turnover"] = round(turnover, 2)
    return out


def breakeven_move(segment: str, price: float, quantity: int, exchange: str = "NSE") -> float:
    """Points the price must move for a round trip to break even after charges."""
    v = price * quantity
    c = trade_charges(segment, v, v, exchange)["total"]
    return c / quantity


def stt_on_exercise(intrinsic_value_total: float) -> float:
    """STT charged when a long option expires ITM and is auto-exercised (0.15 % of intrinsic)."""
    return round(0.0015 * intrinsic_value_total, 2)


if __name__ == "__main__":
    import doctest

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    doctest.testmod()
    for seg, px, q in (("delivery", 1500, 100), ("intraday", 1500, 100), ("futures", 25000, 75),
                       ("options", 120, 75)):
        v = px * q
        c = trade_charges(seg, v, v * 1.01)
        print(f"{seg:<9} turnover ₹{c['turnover']:>12,.0f}  charges ₹{c['total']:>9,.2f}  "
              f"breakeven {breakeven_move(seg, px, q):.2f} pts")
