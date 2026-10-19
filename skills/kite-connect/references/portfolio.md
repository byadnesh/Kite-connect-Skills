# Portfolio: Holdings & Positions

## Holdings (delivery, T+1 settled and T1)

```python
for h in kite.holdings():
    print(h["tradingsymbol"], h["quantity"], h["t1_quantity"], h["average_price"], h["last_price"], h["pnl"])
```

Useful fields: `tradingsymbol`, `exchange`, `instrument_token`, `isin`, `product` (`CNC`),
`quantity` (settled), `t1_quantity` (bought yesterday, unsettled), `realised_quantity`,
`collateral_quantity`, `collateral_type`, `used_quantity`, `average_price`, `last_price`,
`close_price`, `pnl`, `day_change`, `day_change_percentage`, `authorised_quantity` (eDIS / DDPI).

Total quantity you can sell today = `quantity + t1_quantity - used_quantity` (minus pledged / already-sold).

Portfolio summary:

```python
H = kite.holdings()
invested = sum(h["average_price"] * (h["quantity"] + h["t1_quantity"]) for h in H)
current  = sum(h["last_price"]    * (h["quantity"] + h["t1_quantity"]) for h in H)
day_pnl  = sum(h["day_change"]    * (h["quantity"] + h["t1_quantity"]) for h in H)
print(f"Invested ₹{invested:,.0f}  Current ₹{current:,.0f}  P&L ₹{current-invested:,.0f}  Today ₹{day_pnl:,.0f}")
```

### Selling holdings (DDPI / eDIS)

If the user has not given DDPI/POA, a CNC sell needs CDSL TPIN authorisation in Kite first. A sell
without it is rejected with a "holdings not authorised" style message — tell the user to authorise on
kite.zerodha.com (Holdings → Authorise). The API cannot do this step.

### Auction holdings

```python
kite.get_auction_instruments()   # holdings currently in an exchange buy-in auction
```

## Positions (intraday + carry-forward F&O)

```python
pos = kite.positions()
pos["net"]   # cumulative net position per instrument/product — use this for P&L and exits
pos["day"]   # only today's buys/sells
```

Fields: `tradingsymbol`, `exchange`, `instrument_token`, `product`, `quantity` (signed: + long / − short),
`overnight_quantity`, `multiplier`, `average_price`, `last_price`, `close_price`, `value`,
`pnl`, `m2m`, `unrealised`, `realised`, `buy_quantity`, `buy_price`, `buy_value`, `sell_quantity`,
`sell_price`, `sell_value`, `day_buy_*`, `day_sell_*`.

Open positions only:

```python
open_pos = [p for p in kite.positions()["net"] if p["quantity"] != 0]
total_pnl = sum(p["pnl"] for p in kite.positions()["net"])
```

### Square off one position

```python
p = open_pos[0]
side = "SELL" if p["quantity"] > 0 else "BUY"
order = dict(variety="regular", exchange=p["exchange"], tradingsymbol=p["tradingsymbol"],
             transaction_type=side, quantity=abs(p["quantity"]), product=p["product"],
             order_type="LIMIT", price=p["last_price"], tag="kiteskill")
# validate → preview → confirm → place
```

"Square off everything" is a high-risk bulk action: list every leg, total P&L impact, then require one
explicit confirmation for the whole list. Close **short options before long hedges** to avoid a margin
spike.

## Convert position

```python
kite.convert_position(
    exchange="NSE", tradingsymbol="INFY",
    transaction_type="BUY",          # side of the existing position
    position_type="day",             # day | overnight
    quantity=10,
    old_product="MIS", new_product="CNC",
)
```

Common conversions: `MIS → CNC` (keep intraday buy as delivery; needs full cash), `CNC → MIS`,
`MIS ↔ NRML` for F&O. Confirm first — it changes margin requirements immediately.

## Holdings vs positions quick answer

| User asks | Call |
|---|---|
| "my stocks / long-term portfolio" | `holdings()` |
| "today's trades P&L", "F&O positions" | `positions()["net"]` |
| "what did I buy today" | `positions()["day"]` or `trades()` |
| "mutual funds" | `mf_holdings()` |
