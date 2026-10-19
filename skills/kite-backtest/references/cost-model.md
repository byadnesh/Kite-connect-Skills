# Zerodha Cost Model

Implemented in `scripts/charges.py`. Snapshot of zerodha.com/charges (checked Oct 2026). Statutory
rates change with Union Budgets and exchange circulars — re-check before relying on them, and update
`RATES` in the script.

## Components

| Component | Delivery | Intraday | Futures | Options |
|---|---|---|---|---|
| Brokerage | ₹0 | min(0.03 %, ₹20) per executed order | min(0.03 %, ₹20) per order | ₹20 flat per order |
| STT / CTT | 0.1 % buy **and** sell | 0.025 % sell | 0.05 % sell | 0.15 % sell (on premium) |
| Exchange txn — NSE | 0.00307 % | 0.00307 % | 0.00183 % | 0.03553 % (premium) |
| Exchange txn — BSE | 0.00375 % | 0.00375 % | 0 | 0.0325 % (premium) |
| SEBI fee | ₹10/crore | ₹10/crore | ₹10/crore | ₹10/crore |
| Stamp duty (buy side) | 0.015 % | 0.003 % | 0.002 % | 0.003 % |
| GST | 18 % × (brokerage + exchange txn + SEBI) | | | |
| DP charge | ₹15.34 per scrip per day with a sell | – | – | – |

Extras not in the default model:
- **STT on exercise:** long options expiring ITM pay 0.15 % on intrinsic value (`stt_on_exercise()`).
- **MIS auto square-off:** ₹50 + GST per order squared off by Zerodha's RMS.
- Commodity (MCX) and currency have different rates — not modelled.
- Pledge/unpledge, AMC, call & trade charges.

## Formulas

```
turnover   = buy_value + sell_value                     (options: premium turnover)
brokerage  = Σ per order: min(order_value × pct, cap)   (options: 20 × orders)
stt        = rate × (turnover | sell_value)
txn        = exch_rate × turnover
sebi       = 10 / 1e7 × turnover
stamp      = stamp_rate × buy_value
gst        = 0.18 × (brokerage + txn + sebi)
total      = brokerage + stt + txn + sebi + stamp + gst (+ dp)
```

## Worked examples (from `python scripts/charges.py`)

```python
trade_charges("delivery", 1_50_000, 1_51_500)   # ₹350.62: STT ₹301.50 (0.1 % both sides) + stamp + DP
trade_charges("intraday", 1_50_000, 1_51_500)   # ₹100.86: 2 × ₹20 brokerage + ₹37.88 STT + GST
trade_charges("options", 9_000, 9_090)          # ₹68.71:  2 × ₹20 brokerage + GST dominate small premiums
```

## Breakeven

`breakeven_move(segment, price, quantity)` → points the instrument must move for a round trip to
cover charges. Use this to sanity-check scalping ideas: `breakeven_move("options", 100, 65)` ≈ 0.96
points on a 65-unit option trade at ₹100 premium — one-point targets have no edge after costs (before
even counting the bid-ask spread).

## Slippage

Charges ≠ slippage. The engine adds `slippage_bps` per fill (default 2 bps). For options use a
spread-based model instead: e.g. pay half the typical bid-ask spread per fill (often 0.5–2 % of premium
for OTM strikes).
