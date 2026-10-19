# Connection Lifecycle, Reconnects & Threading

## How KiteTicker works under the hood

- Built on **Twisted** + **Autobahn**. All sockets run on one global Twisted *reactor* (event loop).
- `kws.connect()` creates a WebSocket factory, calls `connectWS(...)`, then **runs the reactor** if it
  isn't running yet:
  - `connect()` → `reactor.run()` in the calling thread — **blocks forever**.
  - `connect(threaded=True)` → `reactor.run()` in a daemon thread (signal handlers disabled), returns.
- The reactor can run **once per process**. After `kws.stop()` (= `reactor.stop()`) any further
  connect raises `twisted.internet.error.ReactorNotRestartable`. To reconnect after stopping, start a
  new process.
- Callbacks (`on_ticks`, `on_connect`, `on_close`, `on_error`, `on_reconnect`, `on_noreconnect`,
  `on_order_update`, `on_message`) execute **on the reactor thread**.

## Callback order

```
connect() ─► onConnect  ─► on_connect(ws, response)     ← subscribe here on first connect
          ─► onOpen     ─► (on reconnect) ws.resubscribe()   ← automatic, uses ws.subscribed_tokens
          ─► onMessage  ─► binary → on_ticks(ws, [tick, ...])   (1-byte heartbeats are ignored)
                         text   → {"type": "order"} → on_order_update(ws, data)
                                  {"type": "error"} → on_error(ws, 0, message)
                                  {"type": "message"} → informational
connection lost ─► on_close(ws, code, reason) ─► on_reconnect(ws, attempt) … ─► on_connect again
gave up         ─► on_noreconnect(ws)
```

## Reconnect settings

```python
KiteTicker(api_key, access_token, reconnect=True,
           reconnect_max_tries=50,    # capped at 300 by the SDK
           reconnect_max_delay=60,    # seconds, min 5; exponential backoff
           connect_timeout=30)
```

- The client pings every few seconds and drops the connection if pongs stop — a stalled reactor thread
  (blocking callback) looks like a network failure.
- `kws.stop_retry()` stops ongoing retries; `kws.close()` = `stop_retry()` + close frame.
- A rejected token (expired after 06:00 IST, or invalidated) makes every retry fail → eventually
  `on_noreconnect`. Fix: re-login, restart the stream.

## Thread safety

Twisted APIs are **not thread-safe**. `kws.subscribe/unsubscribe/set_mode` send frames on the socket; call
them from the reactor thread:

```python
from twisted.internet import reactor
reactor.callFromThread(kws.subscribe, [738561])
reactor.callFromThread(kws.set_mode, kws.MODE_FULL, [738561])
```

Inside callbacks (already on the reactor thread) call them directly. `TickStream` wraps all of this.

## The consumer pattern (what `TickStream` does)

```python
import queue
q = queue.Queue(maxsize=200_000)

def on_ticks(ws, ticks):          # reactor thread: enqueue only
    for t in ticks:
        try:
            q.put_nowait(t)
        except queue.Full:
            q.get_nowait(); q.put_nowait(t)   # drop oldest, keep newest

kws.on_ticks = on_ticks
kws.connect(threaded=True)

while True:                       # your thread: do the work
    t = q.get()
    ...
```

Keep the queue bounded: if your consumer is slower than the feed you want to lose old ticks, not run
out of memory. `TickStream.stats["dropped"]` tells you if it happens.

## Multiple connections (> 3,000 instruments)

- Up to 3 connections per api_key → 9,000 instruments.
- All share the one reactor. Start the first with `connect(threaded=True)`, then start the others
  **from the reactor thread**: `reactor.callFromThread(kws2.connect, threaded=True)` (inside the
  reactor `reactor.running` is True, so KiteTicker only opens the socket).
- Order updates are delivered on each connection; listen on one to avoid duplicates.
- Shard by usage, e.g. connection 1 = index + futures in `full`, connections 2–3 = option chain in `quote`.

## asyncio bridge

```python
import asyncio

async def tick_consumer(stream):
    loop = asyncio.get_running_loop()
    while True:
        received_at, tick = await loop.run_in_executor(None, stream.ticks.get)
        ...
```

Or forward from the reactor thread with `loop.call_soon_threadsafe(async_queue.put_nowait, tick)`.

## Jupyter

The reactor runs in a thread, so `connect(threaded=True)` works in notebooks. Re-running the cell that
calls `connect()` again is fine while the reactor is alive; restarting after `stop()` needs a kernel
restart.

## Networking

- WebSocket data is **not** subject to the static-IP whitelist (only order endpoints are).
- Corporate proxies: `kws.connect(threaded=True, proxy={"host": "...", "port": 3128})`.
- Don't log the connection URL — it contains the access token.
