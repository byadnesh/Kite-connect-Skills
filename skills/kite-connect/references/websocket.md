# WebSocket Streaming (KiteTicker)

> Quick start only. For anything long-running — thread-safe subscriptions, > 3,000 instruments, live
> candles, tick recording, reconnect/stale-feed handling — use the **kite-websocket** skill.

Needs the Connect plan. Endpoint: `wss://ws.kite.trade?api_key=...&access_token=...`.

| Limit | Value |
|---|---|
| Connections per api_key | 3 |
| Instruments per connection | 3,000 |
| Subscribe by | integer `instrument_token` |

## Modes

| Mode | Constant | Contents |
|---|---|---|
| `ltp` | `MODE_LTP` | token + last price |
| `quote` | `MODE_QUOTE` | LTP, last qty, avg price, volume, buy/sell qty, OHLC, change |
| `full` | `MODE_FULL` | quote + OI (+ day high/low), last trade time, exchange timestamp, 5-level depth |

Indices send a shorter packet: LTP, OHLC, change (+ exchange timestamp in full). No volume/depth/OI.

## Minimal streamer

```python
import logging, os
from kiteconnect import KiteTicker

logging.basicConfig(level=logging.INFO)
kws = KiteTicker(os.environ["KITE_API_KEY"], os.environ["KITE_ACCESS_TOKEN"],
                 reconnect=True, reconnect_max_tries=50, reconnect_max_delay=60)
TOKENS = [256265, 738561]       # NIFTY 50, RELIANCE

def on_connect(ws, response):
    ws.subscribe(TOKENS)
    ws.set_mode(ws.MODE_FULL, TOKENS)

def on_ticks(ws, ticks):
    for t in ticks:
        print(t["instrument_token"], t["last_price"], t.get("volume_traded"))

def on_order_update(ws, data):
    print("ORDER", data["order_id"], data["status"], data.get("status_message"))

def on_close(ws, code, reason):
    logging.warning("closed %s %s", code, reason)

def on_error(ws, code, reason):
    logging.error("error %s %s", code, reason)

kws.on_connect = on_connect
kws.on_ticks = on_ticks
kws.on_order_update = on_order_update
kws.on_close = on_close
kws.on_error = on_error
kws.on_reconnect = lambda ws, n: logging.info("reconnecting #%s", n)
kws.on_noreconnect = lambda ws: logging.error("gave up reconnecting")

kws.connect()                  # blocks; use connect(threaded=True) to keep the main thread
```

Don't call `ws.stop()` inside `on_close` if you want auto-reconnect. Look up a token from a symbol with
`scripts/instruments.find_equity(kite, "RELIANCE")["instrument_token"]`.

## Tick schema (full mode, tradable)

```python
{
  "tradable": True, "mode": "full", "instrument_token": 738561,
  "last_price": 2950.5, "last_traded_quantity": 5, "average_traded_price": 2944.1,
  "volume_traded": 3120456, "total_buy_quantity": 412300, "total_sell_quantity": 398120,
  "ohlc": {"open": 2930.0, "high": 2961.0, "low": 2925.2, "close": 2928.4},
  "change": 0.75,                      # % vs previous close
  "last_trade_time": datetime, "exchange_timestamp": datetime,
  "oi": 0, "oi_day_high": 0, "oi_day_low": 0,
  "depth": {"buy": [{"price", "quantity", "orders"} × 5], "sell": [... × 5]},
}
```

## Order updates

Text frames with `type: "order"` arrive for every status change of orders placed with this api_key
(and the account). Payload = same shape as postbacks / order book row. Use it instead of polling
`order_history()`.

## Patterns

- **Threaded + queue:** `kws.connect(threaded=True)`, push ticks into `queue.Queue`, consume in main loop.
- **Change subscriptions live:** call `kws.subscribe([...])` / `kws.unsubscribe([...])` /
  `kws.set_mode(...)` from any thread after connect.
- **Bar building:** aggregate `last_price` by minute bucket of `exchange_timestamp`; don't trust local clock.
- **Never place orders from inside `on_ticks` without throttling** — a fast market can fire hundreds of
  ticks/second and blow through the 10 orders/sec cap (and your capital).
