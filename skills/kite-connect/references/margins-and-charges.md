# Funds, Margins & Charges

## Available funds

```python
m = kite.margins()                 # {"equity": {...}, "commodity": {...}}
eq = kite.margins("equity")
eq["net"]                          # usable margin right now
eq["available"]["cash"]            # opening cash balance
eq["available"]["live_balance"]    # cash after today's activity
eq["available"]["collateral"]      # pledged-holdings margin
eq["available"]["intraday_payin"]
eq["utilised"]["debits"], eq["utilised"]["span"], eq["utilised"]["exposure"], eq["utilised"]["option_premium"]
```

Equity and commodity are separate pools at Zerodha — MCX orders use `margins("commodity")`.

## Order margins (single legs, independent)

```python
legs = [{
    "exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY",
    "variety": "regular", "product": "CNC", "order_type": "LIMIT",
    "quantity": 10, "price": 1500.0, "trigger_price": 0,
}]
r = kite.order_margins(legs)[0]
r["total"], r["span"], r["exposure"], r["option_premium"], r["var"], r["leverage"]
r["charges"]["total"]                # estimated brokerage + taxes for this leg
```

## Basket margins (spread benefit)

```python
r = kite.basket_order_margins(legs, consider_positions=True, mode="compact")
r["initial"]["total"]   # sum of legs independently
r["final"]["total"]     # after hedge benefit — this is what will be blocked
r["orders"]             # per-leg breakdown
```

- `consider_positions=True` includes existing open positions (realistic).
- For multi-leg option strategies always check `final.total` against `margins("equity")["net"]`.
- Execution tip: **buy the hedge legs first**, then sell — otherwise the short leg is margined naked
  and may be rejected.

## Pre-trade check pattern

```python
def can_afford(kite, legs):
    need = kite.basket_order_margins(legs, consider_positions=True)["final"]["total"]
    have = kite.margins("equity")["net"]
    return {"required": need, "available": have, "sufficient": have >= need, "shortfall": max(0, need - have)}
```

## Exact charges — virtual contract note

Kite can compute the real brokerage, STT, exchange charges, GST, SEBI fee and stamp duty for executed
(or hypothetical) orders:

```python
note = kite.get_virtual_contract_note([{
    "order_id": "111111111", "exchange": "NSE", "tradingsymbol": "INFY",
    "transaction_type": "BUY", "variety": "regular", "product": "CNC",
    "order_type": "LIMIT", "quantity": 10, "average_price": 1500.0,
}])
note[0]["charges"]  # {"transaction_tax", "transaction_tax_type", "exchange_turnover_charge",
                    #  "sebi_turnover_charge", "brokerage", "stamp_duty", "gst": {...}, "total"}
```

Prefer this over hand-rolled formulas for real P&L. For backtests where there is no order, use the
offline model in the **kite-backtest** skill (`scripts/charges.py`).

## Zerodha charge schedule (snapshot, Oct 2026 — verify at zerodha.com/charges)

| | Equity delivery | Equity intraday | Futures | Options |
|---|---|---|---|---|
| Brokerage | ₹0 | 0.03 % or ₹20 (lower) | 0.03 % or ₹20 (lower) | ₹20 flat / order |
| STT | 0.1 % buy & sell | 0.025 % sell | 0.05 % sell | 0.15 % sell (premium) |
| Exchange txn (NSE) | 0.00307 % | 0.00307 % | 0.00183 % | 0.03553 % (premium) |
| Exchange txn (BSE) | 0.00375 % | 0.00375 % | 0 | 0.0325 % (premium) |
| SEBI | ₹10 / crore | ₹10 / crore | ₹10 / crore | ₹10 / crore |
| Stamp (buy) | 0.015 % | 0.003 % | 0.002 % | 0.003 % |
| GST | 18 % on brokerage + exchange + SEBI | | | |
| DP charge | ₹15.34 per scrip per sell day | – | – | – |

Exercised long options also pay STT on intrinsic value. MIS auto square-off adds ₹50 + GST per order.
