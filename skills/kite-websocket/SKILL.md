---
name: kite-websocket
description: >
  Use when the user wants real-time data from Zerodha Kite Connect over
  WebSocket (KiteTicker): stream live LTP / quotes / 5-level market depth
  for NSE, BSE, NFO, BFO, MCX or CDS instruments; watch indices or option
  strikes live; build live 1-minute (or any N-second) candles from ticks;
  record ticks to disk; monitor order status updates in real time instead
  of polling; scale beyond 3,000 instruments across connections; debug
  disconnects, reconnects, stale feeds, Twisted reactor errors or
  timestamp issues. Triggers on "stream", "live ticks", "real-time",
  "websocket", "KiteTicker", "order updates", "live candles", "tick data"
  with a Zerodha/Kite account. UNOFFICIAL community skill — not affiliated
  with Zerodha.
compatibility: >
  Python 3.9+ and `pip install kiteconnect` (5.x, brings Twisted + Autobahn).
  Needs the Kite Connect (paid) plan — the free Personal plan has no
  WebSocket market data — plus a valid daily access token. WebSocket data
  works from any IP; only order endpoints need the whitelisted static IP.
---

# Kite WebSocket — Live Ticks, Depth, Candles & Order Updates

> **Unofficial**, community-maintained, not affiliated with Zerodha. Live data is for the account
> holder's own use — don't redistribute exchange data.

## Setup

```python
from scripts.kite_common import get_client, resolve_instrument
from scripts.tick_stream import TickStream

kite = get_client()                                  # KITE_API_KEY + KITE_ACCESS_TOKEN / login cache
tokens = [resolve_instrument(kite, s)["instrument_token"] for s in ("NSE:INFY", "NSE:NIFTY 50")]

stream = TickStream(kite.api_key, kite.access_token)
stream.subscribe(tokens, mode="full")                 # ltp | quote | full
stream.start()                                        # background thread, auto-reconnect
stream.wait_connected(10)

for received_at, tick in stream.iter_ticks(timeout=1):  # consume in YOUR thread
    print(tick["instrument_token"], tick["last_price"])
```

Login / token: use the **kite-connect** skill's `scripts/login.py` (tokens expire ~06:00 IST daily).

## Rules — Always Enforce

1. **Never do work inside callbacks.** KiteTicker callbacks run on the Twisted reactor thread; blocking
   there (REST calls, disk, `print` floods, `sleep`) stalls the feed and triggers ping timeouts.
   `TickStream` only enqueues — process ticks in your own thread.
2. **Never call `kws.stop()` / `reactor.stop()` unless the process is exiting.** The Twisted reactor
   can't be restarted (`ReactorNotRestartable`). Use `close()`.
3. **Subscribe/unsubscribe from other threads only via the reactor** (`reactor.callFromThread`).
   `TickStream.subscribe()` does this for you.
4. **No orders from a tick callback** unless the user explicitly approved a written rule (entry, size,
   max orders, max loss, stop time). Even then: debounce, ≤ 10 orders/s, one position per signal, and a
   kill switch. See [references/trading-on-ticks.md](references/trading-on-ticks.md).
5. Respect limits: **3 connections per api_key, 3,000 instruments per connection.** Prefer `ltp`/`quote`
   mode for wide watchlists; use `full` only where you need depth/OI/timestamps.
6. Credentials from environment only; never print the access token (it's in the WebSocket URL — don't
   log URLs).
7. Restart the stream after the daily re-login — old tokens stop working ~06:00 IST.

## Limits & Modes

| Item | Value |
|---|---|
| Endpoint | `wss://ws.kite.trade?api_key=…&access_token=…` |
| Connections per api_key | 3 |
| Instruments per connection | 3,000 |
| Default mode after `subscribe` | `quote` |

| Mode | Tradable fields | Index fields |
|---|---|---|
| `ltp` | token, `last_price` | same |
| `quote` | + `last_traded_quantity`, `average_traded_price`, `volume_traded`, `total_buy_quantity`, `total_sell_quantity`, `ohlc`, `change` | + `ohlc`, `change` |
| `full` | + `last_trade_time`, `exchange_timestamp`, `oi`, `oi_day_high`, `oi_day_low`, `depth` (5 × buy/sell) | + `exchange_timestamp` |

