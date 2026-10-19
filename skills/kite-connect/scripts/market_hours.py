#!/usr/bin/env python3
"""Market-session checks for Indian exchanges (IST, no DST).

UNOFFICIAL — not affiliated with Zerodha.

Kite exposes no holiday calendar, so this only knows weekends and session times.
Pass extra holiday dates via `holidays=` (or KITE_HOLIDAYS="2026-10-20,2026-11-09").
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

SESSIONS = {
    "NSE": (time(9, 15), time(15, 30)),
    "BSE": (time(9, 15), time(15, 30)),
    "NFO": (time(9, 15), time(15, 30)),
    "BFO": (time(9, 15), time(15, 30)),
    "CDS": (time(9, 0), time(17, 0)),
    "BCD": (time(9, 0), time(17, 0)),
    "MCX": (time(9, 0), time(23, 30)),  # 23:55 while the US is on daylight saving
}
PRE_OPEN = (time(9, 0), time(9, 8))  # NSE/BSE cash only

# Approximate Zerodha MIS auto square-off times
MIS_SQUARE_OFF = {
    "NSE": time(15, 20), "BSE": time(15, 20),
    "NFO": time(15, 25), "BFO": time(15, 25),
    "CDS": time(16, 45), "BCD": time(16, 45),
    "MCX": time(23, 0),
}


def _holidays(extra: set[date] | None) -> set[date]:
    env = {date.fromisoformat(d.strip()) for d in os.environ.get("KITE_HOLIDAYS", "").split(",") if d.strip()}
    return env | (extra or set())


def now_ist() -> datetime:
    return datetime.now(IST)


def market_status(exchange: str = "NSE", at: datetime | None = None,
                  holidays: set[date] | None = None) -> dict:
    """Return {'open': bool, 'phase': str, 'detail': str} for an exchange."""
    exchange = exchange.upper()
    at = (at or now_ist()).astimezone(IST)
    start, end = SESSIONS.get(exchange, SESSIONS["NSE"])
    t = at.time()

    if at.weekday() >= 5:
        return {"open": False, "phase": "weekend", "detail": f"{exchange} closed (weekend)"}
    if at.date() in _holidays(holidays):
        return {"open": False, "phase": "holiday", "detail": f"{exchange} closed (holiday)"}
    if exchange in ("NSE", "BSE") and PRE_OPEN[0] <= t < PRE_OPEN[1]:
        return {"open": False, "phase": "pre-open", "detail": "Pre-open call auction (09:00–09:08)"}
    if start <= t < end:
        return {"open": True, "phase": "open", "detail": f"{exchange} open until {end:%H:%M} IST"}
    if t < start:
        return {"open": False, "phase": "before-open", "detail": f"{exchange} opens {start:%H:%M} IST"}
    return {"open": False, "phase": "closed", "detail": f"{exchange} closed at {end:%H:%M} IST"}


def is_market_open(exchange: str = "NSE", at: datetime | None = None) -> bool:
    return market_status(exchange, at)["open"]


def mis_square_off_warning(exchange: str, at: datetime | None = None, minutes_before: int = 15) -> str | None:
    at = (at or now_ist()).astimezone(IST)
    cutoff = MIS_SQUARE_OFF.get(exchange.upper())
    if not cutoff:
        return None
    cutoff_dt = datetime.combine(at.date(), cutoff, IST)
    if at >= cutoff_dt - timedelta(minutes=minutes_before):
        return (f"MIS positions on {exchange} are auto-squared off around {cutoff:%H:%M} IST "
                "(with an extra charge). Consider CNC/NRML or skip.")
    return None


if __name__ == "__main__":
    for ex in ("NSE", "NFO", "MCX", "CDS"):
        print(ex, market_status(ex))
