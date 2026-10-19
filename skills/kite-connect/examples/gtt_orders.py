#!/usr/bin/env python3
"""GTT examples.

    python examples/gtt_orders.py single INFY --trigger 1400 --qty 1          # buy on dip
    python examples/gtt_orders.py oco INFY --sl 1350 --target 1650 --qty 10   # protect a holding
    python examples/gtt_orders.py list
    python examples/gtt_orders.py delete 123456
"""

import argparse

from _common import confirm, tick_round
from scripts.instruments import find_equity
from scripts.kite_client import get_client
from scripts.trade_journal import log_action


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["single", "oco", "list", "delete"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--trigger", type=float)
    ap.add_argument("--sl", type=float)
    ap.add_argument("--target", type=float)
    ap.add_argument("--qty", type=int, default=1)
    a = ap.parse_args()
    kite = get_client()

    if a.cmd == "list":
        for g in kite.get_gtts():
            c = g["condition"]
            print(g["id"], g["status"], g["type"], c["exchange"], c["tradingsymbol"], c["trigger_values"])
        return
    if a.cmd == "delete":
        if confirm(f"Delete GTT {a.arg}? (yes): "):
            kite.delete_gtt(int(a.arg))
            log_action("gtt_delete", {"trigger_id": a.arg})
        return

    inst = find_equity(kite, a.arg)
    tick = inst["tick_size"]
    key = f"NSE:{inst['tradingsymbol']}"
    ltp = kite.ltp(key)[key]["last_price"]

    if a.cmd == "single":
        if not a.trigger:
            ap.error("--trigger required")
        side = "BUY" if a.trigger < ltp else "SELL"
        orders = [{"transaction_type": side, "quantity": a.qty, "order_type": "LIMIT", "product": "CNC",
                   "price": tick_round(a.trigger * (1.001 if side == "BUY" else 0.999), tick)}]
        params = dict(trigger_type=kite.GTT_TYPE_SINGLE, tradingsymbol=inst["tradingsymbol"], exchange="NSE",
                      trigger_values=[a.trigger], last_price=ltp, orders=orders)
    else:
        if not (a.sl and a.target) or not a.sl < ltp < a.target:
            ap.error("need --sl < LTP < --target")
        orders = [
            {"transaction_type": "SELL", "quantity": a.qty, "order_type": "LIMIT", "product": "CNC",
             "price": tick_round(a.sl * 0.995, tick)},
            {"transaction_type": "SELL", "quantity": a.qty, "order_type": "LIMIT", "product": "CNC",
             "price": tick_round(a.target, tick)},
        ]
        params = dict(trigger_type=kite.GTT_TYPE_OCO, tradingsymbol=inst["tradingsymbol"], exchange="NSE",
                      trigger_values=[a.sl, a.target], last_price=ltp, orders=orders)

    print(f"LTP {ltp}\nGTT {params['trigger_type']} {key} triggers={params['trigger_values']}")
    for o in orders:
        print(f"  → {o['transaction_type']} {o['quantity']} LIMIT {o['price']} {o['product']}")
    if confirm("Create this GTT? (yes): "):
        tid = kite.place_gtt(**params)["trigger_id"]
        log_action("gtt_place", params, order_id=str(tid))
        print("trigger_id", tid)


if __name__ == "__main__":
    main()
