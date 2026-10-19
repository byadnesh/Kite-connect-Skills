# Acting on Ticks (Orders From a Live Feed)

Tick-driven order placement is where agents and bots lose money fastest. This skill's default is
**observe and alert only**. Place orders from a live feed only when the user has explicitly approved
a written rule.

## Before writing any tick-triggered order code, get the user to confirm

| Item | Example |
|---|---|
| Instrument(s) | `NFO:NIFTY26OCTFUT` only |
| Trigger | 1-minute close above 25,200 |
| Action | BUY 1 lot, LIMIT at ask + 1 tick, product NRML |
| Exit | SL 25,120 (SL order), target 25,350 |
| Max orders | 4 per day |
| Max loss | ₹5,000 per day → stop trading |
| Active window | 09:20–15:00 IST |
| Kill switch | Ctrl+C or file `STOP` cancels open orders and stops |

Restate it back and ask for "yes". That approval covers only that rule.

## Implementation rules

1. **Decide on bars, not raw ticks** (e.g. 1-minute close from `BarBuilder`) to avoid flicker
   triggers. If you must use ticks, require the condition to hold for N ticks / T seconds.
2. **Never call REST from the reactor thread.** Signal in your consumer thread; place orders there.
3. **One in-flight order per signal.** Track state: `IDLE → PENDING → IN_POSITION → EXITING`. Ignore new
   signals while `PENDING`.
4. **Confirm fills via `stream.order_updates`** (filter by `tag`), not by assuming success.
5. **Throttle**: ≤ 10 orders/second (exchange rule), and keep a per-day order counter.
6. **Validate every order** with kite-connect `scripts/validate_order.py` and journal it with
   `scripts/trade_journal.py`.
7. **Market orders** need `market_protection=-1`; prefer LIMIT.
8. **Stale-data guard**: don't act if the triggering tick is older than ~2 s (`tick_time` vs now) or if
   the stream reconnected within the last few seconds.
9. **Kill switch**: on stop, cancel open orders, optionally flatten MIS, log, exit.
10. Orders still go only from the user's whitelisted static IP.

## Skeleton

```python
import time
from scripts.bars import BarBuilder

state, orders_today, MAX_ORDERS = "IDLE", 0, 4
bb = BarBuilder(60)

for received_at, tick in stream.iter_ticks(timeout=1):
    bars = bb.update(tick, received_at) + bb.flush()
    for bar in bars:
        if bar["token"] != FUT_TOKEN or state != "IDLE" or orders_today >= MAX_ORDERS:
            continue
        if bar["close"] > 25200:
            order = {...}                                  # build LIMIT order
            report = validate_order(order, instrument=inst, ltp=bar["close"])
            if report["ok"]:
                oid = kite.place_order(**order); orders_today += 1; state = "PENDING"
                log_action("place", order, order_id=oid, note="rule: 1m close > 25200 (approved)")
    while not stream.order_updates.empty():
        u = stream.order_updates.get_nowait()
        if u.get("tag") == "kiteskill" and u["status"] in ("COMPLETE", "REJECTED", "CANCELLED"):
            state = "IN_POSITION" if u["status"] == "COMPLETE" else "IDLE"
```

## Things this skill will not build

- Latency races / HFT-style strategies above 10 orders/second (need exchange algo registration).
- Spoofing, layering, quote stuffing or any manipulative pattern.
- Unattended bots without a kill switch and daily loss limit.
