#!/usr/bin/env python3
"""Pre-flight validation for Kite Connect orders.

UNOFFICIAL — not affiliated with Zerodha.

Pure standard library — no API calls. Pass the instrument row from
scripts/instruments.py (for lot_size / tick_size) and the current LTP when you
have them; the checks get stricter with more context.

    report = validate_order(order, instrument=inst, ltp=ltp)
    report -> {"ok": bool, "errors": [...], "warnings": [...], "notional": float | None}

`ok` is False if there is any error. Warnings must still be shown to the user.

CLI:
    python scripts/validate_order.py '{"exchange":"NSE","tradingsymbol":"INFY", ...}'
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.market_hours import market_status, mis_square_off_warning  # noqa: E402

EXCHANGES = {"NSE", "BSE", "NFO", "BFO", "MCX", "CDS", "BCD"}
CASH_EXCHANGES = {"NSE", "BSE"}
VARIETIES = {"regular", "amo", "iceberg", "auction", "co"}
ORDER_TYPES = {"MARKET", "LIMIT", "SL", "SL-M"}
PRODUCTS = {"CNC", "MIS", "NRML", "MTF", "CO"}
VALIDITIES = {"DAY", "IOC", "TTL"}
TRANSACTIONS = {"BUY", "SELL"}

DEFAULT_MAX_VALUE = 50_000.0
PRICE_DEVIATION_WARN = 0.05  # 5 % from LTP
TAG_RE = re.compile(r"^[A-Za-z0-9]{1,20}$")


def _is_multiple(value: float, step: float) -> bool:
    if not step:
        return True
    return abs(round(value / step) * step - value) < 1e-6


def validate_order(order: dict[str, Any], instrument: dict[str, Any] | None = None,
                   ltp: float | None = None, now: datetime | None = None,
                   max_order_value: float | None = None,
                   freeze_quantity: int | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    variety = str(order.get("variety", "regular")).lower()
    exchange = str(order.get("exchange", "")).upper()
    side = str(order.get("transaction_type", "")).upper()
    otype = str(order.get("order_type", "")).upper()
    product = str(order.get("product", "")).upper()
    validity = str(order.get("validity", "DAY")).upper()
    qty = order.get("quantity")
    price = order.get("price")
    trigger = order.get("trigger_price")
    mp = order.get("market_protection")
    symbol = order.get("tradingsymbol")

    # --- required fields & enums -------------------------------------------------
    if not symbol:
        errors.append("tradingsymbol is required")
    if exchange not in EXCHANGES:
        errors.append(f"exchange must be one of {sorted(EXCHANGES)}, got {exchange!r}")
    if side not in TRANSACTIONS:
        errors.append("transaction_type must be BUY or SELL")
    if otype not in ORDER_TYPES:
        errors.append(f"order_type must be one of {sorted(ORDER_TYPES)}")
    if product not in PRODUCTS:
        errors.append(f"product must be one of {sorted(PRODUCTS)}")
    if variety not in VARIETIES:
        errors.append(f"variety must be one of {sorted(VARIETIES)}")
    if validity not in VALIDITIES:
        errors.append(f"validity must be one of {sorted(VALIDITIES)}")

    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        errors.append("quantity must be a positive integer")
        qty = None

    # --- product / segment rules -------------------------------------------------
    is_cash = exchange in CASH_EXCHANGES
    if product in ("CNC", "MTF") and not is_cash:
        errors.append(f"{product} is only valid on NSE/BSE cash; use NRML or MIS for {exchange}")
    if product == "NRML" and is_cash:
        errors.append("NRML is for F&O/commodity/currency; use CNC (delivery) or MIS (intraday) on NSE/BSE")
    if product == "CO" or variety == "co":
        warnings.append("Cover orders are a legacy variety; prefer a regular order plus a separate SL/GTT")

    # --- price fields --------------------------------------------------------------
    if otype == "LIMIT" and not (isinstance(price, (int, float)) and price > 0):
        errors.append("LIMIT orders need price > 0")
    if otype in ("SL", "SL-M") and not (isinstance(trigger, (int, float)) and trigger > 0):
        errors.append(f"{otype} orders need trigger_price > 0")
    if otype == "SL" and not (isinstance(price, (int, float)) and price > 0):
        errors.append("SL orders need a limit price > 0 as well as trigger_price")
    if otype in ("MARKET", "SL-M"):
        if mp is None:
            errors.append(f"{otype} orders must set market_protection (-1 for auto, or 1–100 %) — "
                          "orders without it are rejected")
        elif mp != -1 and not (0 < float(mp) <= 100):
            errors.append("market_protection must be -1 or within (0, 100]; 0 is rejected")
        warnings.append(f"{otype} order: fill price is not controlled. Prefer LIMIT unless the user asked.")
    if otype == "SL" and isinstance(price, (int, float)) and isinstance(trigger, (int, float)):
        if side == "BUY" and price < trigger:
            errors.append("BUY SL: limit price must be ≥ trigger_price")
        if side == "SELL" and price > trigger:
            errors.append("SELL SL: limit price must be ≤ trigger_price")
    if otype in ("SL", "SL-M") and ltp and isinstance(trigger, (int, float)):
        if side == "BUY" and trigger <= ltp:
            warnings.append(f"BUY stop trigger {trigger} is at/below LTP {ltp}; it may trigger immediately")
        if side == "SELL" and trigger >= ltp:
            warnings.append(f"SELL stop trigger {trigger} is at/above LTP {ltp}; it may trigger immediately")

    # --- validity / variety extras -----------------------------------------------
    if validity == "TTL":
        ttl = order.get("validity_ttl")
        if not isinstance(ttl, int) or ttl < 1:
            errors.append("TTL validity needs validity_ttl (minutes, integer ≥ 1)")
    if variety == "iceberg":
        legs = order.get("iceberg_legs")
        if not isinstance(legs, int) or not 2 <= legs <= 50:
            errors.append("iceberg_legs must be an integer between 2 and 50")
        if not order.get("iceberg_quantity"):
            errors.append("iceberg orders need iceberg_quantity (quantity / iceberg_legs)")
    if variety == "auction" and not order.get("auction_number"):
        errors.append("auction orders need auction_number (see kite.get_auction_instruments())")
    tag = order.get("tag")
    if tag is None:
        warnings.append("No tag set — add tag='kiteskill' so agent orders are traceable")
    elif not TAG_RE.match(str(tag)):
        errors.append("tag must be alphanumeric, 1–20 characters")
    if order.get("disclosed_quantity") and not is_cash:
        warnings.append("disclosed_quantity applies to equity only; it will be ignored/rejected for F&O")

    # --- instrument-aware checks --------------------------------------------------
    lot_size = tick_size = None
    if instrument:
        lot_size = int(instrument.get("lot_size") or 1)
        tick_size = float(instrument.get("tick_size") or 0)
        if instrument.get("tradingsymbol") and symbol and instrument["tradingsymbol"] != symbol:
            errors.append(f"instrument row is {instrument['tradingsymbol']}, order is {symbol}")
        if instrument.get("exchange") and exchange and instrument["exchange"] != exchange:
            errors.append(f"instrument is listed on {instrument['exchange']}, order says {exchange}")
        if instrument.get("segment") == "INDICES":
            errors.append("Indices are not tradable — trade their futures/options instead")
    elif not is_cash:
        errors.append("Derivative order without instrument data — resolve it via scripts/instruments.py "
                      "so lot size and tick size can be checked")

    if qty and lot_size and lot_size > 1 and qty % lot_size:
        errors.append(f"quantity {qty} is not a multiple of lot size {lot_size} "
                      f"(nearest: {max(lot_size, round(qty / lot_size) * lot_size)})")
    for label, val in (("price", price), ("trigger_price", trigger)):
        if tick_size and isinstance(val, (int, float)) and val > 0 and not _is_multiple(val, tick_size):
            errors.append(f"{label} {val} is not a multiple of tick size {tick_size}")

    if qty and freeze_quantity and qty > freeze_quantity:
        warnings.append(f"quantity {qty} exceeds freeze limit {freeze_quantity}; "
                        "use kite.place_autoslice_order (max 10 slices)")

    # --- risk warnings ------------------------------------------------------------
    ref_price = price if isinstance(price, (int, float)) and price > 0 else ltp
    notional = float(qty * ref_price) if qty and ref_price else None
    limit = max_order_value or float(os.environ.get("KITE_MAX_ORDER_VALUE", DEFAULT_MAX_VALUE))
    if notional and notional > limit:
        warnings.append(f"Order value ₹{notional:,.0f} exceeds ₹{limit:,.0f} — confirm size explicitly")

    if ltp and isinstance(price, (int, float)) and price > 0 and otype in ("LIMIT", "SL"):
        dev = abs(price - ltp) / ltp
        if dev > PRICE_DEVIATION_WARN:
            warnings.append(f"Limit price {price} is {dev:.1%} away from LTP {ltp} — possible fat-finger")

    itype = (instrument or {}).get("instrument_type") or (str(symbol)[-2:] if symbol else "")
    if side == "SELL" and itype in ("CE", "PE") and not is_cash:
        warnings.append("Short option: risk is large/unlimited and margin-heavy. "
                        "Check basket_order_margins and consider a hedge.")

    if exchange in EXCHANGES:
        status = market_status(exchange, now)
        if variety == "amo":
            if status["open"]:
                warnings.append("Market is open — AMO is unnecessary; use variety='regular'")
        elif not status["open"]:
            warnings.append(f"{status['detail']}. Regular orders will be rejected — offer variety='amo'.")
        if product == "MIS":
            msg = mis_square_off_warning(exchange, now)
            if msg:
                warnings.append(msg)

    return {"ok": not errors, "errors": errors, "warnings": warnings, "notional": notional}


def format_preview(order: dict[str, Any], report: dict[str, Any] | None = None) -> str:
    """Human-readable order ticket for the confirmation prompt."""
    o = order
    px = o.get("price") or ("MKT" if o.get("order_type") in ("MARKET", "SL-M") else "-")
    lines = [
        "┌─ ORDER PREVIEW (not yet placed) ─────────────",
        f"│ {o.get('transaction_type')} {o.get('quantity')} × {o.get('exchange')}:{o.get('tradingsymbol')}",
        f"│ type={o.get('order_type')}  price={px}  trigger={o.get('trigger_price') or '-'}",
        f"│ product={o.get('product')}  variety={o.get('variety', 'regular')}  validity={o.get('validity', 'DAY')}",
    ]
    if o.get("market_protection") is not None:
        lines.append(f"│ market_protection={o['market_protection']}")
    if report:
        if report.get("notional"):
            lines.append(f"│ approx value ₹{report['notional']:,.2f}")
        for e in report["errors"]:
            lines.append(f"│ ✖ {e}")
        for w in report["warnings"]:
            lines.append(f"│ ⚠ {w}")
        lines.append(f"│ status: {'READY — awaiting your confirmation' if report['ok'] else 'BLOCKED — fix errors'}")
    lines.append("└──────────────────────────────────────────────")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    o = json.loads(sys.argv[1])
    r = validate_order(o, ltp=o.pop("_ltp", None))
    print(format_preview(o, r))
    raise SystemExit(0 if r["ok"] else 1)
