---
name: kite-backtest
description: >
  Use when the user wants to backtest or research a trading strategy on
  Indian markets with Zerodha Kite Connect historical data: fetch long
  OHLCV/OI candle histories (chunked + cached + rate-limited), compute
  realistic Zerodha brokerage, STT, exchange, SEBI, stamp duty, GST and DP
  charges, run a no-look-ahead bar-by-bar backtest for delivery, intraday
  (MIS square-off), futures or options, and report CAGR, drawdown, Sharpe,
  win rate, profit factor and cost drag. Also for "how much will charges
  eat", "breakeven move after costs", or paper-testing an idea before
  going live on Kite. UNOFFICIAL community skill — not affiliated with Zerodha.
compatibility: >
  Python 3.9+. Fetching data needs `pip install kiteconnect` and the Kite
  Connect (paid) plan. The backtester (scripts/backtest.py) and cost model
  (scripts/charges.py) are pure standard library; pandas is optional for
  analysis.
---

# Kite Backtest — Historical Data & Zerodha Cost Model

> **Unofficial**, not affiliated with Zerodha. Backtests are hypothetical — past results don't predict
> future returns. Not investment advice.

## Setup

```python
from scripts.kite_common import get_client, find_equity_token
from scripts.fetch_history import fetch_candles, to_dataframe, write_csv, read_csv
from scripts.backtest import run_backtest, buy_and_hold, format_metrics
from scripts.charges import trade_charges, breakeven_move

kite = get_client()
tok = find_equity_token(kite, "RELIANCE")
candles = fetch_candles(kite, tok, "2018-01-01", "2026-09-30", "day")   # chunked + cached
```

CLI: `python scripts/fetch_history.py RELIANCE day 2018-01-01 2026-09-30 --out reliance.csv`

## Workflow

1. **Data** — `fetch_candles` (chunks by interval limit, ≤ 3 req/s, retries, caches completed ranges
   under `~/.kite-skills/history`). Save to CSV so research doesn't hit the API repeatedly.
2. **Signals** — compute a list `signals[i] ∈ {-1, 0, +1}` using **only data up to bar i**.
3. **Run** — `run_backtest(candles, signals, segment=..., capital=..., quantity=..., lot_size=...)`.
   Execution happens at the next bar's open with slippage + full charges.
4. **Compare** — always print `buy_and_hold(candles)` for the same period.
5. **Report** — metrics table, number of trades, charges as % of capital, and caveats (below).

## Rules the engine enforces

| Rule | Why |
|---|---|
| Signal on bar *i* fills at open of *i+1* | No look-ahead |
| Slippage default 2 bps per fill | Real fills aren't at the print |
| Full Zerodha charges per fill | Intraday/options costs often kill edge |
| `intraday` flattened at each day's last bar close | MIS auto square-off |
| `delivery` can't short | No overnight cash shorting in India |
| F&O requires `quantity` multiple of `lot_size` | Contracts, not notional |

## Charges quick answers

```python
trade_charges("options", buy_value=120*75, sell_value=150*75)        # premium turnover
trade_charges("intraday", 2_00_000, 2_01_000)
breakeven_move("futures", price=25000, quantity=75)                   # points needed to cover costs
```

Snapshot rates (Oct 2026): delivery STT 0.1 % both sides; intraday 0.025 % sell; futures 0.05 % sell;
options 0.15 % of sell premium; options brokerage ₹20/order; intraday & futures 0.03 % or ₹20.
Details and the full table: [references/cost-model.md](references/cost-model.md). For executed orders,
`kite.get_virtual_contract_note()` gives exact charges.

## Must-say caveats in every backtest report

- Kite's instruments dump lists only **currently live** instruments → stock universes built today have
  **survivorship bias** (delisted/merged names missing).
- **Expired options/futures have no history on Kite** (except futures `continuous=True` day candles).
  Option backtests need data you recorded while contracts were live, or a modelled price.
- Corporate actions: check splits/bonuses in the period; Kite's equity history may not be adjusted for
  every action.
- Intraday minute data is limited to ~60 days per request and history depth varies — state the range used.
- Taxes (STCG/LTCG/business income) are **not** modelled.

## Reference files

| Need | File |
|---|---|
| Intervals, per-request limits, continuous futures, OI, caching | [references/data-fetching.md](references/data-fetching.md) |
| Every charge component, formulas, worked examples | [references/cost-model.md](references/cost-model.md) |
| Bias, overfitting, walk-forward, paper trading → live checklist | [references/pitfalls.md](references/pitfalls.md) |

Examples: `examples/sma_crossover.py` (daily delivery), `examples/opening_range_breakout.py`
(15-minute intraday with MIS square-off).
