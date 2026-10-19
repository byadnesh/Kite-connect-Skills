#!/usr/bin/env python3
"""Full order lifecycle demo: place a far-from-market LIMIT, modify it, cancel it.

Uses a price 5 % below LTP so it should rest unfilled. Every step asks for confirmation.

    python examples/order_lifecycle.py SBIN
"""

import argparse
import time

from _common import confirm, tick_round
from scripts.instruments import find_equity
from scripts.kite_client import get_client
from scripts.trade_journal import log_action
from scripts.validate_order import format_preview, validate_order


def main(symbol="SBIN"):
    kite = get_client()
    inst = find_equity(kite, symbol)
    key = f"NSE:{inst['tradingsymbol']}"
    ltp = kite.ltp(key)[key]["last_price"]
    order = dict(variety="regular", exchange="NSE", tradingsymbol=inst["tradingsymbol"], transaction_type="BUY",
                 quantity=1, product="CNC", order_type="LIMIT",
                 price=tick_round(ltp * 0.95, inst["tick_size"]), validity="DAY", tag="kiteskill")
    report = validate_order(order, instrument=inst, ltp=ltp)
    print(format_preview(order, report))
    if not report["ok"] or not confirm("1/3 place? (yes): "):
        return

    oid = kite.place_order(**order)
    log_action("place", order, order_id=oid)
    time.sleep(1)
    print("status:", kite.order_history(oid)[-1]["status"])

    new_price = tick_round(ltp * 0.94, inst["tick_size"])
    if confirm(f"2/3 modify price → {new_price}? (yes): "):
        kite.modify_order(variety="regular", order_id=oid, price=new_price, order_type="LIMIT", quantity=1)
        log_action("modify", {"price": new_price}, order_id=oid)
        time.sleep(1)
        print("status:", kite.order_history(oid)[-1]["status"])

    if confirm("3/3 cancel? (yes): "):
        kite.cancel_order(variety="regular", order_id=oid)
        log_action("cancel", {}, order_id=oid)
        time.sleep(1)
        print("status:", kite.order_history(oid)[-1]["status"])

    print("\nToday's orders for", inst["tradingsymbol"])
    for o in kite.orders():
        if o["tradingsymbol"] == inst["tradingsymbol"]:
            print(o["order_id"], o["status"], o["price"], o["quantity"], o.get("tag"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol", nargs="?", default="SBIN", help="NSE equity symbol (default SBIN)")
    main(ap.parse_args().symbol)
