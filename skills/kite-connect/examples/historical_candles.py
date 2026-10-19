#!/usr/bin/env python3
"""Fetch candles and print simple stats (SMA, period return, ATR). Needs the Connect plan.

    python examples/historical_candles.py RELIANCE --days 180 --interval day
    python examples/historical_candles.py "NIFTY 50" --days 5 --interval 15minute
"""

import argparse
from datetime import datetime, timedelta

import _common  # noqa: F401  (adds the skill root to sys.path)
from scripts.instruments import find_equity
from scripts.kite_client import get_client


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--interval", default="day")
    ap.add_argument("--exchange", default="NSE")
    a = ap.parse_args()

    kite = get_client()
    tok = find_equity(kite, a.symbol, a.exchange)["instrument_token"]
    to = datetime.now()
    rows = kite.historical_data(tok, to - timedelta(days=a.days), to, a.interval)
    if not rows:
        print("No candles returned")
        return
    closes = [r["close"] for r in rows]
    trs = [max(r["high"] - r["low"], abs(r["high"] - p["close"]), abs(r["low"] - p["close"]))
           for p, r in zip(rows, rows[1:])]
    print(f"{len(rows)} candles {rows[0]['date']} → {rows[-1]['date']}")
    print(f"Last close {closes[-1]:.2f}  period return {(closes[-1] / closes[0] - 1) * 100:.2f}%")
    for n in (20, 50, 200):
        v = sma(closes, n)
        if v:
            print(f"SMA{n} {v:.2f}  ({'above' if closes[-1] > v else 'below'})")
    if len(trs) >= 14:
        print(f"ATR14 {sum(trs[-14:]) / 14:.2f}")
    print(f"High {max(r['high'] for r in rows):.2f}  Low {min(r['low'] for r in rows):.2f}")


if __name__ == "__main__":
    main()
