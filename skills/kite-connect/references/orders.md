# Orders

## place_order

```python
order_id = kite.place_order(
    variety="regular",             # regular | amo | iceberg | auction | co
    exchange="NSE",                # NSE BSE NFO BFO MCX CDS BCD
    tradingsymbol="INFY",
    transaction_type="BUY",        # BUY | SELL
    quantity=1,                    # shares, or contracts (multiple of lot_size) for F&O
    product="CNC",                 # CNC | MIS | NRML | MTF
    order_type="LIMIT",            # MARKET | LIMIT | SL | SL-M
    price=1500.0,                  # LIMIT and SL
    trigger_price=None,            # SL and SL-M
    validity="DAY",                # DAY | IOC | TTL
    validity_ttl=None,             # minutes, with validity=TTL
    disclosed_quantity=None,       # equity only, ≥ 10 % of quantity
    iceberg_legs=None,             # 2–50, variety=iceberg
    iceberg_quantity=None,         # quantity / iceberg_legs
    auction_number=None,           # variety=auction
    market_protection=None,        # MARKET / SL-M: -1 auto, or (0, 100] %
    tag="kiteskill",               # ≤ 20 alphanumeric chars
    algo_id=None,                  # exchange-registered algo id (only if you have one)
)
```

Returns the `order_id` string. **This does not mean the order executed.** Check:

```python
hist = kite.order_history(order_id)       # chronological list of state changes
final = hist[-1]
final["status"], final["status_message"], final["filled_quantity"], final["average_price"]
```

### Field rules

| Field | Rule |
|---|---|
| `product` | `CNC` (delivery) / `MTF` (margin trading) only on NSE/BSE cash. `NRML` only on F&O, MCX, currency. `MIS` = intraday anywhere |
| `price` | Must be a multiple of `tick_size` (0.05 for most stocks/options, 0.01 for some). Within circuit limits |
| `trigger_price` | BUY SL: trigger ≤ price, trigger above LTP. SELL SL: trigger ≥ price, trigger below LTP |
| `market_protection` | **Mandatory** for `MARKET` and `SL-M`. `-1` = exchange-defined protection; `0` is rejected. Converts to a protected limit; exchange LPP bands still apply |
| `quantity` | F&O: multiple of `lot_size`. Above freeze quantity → `place_autoslice_order` |
| `tag` | Alphanumeric, ≤ 20 chars. Shows up in order book and postbacks |
| `validity=IOC` | Unfilled part cancels immediately |
| `validity=TTL` | Order auto-cancels after `validity_ttl` minutes (equity) |

### Order types

| Type | Needs | Use |
|---|---|---|
| `LIMIT` | `price` | Default for this skill |
| `MARKET` | `market_protection` | Only when user explicitly asks |
| `SL` | `price` + `trigger_price` | Stop-loss limit |
| `SL-M` | `trigger_price` + `market_protection` | Stop-loss market |

### Varieties

| Variety | Notes |
|---|---|
| `regular` | Normal order during market hours |
| `amo` | After-market order, queued for next session open. Use when market is closed |
| `iceberg` | Splits a large order into 2–50 visible legs; needs `iceberg_legs`, `iceberg_quantity` |
| `auction` | Participate in exchange buy-in auctions for your holdings; `auction_number` from `get_auction_instruments()` |
| `co` | Cover order (entry + compulsory SL). Legacy — prefer regular + SL/GTT |

## place_autoslice_order

Same parameters as `place_order`. Splits quantity above the exchange freeze limit into slices (max 10).
Returns a list where each item is either `{"order_id": ...}` or an error object — check every element.

```python
resp = kite.place_autoslice_order(variety="regular", exchange="NFO", tradingsymbol=sym,
                                  transaction_type="BUY", quantity=lot * 40, product="NRML",
                                  order_type="LIMIT", price=101.5, tag="kiteskill")
failed = [r for r in resp if "order_id" not in r]
```

## modify_order

```python
kite.modify_order(variety="regular", order_id=oid, quantity=2, price=1498.0,
                  order_type="LIMIT", trigger_price=None, validity="DAY",
                  disclosed_quantity=None, market_protection=None)
```

- Only `OPEN` / `TRIGGER PENDING` orders can be modified.
- Max 25 modifications per order; then cancel + re-place.
- Pass the order's own `variety`.

## cancel_order / exit_order

```python
kite.cancel_order(variety="regular", order_id=oid)
kite.exit_order(variety="co", order_id=child_oid, parent_order_id=parent_oid)  # CO legs
```

To **exit a position**, place an opposite order (same product, same quantity) — `exit_order` is not for that.

## Order book & trades

```python
kite.orders()                  # all orders today (incl. rejected/cancelled)
kite.order_history(order_id)   # state transitions
kite.trades()                  # all fills today
kite.order_trades(order_id)    # fills for one order
```

Important order fields: `order_id`, `exchange_order_id`, `parent_order_id`, `status`, `status_message`,
`tradingsymbol`, `exchange`, `instrument_token`, `transaction_type`, `order_type`, `product`, `variety`,
`validity`, `price`, `trigger_price`, `average_price`, `quantity`, `filled_quantity`, `pending_quantity`,
`cancelled_quantity`, `order_timestamp`, `exchange_timestamp`, `tag`, `guid`.

## Statuses

Final: `COMPLETE`, `CANCELLED`, `REJECTED`, plus `OPEN` (resting), `TRIGGER PENDING` (SL waiting).

Transient: `PUT ORDER REQ RECEIVED`, `VALIDATION PENDING`, `OPEN PENDING`, `MODIFY VALIDATION PENDING`,
`MODIFY PENDING`, `CANCEL PENDING`, `AMO REQ RECEIVED`, `MODIFIED`.

### Wait-for-final helper

```python
import time
FINAL = {"COMPLETE", "CANCELLED", "REJECTED", "OPEN", "TRIGGER PENDING"}

def wait_status(kite, order_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        st = kite.order_history(order_id)[-1]
        if st["status"] in FINAL:
            return st
        time.sleep(0.5)
    return st
```

For many orders, use WebSocket `on_order_update` instead of polling ([websocket.md](websocket.md)).

## Trigger range

```python
kite.trigger_range("BUY", "NSE:INFY", "NFO:NIFTY25OCT25000CE")
```

Returns allowed trigger price bands — useful before SL orders on illiquid instruments.

## Confirmation template

Before any state-changing call, show:

```
BUY 1 × NSE:INFY  LIMIT 1,498.00  CNC  DAY  tag=kiteskill
≈ ₹1,498.00   |  warnings: none
Proceed? (yes/no)
```

and use `scripts/validate_order.format_preview()` for the exact ticket.
