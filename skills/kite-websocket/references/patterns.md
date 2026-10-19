# Streaming Patterns

## 1. Watchlist snapshot

```python
stream = TickStream(kite.api_key, kite.access_token)
stream.subscribe(tokens, "quote")
stream.start(); stream.wait_connected(10)
time.sleep(2)                                   # let first ticks arrive
snapshot = dict(stream.latest)                  # token -> last tick
```

Faster and cheaper than REST `quote()` for > 1 refresh/second; REST is simpler for a one-off answer.

## 2. Live candles

`scripts/bars.BarBuilder(interval=seconds, anchor=time(9, 15))`

- Buckets are anchored to the session open so 15/30/60-minute bars line up with Kite's historical
  candles (09:15, 09:45, 10:15 … for 30-minute). For MCX use `anchor=time(9, 0)`.
- `update(tick, received_at)` returns bars that **closed** because a tick for a later bucket arrived.
- `flush(now)` closes bars whose bucket ended — call it every second from your loop so illiquid
  instruments still emit bars.
- Volume = difference of cumulative `volume_traded` (first tick of the day contributes 0).
- Minutes with no ticks produce **no bar** (no forward-fill). Forward-fill yourself if a strategy needs
  a regular grid.
- Use `mode="full"` for exchange timestamps; with `quote` the builder uses receive time.

Seed indicators with history so they're valid from the first live bar:

```python
hist = kite.historical_data(token, from_dt, to_dt, "minute")   # kite-connect / kite-backtest
closes = [c["close"] for c in hist]
```

## 3. Recording ticks

```python
from scripts.recorder import TickRecorder, read_ticks
rec = TickRecorder("ticks/")                     # ticks/ticks_YYYYMMDD.jsonl, rotates at IST midnight
for received_at, tick in stream.iter_ticks(timeout=1):
    rec.write(received_at, tick)
rec.close()

for row in read_ticks("ticks/ticks_20261020.jsonl"):
    ...
```

Rows are flattened (`token, ts, recv, ltp, ltq, atp, volume, oi, bid, ask, bid_qty, ask_qty, buy_qty,
sell_qty`). Use this to build your own option history — Kite has no expired-options data.

Don't commit recordings or share them publicly (exchange data licensing).

## 4. Streaming an option chain

1. Resolve strikes around ATM from the NFO dump (see kite-options `build_chain`, or filter
   `load_instruments(kite, "NFO")` by `name`, `expiry`, `strike`).
2. Subscribe CE + PE tokens in `quote` (or `full` for depth/OI), the underlying index in `full`.
3. Keep `stream.latest`; recompute IV/Greeks on a timer (e.g. every 1–2 s), not per tick.
4. Re-centre: when spot moves more than N strikes, `subscribe` the new strikes and `unsubscribe` the far ones.

A ±20-strike chain for one expiry = 82 instruments — trivial for one connection.

## 5. Order-update monitor

```python
stream.start()
while True:
    u = stream.order_updates.get()
    if u.get("tag") != "kiteskill":
        continue
    print(u["order_id"], u["status"], u["filled_quantity"], u["average_price"], u.get("status_message"))
```

Use this instead of polling `order_history()` after placing orders.

## 6. Health monitoring

```python
stream.health()              # per connection: connected, tokens, reconnects, last tick age; queue size; drops
stream.stale_tokens(30)      # tokens with no tick for 30 s (during market hours that's suspicious for liquid names)
```

Rules of thumb:
- No ticks at all for > 15 s during market hours on liquid instruments → feed problem; check `health()`.
- `dropped > 0` → consumer too slow; lighten processing or use `ltp` mode.
- `on_noreconnect` fired → usually an expired/invalid token. Re-login and restart.

## 7. Daily lifecycle

```
08:55  login (kite-connect/scripts/login.py) → new access token
09:00  start stream, subscribe
...    process
15:35  (equity) close stream, flush bars, close recorder
~06:00 next day: token expires — never reuse it
```

Long-running services should exit after the session and be restarted by a scheduler after login, rather
than trying to swap tokens inside a live reactor.
