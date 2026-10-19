#!/usr/bin/env python3
"""Opening-range breakout on 15-minute candles, intraday (MIS) with end-of-day square-off.

UNOFFICIAL — not affiliated with Zerodha. Hypothetical results; not investment advice.

Rule: the first 15-minute bar (09:15–09:30) sets the range. Go long when a later bar closes above
the range high, short when it closes below the range low; one entry per day; exit at the close of
the day's last bar (enforced by the engine). Fills happen at the next bar's open.

    python examples/opening_range_breakout.py SBIN --start 2026-04-01 --end 2026-09-30
    python examples/opening_range_breakout.py --csv sbin_15m.csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.backtest import format_metrics, run_backtest  # noqa: E402
from scripts.fetch_history import fetch_candles, read_csv  # noqa: E402


def orb_signals(candles):
    sig, day, hi, lo, state = [], None, None, None, 0
    for c in candles:
        d = c["date"].date()
        if d != day:  # first bar of the day defines the range
            day, hi, lo, state = d, c["high"], c["low"], 0
            sig.append(0)
            continue
        if state == 0:
            if c["close"] > hi:
                state = 1
            elif c["close"] < lo:
                state = -1
        sig.append(state)
    return sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?")
    ap.add_argument("--csv")
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--quantity", type=int, default=100)
    ap.add_argument("--capital", type=float, default=100_000)
    a = ap.parse_args()

    if a.csv:
        candles = read_csv(a.csv)
    else:
        from scripts.kite_common import find_equity_token, get_client
        kite = get_client()
        candles = fetch_candles(kite, find_equity_token(kite, a.symbol), a.start, a.end, "15minute")

    res = run_backtest(candles, orb_signals(candles), segment="intraday", capital=a.capital,
                       quantity=a.quantity, slippage_bps=3)
    m = res["metrics"]
    print(f"ORB 15m — {a.symbol or a.csv}, {a.quantity} shares/trade\n")
    print(format_metrics(m))
    gross = sum(t["gross_pnl"] for t in res["trades"])
    print(f"\nGross P&L ₹{gross:,.0f} vs charges ₹{m['total_charges']:,.0f} "
          f"→ costs ate {m['total_charges'] / gross * 100:.0f}% of gross" if gross > 0 else
          f"\nGross P&L ₹{gross:,.0f} (negative before costs)")


if __name__ == "__main__":
    main()
