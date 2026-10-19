# Mutual Funds (Coin) via Kite Connect

Orders go to Zerodha Coin. NAV-based, settles T+1/T+2+. Same confirmation rules as equity orders.

## Discover schemes

```python
funds = kite.mf_instruments()
direct_growth = [f for f in funds
                 if "parag parikh flexi" in f["name"].lower()
                 and f["plan"] == "direct" and f["dividend_type"] == "growth"]
```

Fields: `tradingsymbol` (ISIN), `name`, `fund_house`, `scheme_type`, `plan` (`direct`/`regular`),
`dividend_type` (`growth`/`payout`/`reinvest`), `minimum_purchase_amount`,
`minimum_additional_purchase_amount`, `purchase_allowed`, `redemption_allowed`, `last_price` (NAV),
`last_price_date`, `settlement_type`.

## Orders

```python
# Buy by amount
kite.place_mf_order(tradingsymbol="INF879O01027", transaction_type="BUY", amount=5000, tag="kiteskill")
# Redeem by units
kite.place_mf_order(tradingsymbol="INF879O01027", transaction_type="SELL", quantity=12.345)

kite.mf_orders()                 # list
kite.mf_orders(order_id)         # one
kite.cancel_mf_order(order_id)   # only while still open
```

BUY uses `amount`; SELL uses `quantity` (units).

## SIPs

```python
sip = kite.place_mf_sip(tradingsymbol="INF879O01027", amount=2000, instalments=-1,   # -1 = perpetual
                        frequency="monthly", instalment_day=5, initial_amount=None, tag="kiteskill")
kite.mf_sips()
kite.modify_mf_sip(sip_id, amount=3000, status="active")   # status: active | paused
kite.cancel_mf_sip(sip_id)
```

`frequency`: `weekly`, `monthly`, `quarterly`.

## Holdings

```python
for h in kite.mf_holdings():
    print(h["fund"], h["quantity"], h["average_price"], h["last_price"], h["pnl"])
```

## Agent rules

- Confirm scheme name + plan (direct vs regular) + amount before placing — ISINs are easy to confuse.
- Show the exit load / lock-in caveat (ELSS = 3-year lock-in) when redeeming.
