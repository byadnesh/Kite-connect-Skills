#!/usr/bin/env python3
"""Daily SMA crossover (long-only, delivery) vs buy-and-hold, with Zerodha charges.

UNOFFICIAL — not affiliated with Zerodha. Hypothetical results; not investment advice.

    python examples/sma_crossover.py RELIANCE --start 2018-01-01 --end 2026-09-30 --fast 50 --slow 200
    python examples/sma_crossover.py --csv reliance_day.csv                 # offline
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.backtest import buy_and_hold, format_metrics, run_backtest  # noqa: E402
from scripts.fetch_history import fetch_candles, read_csv  # noqa: E402


def sma(values, n):
    out, s = [None] * len(values), 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def signals_sma(candles, fast, slow):
    closes = [c["close"] for c in candles]
    f, s = sma(closes, fast), sma(closes, slow)
    return [1 if (f[i] is not None and s[i] is not None and f[i] > s[i]) else 0 for i in range(len(candles))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?")
    ap.add_argument("--csv")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--fast", type=int, default=50)
    ap.add_argument("--slow", type=int, default=200)
    ap.add_argument("--capital", type=float, default=100_000)
    a = ap.parse_args()

    if a.csv:
        candles = read_csv(a.csv)
    else:
        from scripts.kite_common import find_equity_token, get_client
        kite = get_client()
        candles = fetch_candles(kite, find_equity_token(kite, a.symbol), a.start, a.end, "day")

    sig = signals_sma(candles, a.fast, a.slow)
    res = run_backtest(candles, sig, segment="delivery", capital=a.capital)
    bh = buy_and_hold(candles, capital=a.capital)

    print(f"SMA {a.fast}/{a.slow} crossover — {a.symbol or a.csv}\n")
    print(format_metrics(res["metrics"]))
    print("\nBuy & hold")
    print(format_metrics({k: bh["metrics"][k] for k in ("total_return_pct", "cagr_pct", "max_drawdown_pct",
                                                         "sharpe", "total_charges")}))
    print("\nLast 5 trades:")
    for t in res["trades"][-5:]:
        print(f"  {t['entry_date']:%Y-%m-%d} → {t['exit_date']:%Y-%m-%d}  {t['qty']} @ {t['entry_price']:.2f} → "
              f"{t['exit_price']:.2f}  net ₹{t['net_pnl']:,.0f}")


if __name__ == "__main__":
    main()
