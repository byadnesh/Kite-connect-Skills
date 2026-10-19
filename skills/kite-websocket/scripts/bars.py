"""Build OHLCV candles from KiteTicker ticks.

UNOFFICIAL — not affiliated with Zerodha. Standard library only.

    bb = BarBuilder(interval=60)                 # seconds; anchored to 09:15 IST
    for received_at, tick in stream.iter_ticks(timeout=1):
        for bar in bb.update(tick, received_at) + bb.flush():
            ...

A bar: {"token", "start", "end", "open", "high", "low", "close", "volume", "oi", "ticks"}
(`start`/`end` are aware IST datetimes; `end` is exclusive).
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.tick_utils import IST, now_ist, tick_time  # noqa: E402


class BarBuilder:
    def __init__(self, interval: int = 60, anchor: time = time(9, 15), use_exchange_time: bool = True,
                 on_bar: Callable[[dict[str, Any]], None] | None = None):
        if interval <= 0:
            raise ValueError("interval must be a positive number of seconds")
        self.interval = int(interval)
        self.anchor = anchor
        self.use_exchange_time = use_exchange_time
        self.on_bar = on_bar
        self.current: dict[int, dict[str, Any]] = {}
        self._cum_volume: dict[int, tuple[Any, int]] = {}  # token -> (date, cumulative volume)
        self.late_ticks = 0

    def bucket_start(self, ts: datetime) -> datetime:
        ts = ts.astimezone(IST)
        anchor_dt = datetime.combine(ts.date(), self.anchor, IST)
        k = math.floor((ts - anchor_dt).total_seconds() / self.interval)
        return anchor_dt + timedelta(seconds=k * self.interval)

    def _emit(self, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.on_bar:
            for b in bars:
                self.on_bar(b)
        return bars

    def update(self, tick: dict[str, Any], received_at: datetime | None = None) -> list[dict[str, Any]]:
        price = tick.get("last_price")
        token = tick.get("instrument_token")
        if not price or token is None:
            return []
        ts = tick_time(tick, received_at) if self.use_exchange_time else (
            received_at.astimezone(IST) if received_at else now_ist())

        # Cumulative day volume -> per-tick volume.
        dv = 0
        cum = tick.get("volume_traded")
        if cum is not None:
            prev = self._cum_volume.get(token)
            if prev and prev[0] == ts.date() and cum >= prev[1]:
                dv = cum - prev[1]
            self._cum_volume[token] = (ts.date(), cum)

        start = self.bucket_start(ts)
        done: list[dict[str, Any]] = []
        bar = self.current.get(token)
        if bar is not None and start < bar["start"]:
            self.late_ticks += 1          # out-of-order tick for an already-closed bucket
            return []
        if bar is not None and start > bar["start"]:
            done.append(bar)
            bar = None
        if bar is None:
            bar = {"token": token, "start": start, "end": start + timedelta(seconds=self.interval),
                   "open": price, "high": price, "low": price, "close": price, "volume": 0,
                   "oi": tick.get("oi"), "ticks": 0}
            self.current[token] = bar
        bar["high"] = max(bar["high"], price)
        bar["low"] = min(bar["low"], price)
        bar["close"] = price
        bar["volume"] += dv
        bar["ticks"] += 1
        if tick.get("oi") is not None:
            bar["oi"] = tick["oi"]
        return self._emit(done)

    def flush(self, now: datetime | None = None, force: bool = False) -> list[dict[str, Any]]:
        """Close bars whose bucket has ended (or all bars with force=True, e.g. at shutdown)."""
        now = (now or now_ist()).astimezone(IST)
        done = [b for b in self.current.values() if force or b["end"] <= now]
        for b in done:
            del self.current[b["token"]]
        done.sort(key=lambda b: (b["start"], b["token"]))
        return self._emit(done)