Full schema: [references/tick-schema.md](references/tick-schema.md).

## High-Value Gotchas

- **Timestamps are naive and in the *machine's* local timezone** (`datetime.fromtimestamp`). On a UTC
  server 09:15 IST shows as 03:45. Always convert with `scripts/tick_utils.to_ist()`.
- `quote` mode has **no timestamp**; bar-building on quote ticks uses receive time.
- `volume_traded` is **cumulative for the day** — bar volume is the difference between ticks.
- `ohlc.close` is the **previous day's close**; `change` is % vs that.
- Ticks arrive only when something changes. Illiquid strikes may be silent for minutes — use
  `stream.stale_tokens(...)` before concluding the feed is dead.
- KiteTicker resubscribes automatically after reconnect; `on_connect` fires again on every reconnect.
- **Order updates** (`on_order_update`) come as text frames on every connection — `TickStream` listens on
  the first connection only, so you don't get duplicates.
- One process = one reactor. Multiple `KiteTicker` objects share it; additional connections must be
  started from the reactor thread (`TickStream` handles it).
- `kws.connect()` without `threaded=True` **blocks forever** — fine for a script, wrong for an agent
  that needs to keep working.

## Helpers

| Module | Use |
|---|---|
| `scripts/tick_stream.py` | `TickStream`: thread-safe subscribe/unsubscribe, sharding over up to 3 connections, bounded queue (drops oldest, counts drops), `latest` snapshot, order-update queue, health/stale checks |
| `scripts/bars.py` | `BarBuilder`: N-second candles from ticks, session-anchored (09:15) buckets, cumulative-volume diffing, timer `flush()` |
| `scripts/tick_utils.py` | `to_ist`, `tick_time`, `best_bid_ask`, `mid`, `spread_bps`, `book_imbalance`, `flatten` |
| `scripts/recorder.py` | `TickRecorder`: daily-rotating JSONL tick logs; `read_ticks()` to replay |
| `scripts/kite_common.py` | `get_client`, `resolve_instrument("NFO:…")`, cached instruments |

## Core Patterns

### Latest snapshot (dashboards, quick answers)

```python
stream.subscribe(tokens, "quote"); stream.start(); stream.wait_connected(10)
import time; time.sleep(2)
for tok, t in stream.latest.items():
    print(tok, t["last_price"], f"{t.get('change', 0):+.2f}%")
```

### Live candles

```python
from scripts.bars import BarBuilder
bb = BarBuilder(interval=60)                        # 1-minute, anchored at 09:15 IST
for received_at, tick in stream.iter_ticks(timeout=1):
    for bar in bb.update(tick, received_at):
        print(bar)                                   # {"token","start","end","open","high","low","close","volume","oi","ticks"}
    for bar in bb.flush():                           # closes bars of silent instruments
        print(bar)
```

### Order updates only

```python
stream = TickStream(kite.api_key, kite.access_token)  # no subscriptions needed
stream.start()
upd = stream.order_updates.get()                      # dict like an order-book row
print(upd["order_id"], upd["status"], upd.get("status_message"))
```

### Depth analytics

```python
from scripts.tick_utils import best_bid_ask, spread_bps, book_imbalance
t = stream.latest[token]                              # needs mode="full"
bid, ask = best_bid_ask(t); print(spread_bps(t), book_imbalance(t))
```

## Reference Files

| Need | File |
|---|---|
| Connection lifecycle, reconnects, reactor & threading, multiple connections, asyncio bridge | [references/connection-and-threading.md](references/connection-and-threading.md) |
| Every tick field per mode, index vs tradable, binary packet layout, text messages | [references/tick-schema.md](references/tick-schema.md) |
| Bars, recording, option-chain streaming, health monitoring, daily restart | [references/patterns.md](references/patterns.md) |
| Rules for acting on ticks (orders), throttling, kill switch | [references/trading-on-ticks.md](references/trading-on-ticks.md) |

Examples: `stream_quotes.py` (live table), `live_candles.py`, `order_updates.py`, `record_ticks.py`,
`watch_levels.py` (local price alerts, no orders).
