# Common Multi-Step Workflows

Each workflow: gather → compute → **preview everything** → one confirmation → execute → verify → journal.

## 1. Morning check

```python
from scripts.kite_client import get_client, session_summary
from scripts.market_hours import market_status
kite = get_client()
print(session_summary(kite))
print(market_status("NSE"))
print([o for o in kite.orders() if o["status"] in ("OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED")])
print(len(kite.get_gtts()), "GTTs")
```

## 2. Entry with protective stop

Kite has no bracket order for retail API use. Emulate:

1. Place entry LIMIT (regular, MIS/CNC/NRML).
2. Wait for `COMPLETE` (WebSocket `on_order_update` or poll `order_history`).
3. Place `SL` (or `SL-M` + `market_protection=-1`) on the opposite side for the filled quantity.
4. Optional target: separate LIMIT; when one fills, cancel the other (the agent must watch, or use GTT OCO
   for CNC/NRML that can outlive the day).

```python
entry = kite.place_order(variety="regular", exchange="NSE", tradingsymbol="SBIN", transaction_type="BUY",
                         quantity=10, product="MIS", order_type="LIMIT", price=800.0, tag="kiteskill")
st = wait_status(kite, entry)            # see orders.md
if st["status"] == "COMPLETE":
    sl = kite.place_order(variety="regular", exchange="NSE", tradingsymbol="SBIN", transaction_type="SELL",
                          quantity=st["filled_quantity"], product="MIS", order_type="SL",
                          trigger_price=792.0, price=791.0, tag="kiteskill")
```

Confirm both legs up front ("entry 800, stop 792/791, 10 shares, max loss ≈ ₹90 + charges").

## 3. Rebalance holdings to target weights

```python
targets = {"INFY": 0.25, "HDFCBANK": 0.25, "RELIANCE": 0.25, "TCS": 0.25}
H = {h["tradingsymbol"]: h for h in kite.holdings()}
ltp = {k.split(":")[1]: v["last_price"] for k, v in kite.ltp(*[f"NSE:{s}" for s in targets]).items()}
value = sum((H[s]["quantity"] + H[s]["t1_quantity"]) * ltp[s] for s in targets if s in H)
cash = kite.margins("equity")["net"]
total = value + cash
plan = []
for s, w in targets.items():
    have = (H[s]["quantity"] + H[s]["t1_quantity"]) if s in H else 0
    want = int(total * w // ltp[s])
    if want != have:
        plan.append({"symbol": s, "side": "BUY" if want > have else "SELL", "qty": abs(want - have), "ltp": ltp[s]})
```

Show the plan as a table, totals, and estimated charges. Execute **SELLs first** (frees cash), then BUYs.

## 4. End-of-day report

```python
pos = [p for p in kite.positions()["net"] if p["quantity"] or p["realised"]]
trades = kite.trades()
print("Realised:", sum(p["realised"] for p in pos), "Unrealised:", sum(p["unrealised"] for p in pos))
print("Trades:", len(trades), "Orders rejected:", sum(o["status"] == "REJECTED" for o in kite.orders()))
```

Add exact charges via `get_virtual_contract_note` for executed orders.

## 5. Trailing stop (agent-managed)

Kite has no native trailing SL for retail API orders. If the user wants one:
- Subscribe the instrument on WebSocket.
- Keep `highest = max(highest, ltp)`; when `highest - trail > current_trigger + tick`, call `modify_order`
  on the SL order with the new trigger.
- Throttle modifications (≥ 1 s apart, ≤ 25 per order — after that cancel and re-place).
- Confirm the *rule* with the user once; each modification is pre-authorised by that rule — state this
  explicitly and stop if anything unexpected happens.

## 6. Panic button: exit all intraday positions

1. `positions()["net"]` with `quantity != 0` and `product == "MIS"`.
2. Cancel open orders for those symbols (pending SLs).
3. Build opposite LIMIT orders at LTP ± a few ticks (or MARKET + `market_protection=-1` if user insists).
4. Sort: buy back shorts (options) before selling longs.
5. One preview, one confirmation, then execute and report each order's final status.
