#!/usr/bin/env python3
"""Chunked, rate-limited, cached historical candle fetcher for Kite Connect.

UNOFFICIAL — not affiliated with Zerodha. Needs the Kite Connect (paid) plan.

    from scripts.fetch_history import fetch_candles, to_dataframe
    rows = fetch_candles(kite, 738561, "2019-01-01", "2026-10-01", "day")
    df = to_dataframe(rows)          # pandas optional

CLI:
    python scripts/fetch_history.py RELIANCE day 2019-01-01 2026-10-01 --out reliance_day.csv
    python scripts/fetch_history.py "NIFTY 50" 5minute 2026-08-01 2026-10-01 --out nifty_5m.csv
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.kite_common import HOME, IST  # noqa: E402

# Observed max span per request; we stay a little under.
MAX_DAYS = {
    "minute": 60, "3minute": 100, "5minute": 100, "10minute": 100,
    "15minute": 200, "30minute": 200, "60minute": 400, "day": 2000,
}
MIN_INTERVAL_S = 0.35  # 3 req/s limit


def _as_dt(x) -> datetime:
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=IST)
    if isinstance(x, date):
        return datetime(x.year, x.month, x.day, tzinfo=IST)
    s = str(x)
    return datetime.fromisoformat(s if len(s) > 10 else s + " 00:00:00").replace(tzinfo=IST)


def chunk_ranges(start, end, interval: str) -> list[tuple[datetime, datetime]]:
    if interval not in MAX_DAYS:
        raise ValueError(f"interval must be one of {list(MAX_DAYS)}")
    s, e = _as_dt(start), _as_dt(end)
    if e <= s:
        return []
    step = timedelta(days=MAX_DAYS[interval] - 1)
    out, cur = [], s
    while cur < e:
        nxt = min(cur + step, e)
        out.append((cur, nxt))
        cur = nxt + timedelta(seconds=1)
    return out


def fetch_candles(kite, instrument_token: int, start, end, interval: str = "day", oi: bool = False,
                  continuous: bool = False, cache: bool = True, max_retries: int = 3) -> list[dict[str, Any]]:
    """All candles in [start, end], de-duplicated and sorted. Dates are tz-aware IST datetimes."""
    s, e = _as_dt(start), _as_dt(end)
    cache_file = HOME / "history" / (f"{instrument_token}_{interval}_{s:%Y%m%d}_{e:%Y%m%d}"
                                     f"{'_oi' if oi else ''}{'_cont' if continuous else ''}.json")
    # Only cache ranges that end before today (today's candles are still forming).
    cacheable = cache and e.date() < datetime.now(IST).date()
    if cacheable and cache_file.exists():
        rows = json.loads(cache_file.read_text(encoding="utf-8"))
        for r in rows:
            r["date"] = datetime.fromisoformat(r["date"])
        return rows

    rows: dict[datetime, dict[str, Any]] = {}
    last_call = 0.0
    for a, b in chunk_ranges(s, e, interval):
        for attempt in range(max_retries):
            wait = MIN_INTERVAL_S - (time.time() - last_call)
            if wait > 0:
                time.sleep(wait)
            last_call = time.time()
            try:
                batch = kite.historical_data(instrument_token, a.replace(tzinfo=None), b.replace(tzinfo=None),
                                             interval, continuous=continuous, oi=oi)
                break
            except Exception as exc:  # NetworkException / 429 → back off
                if attempt == max_retries - 1 or "Token" in type(exc).__name__ or "Input" in type(exc).__name__:
                    raise
                time.sleep(1.5 * (attempt + 1))
        for r in batch:
            rows[r["date"]] = r
    out = [rows[k] for k in sorted(rows)]

    if cacheable and out:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps([{**r, "date": r["date"].isoformat()} for r in out]), encoding="utf-8")
    return out


def to_dataframe(rows: list[dict[str, Any]]):
    """pandas DataFrame indexed by IST datetime (requires pandas)."""
    import pandas as pd

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def write_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({**r, "date": r["date"].isoformat()})


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            row = {"date": datetime.fromisoformat(r["date"])}
            for k in ("open", "high", "low", "close"):
                row[k] = float(r[k])
            row["volume"] = int(float(r.get("volume") or 0))
            if r.get("oi") not in (None, ""):
                row["oi"] = int(float(r["oi"]))
            out.append(row)
    return out


if __name__ == "__main__":
    import argparse

    from scripts.kite_common import find_equity_token, get_client

    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="NSE tradingsymbol or index name, or a numeric instrument_token")
    ap.add_argument("interval", choices=list(MAX_DAYS))
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--exchange", default="NSE")
    ap.add_argument("--oi", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    k = get_client()
    tok = int(a.symbol) if a.symbol.isdigit() else find_equity_token(k, a.symbol, a.exchange)
    data = fetch_candles(k, tok, a.start, a.end, a.interval, oi=a.oi)
    print(f"{len(data)} candles", data[0]["date"] if data else "", "→", data[-1]["date"] if data else "")
    if a.out:
        write_csv(data, a.out)
        print("wrote", a.out)
