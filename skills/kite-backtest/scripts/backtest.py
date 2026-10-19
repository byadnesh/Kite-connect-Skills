#!/usr/bin/env python3
"""Small, honest bar-by-bar backtester with the Zerodha cost model.

UNOFFICIAL — not affiliated with Zerodha. Pure standard library.

Rules baked in to avoid common lies:
- Signals computed on bar i are executed at the OPEN of bar i+1 (no look-ahead).
- Every fill pays slippage (bps) and full Zerodha charges (scripts/charges.py).
- `intraday` segment is force-flattened at the close of each day's last bar (MIS square-off).
- `delivery` cannot go short (no overnight shorting of cash equity in India).
- Futures/options need an explicit `quantity` (multiple of lot_size) — no notional "all-in".

    from scripts.backtest import run_backtest
    result = run_backtest(candles, signals, segment="delivery", capital=100_000)
    print(result["metrics"])

`candles`: list of {"date": datetime, "open", "high", "low", "close", "volume"} (oldest first)
`signals`: list of target exposure per bar, same length: +1 long, 0 flat, -1 short
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.charges import trade_charges  # noqa: E402


def _day(d):
    return d.date() if hasattr(d, "date") else d


def run_backtest(candles: list[dict[str, Any]], signals: list[float], *, segment: str = "delivery",
                 exchange: str = "NSE", capital: float = 100_000.0, quantity: int | None = None,
                 lot_size: int = 1, slippage_bps: float = 2.0, allow_short: bool | None = None) -> dict[str, Any]:
    n = len(candles)
    if n != len(signals):
        raise ValueError("candles and signals must have the same length")
    if segment in ("futures", "options") and not quantity:
        raise ValueError("futures/options backtests need an explicit quantity (lots × lot_size)")
    if quantity and quantity % lot_size:
        raise ValueError(f"quantity {quantity} is not a multiple of lot_size {lot_size}")
    if allow_short is None:
        allow_short = segment != "delivery"
    slip = slippage_bps / 10_000

    cash, pos, avg = float(capital), 0, 0.0
    total_charges = 0.0
    fills: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    open_trade: dict[str, Any] | None = None
    equity: list[tuple[Any, float]] = []

    def fill(i, target, raw_price, reason):
        nonlocal cash, pos, avg, total_charges, open_trade
        delta = target - pos
        if delta == 0:
            return
        side = "BUY" if delta > 0 else "SELL"
        px = raw_price * (1 + slip) if side == "BUY" else raw_price * (1 - slip)
        value = abs(delta) * px
        ch = trade_charges(segment, buy_value=value if side == "BUY" else 0.0,
                           sell_value=value if side == "SELL" else 0.0, exchange=exchange)["total"]
        total_charges += ch
        cash -= delta * px + ch
        fills.append({"date": candles[i]["date"], "side": side, "qty": abs(delta), "price": px,
                      "charges": ch, "reason": reason})

        # Round-trip bookkeeping
        if pos != 0 and (target == 0 or (target > 0) != (pos > 0)):
            closed = abs(pos)
            gross = (px - avg) * closed * (1 if pos > 0 else -1) + open_trade["realized"]
            open_trade["charges"] += ch * (closed / abs(delta))
            trades.append({**{k: v for k, v in open_trade.items() if k != "realized"}, "exit_date": candles[i]["date"], "exit_price": px,
                           "gross_pnl": gross, "net_pnl": gross - open_trade["charges"]})
            open_trade = None
            rem = abs(target)
            if rem:
                open_trade = {"entry_date": candles[i]["date"], "side": "LONG" if target > 0 else "SHORT",
                              "qty": rem, "entry_price": px, "charges": ch * (rem / abs(delta)), "realized": 0.0}
            avg = px if rem else 0.0
        elif pos == 0:
            open_trade = {"entry_date": candles[i]["date"], "side": "LONG" if target > 0 else "SHORT",
                          "qty": abs(target), "entry_price": px, "charges": ch, "realized": 0.0}
            avg = px
        else:  # scaling within the same direction
            if abs(target) > abs(pos):
                avg = (avg * abs(pos) + px * abs(delta)) / abs(target)
                open_trade["qty"] = abs(target)
            else:  # partial exit: realise P&L on the reduced quantity
                open_trade["realized"] += (px - avg) * abs(delta) * (1 if pos > 0 else -1)
            open_trade["charges"] += ch
        pos = target

    def target_qty(sig, price, eq_now):
        if sig == 0:
            return 0
        if sig < 0 and not allow_short:
            return 0
        if quantity:
            units = quantity
        else:
            units = int(eq_now * abs(sig) / (price * (1 + slip)) / lot_size) * lot_size
            units = int(units * 0.995 / lot_size) * lot_size  # leave room for charges
        return units if sig > 0 else -units

    for i in range(n):
        bar = candles[i]
        if i > 0:
            eq_now = cash + pos * bar["open"]
            tgt = target_qty(signals[i - 1], bar["open"], eq_now)
            if segment == "intraday":
                first_of_day = _day(candles[i - 1]["date"]) != _day(bar["date"])
                last_of_day = i + 1 == n or _day(candles[i + 1]["date"]) != _day(bar["date"])
                # Yesterday's last signal never carries into today's open, and a fresh position is
                # not opened on the day's last bar (it would be squared off immediately).
                if first_of_day or (last_of_day and pos == 0):
                    tgt = 0 if first_of_day else pos
            fill(i, tgt, bar["open"], "signal")
        last_of_day = i + 1 == n or _day(candles[i + 1]["date"]) != _day(bar["date"])
        if segment == "intraday" and last_of_day and pos != 0:
            fill(i, 0, bar["close"], "eod_squareoff")
        equity.append((bar["date"], cash + pos * bar["close"]))

    if pos != 0:
        fill(n - 1, 0, candles[-1]["close"], "end_of_data")
        equity[-1] = (candles[-1]["date"], cash)

    return {"metrics": compute_metrics(equity, trades, capital, total_charges), "trades": trades,
            "fills": fills, "equity": equity}


def compute_metrics(equity, trades, capital, total_charges) -> dict[str, Any]:
    if not equity:
        return {}
    final = equity[-1][1]
    peak, mdd = -math.inf, 0.0
    for _, v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)

    daily: dict[Any, float] = {}
    for d, v in equity:
        daily[_day(d)] = v
    vals = list(daily.values())
    rets = [b / a - 1 for a, b in zip(vals, vals[1:]) if a]
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0.0
    downside = [r for r in rets if r < 0]
    dsd = math.sqrt(sum(r * r for r in downside) / len(rets)) if rets and downside else 0.0

    first_day, last_day = list(daily)[0], list(daily)[-1]
    years = max((last_day - first_day).days / 365.25, 1 / 365.25)
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = -sum(t["net_pnl"] for t in losses)

    return {
        "start": str(first_day), "end": str(last_day),
        "initial_capital": round(capital, 2), "final_equity": round(final, 2),
        "total_return_pct": round((final / capital - 1) * 100, 2),
        "cagr_pct": round(((final / capital) ** (1 / years) - 1) * 100, 2) if final > 0 else None,
        "max_drawdown_pct": round(mdd * 100, 2),
        "sharpe": round(mean / sd * math.sqrt(252), 2) if sd else None,
        "sortino": round(mean / dsd * math.sqrt(252), 2) if dsd else None,
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "avg_trade": round(sum(t["net_pnl"] for t in trades) / len(trades), 2) if trades else None,
        "total_charges": round(total_charges, 2),
        "charges_pct_of_capital": round(total_charges / capital * 100, 2),
    }


def buy_and_hold(candles, capital=100_000.0, segment="delivery") -> dict[str, Any]:
    """Benchmark: long from the second bar's open to the end."""
    return run_backtest(candles, [1] * len(candles), segment=segment, capital=capital)


def format_metrics(m: dict[str, Any]) -> str:
    return "\n".join(f"{k:<24}{v}" for k, v in m.items())
