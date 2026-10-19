# GTT (Good Till Triggered) & Alerts

## GTT

Server-side triggers valid for up to **1 year**. When LTP crosses a trigger, Kite places the attached
**LIMIT** order. A trigger firing ≠ order filled (the limit may not fill, or can be rejected for margin).

| Type | Constant | trigger_values | orders |
|---|---|---|---|
| Single | `GTT_TYPE_SINGLE` = `"single"` | `[trigger]` | 1 order |
| OCO (two-leg) | `GTT_TYPE_OCO` = `"two-leg"` | `[stoploss_trigger, target_trigger]` (ascending) | 2 orders, same order |

Rules:
- GTT orders must be `order_type="LIMIT"`.
- `last_price` = current LTP (used to validate trigger direction).
- Trigger must differ from LTP by a minimum gap (≈0.25 %) or it is rejected.
- OCO is typically used to exit an existing holding/position: stop-loss below, target above.
- Product: `CNC` for equity, `NRML` (or `MIS`) for F&O.

### Single: buy on dip

```python
ltp = kite.ltp("NSE:INFY")["NSE:INFY"]["last_price"]
trigger_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_SINGLE,
    tradingsymbol="INFY", exchange="NSE",
    trigger_values=[1400.0], last_price=ltp,
    orders=[{"transaction_type": "BUY", "quantity": 1, "order_type": "LIMIT",
             "product": "CNC", "price": 1401.0}],
)["trigger_id"]
```

### OCO: stop-loss + target on a holding

```python
kite.place_gtt(
    trigger_type=kite.GTT_TYPE_OCO,
    tradingsymbol="INFY", exchange="NSE",
    trigger_values=[1350.0, 1650.0], last_price=ltp,
    orders=[
        {"transaction_type": "SELL", "quantity": 10, "order_type": "LIMIT", "product": "CNC", "price": 1345.0},
        {"transaction_type": "SELL", "quantity": 10, "order_type": "LIMIT", "product": "CNC", "price": 1650.0},
    ],
)
```

### Manage

```python
kite.get_gtts()                      # all GTTs (active + recent history)
kite.get_gtt(trigger_id)
kite.modify_gtt(trigger_id, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)
kite.delete_gtt(trigger_id)
```

GTT statuses: `active`, `triggered`, `disabled`, `expired`, `cancelled`, `rejected`, `deleted`.
`modify_gtt` replaces the whole definition — send all fields again.

## Alerts (REST — not in pykiteconnect)

Up to **500 active alerts** per user. Two types:

| type | Behaviour |
|---|---|
| `simple` | Notification only (Kite app / email) |
| `ato` | *Alert Triggers Order* — places the attached `basket` of orders when it fires. Treat like an order: preview + confirm |

Endpoints (base `https://api.kite.trade`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/alerts` | Create |
| GET | `/alerts?status=enabled&page=1&page_size=50` | List |
| GET | `/alerts/{uuid}` | One alert |
| PUT | `/alerts/{uuid}` | Modify |
| DELETE | `/alerts?uuid={uuid}` | Delete (repeat `uuid` for many) |
| GET | `/alerts/{uuid}/history` | Trigger history |

Parameters:

| Param | Values |
|---|---|
| `name` | Free text |
| `type` | `simple` / `ato` |
| `lhs_exchange` | `NSE` `BSE` `NFO` `BFO` `CDS` `BCD` `MCX` `INDICES` |
| `lhs_tradingsymbol` | e.g. `INFY`, `NIFTY 50` |
| `lhs_attribute` | `LastTradedPrice` |
| `operator` | `<=` `>=` `<` `>` `==` |
| `rhs_type` | `constant` or `instrument` |
| `rhs_constant` | number (when `rhs_type=constant`) |
| `rhs_exchange`, `rhs_tradingsymbol`, `rhs_attribute` | when comparing two instruments |
| `basket` | JSON string of orders (required for `ato`) |

Statuses: `enabled`, `disabled`, `deleted`.

```python
from scripts.kite_client import get_client, alerts_request
kite = get_client()

alert = alerts_request(kite, "POST", params={
    "name": "NIFTY above 26000", "type": "simple",
    "lhs_exchange": "INDICES", "lhs_tradingsymbol": "NIFTY 50", "lhs_attribute": "LastTradedPrice",
    "operator": ">=", "rhs_type": "constant", "rhs_constant": 26000,
})
alerts_request(kite, "GET", params={"status": "enabled"})
alerts_request(kite, "DELETE", params={"uuid": alert["uuid"]})
```

## GTT vs Alert vs SL order

| Need | Use |
|---|---|
| Stop-loss for today's intraday trade | `SL` / `SL-M` order |
| Stop-loss + target on a long-term holding | GTT OCO |
| Buy if price dips over the next weeks | GTT single |
| Just notify me | Alert `simple` |
| Fire a multi-leg basket on a condition (incl. index level) | Alert `ato` |
