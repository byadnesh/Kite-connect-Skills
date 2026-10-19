#!/usr/bin/env python3
"""Buy/sell NSE equity with a LIMIT order: resolve → validate → preview → confirm → place → verify.

    python examples/place_equity_order.py INFY BUY 1 --price 1500
    python examples/place_equity_order.py INFY BUY 1                # limit = LTP ∓ 0.5 %, rounded to tick
"""

import argparse
import time

from _common import confirm, tick_round
from scripts.instruments import find_equity, quote_key
from scripts.kite_client import get_client
from scripts.trade_journal import log_action
from scripts.validate_order import format_preview, validate_order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("side", choices=["BUY", "SELL"])
    ap.add_argument("quantity", type=int)
    ap.add_argument("--price", type=float)
    ap.add_argument("--product", default="CNC", choices=["CNC", "MIS", "MTF"])
    ap.add_argument("--exchange", default="NSE", choices=["NSE", "BSE"])
    a = ap.parse_args()

    kite = get_client()
    inst = find_equity(kite, a.symbol, a.exchange)
    key = quote_key(inst)
    ltp = kite.ltp(key)[key]["last_price"]
    price = a.price or tick_round(ltp * (0.995 if a.side == "BUY" else 1.005), inst["tick_size"])

    order = dict(variety="regular", exchange=a.exchange, tradingsymbol=inst["tradingsymbol"],
                 transaction_type=a.side, quantity=a.quantity, product=a.product,
                 order_type="LIMIT", price=price, validity="DAY", tag="kiteskill")
    report = validate_order(order, instrument=inst, ltp=ltp)
    print(f"LTP {ltp}")
    print(format_preview(order, report))
    if not report["ok"] or not confirm():
        print("Not placed.")
        return

    oid = kite.place_order(**order)
    time.sleep(1)
    st = kite.order_history(oid)[-1]
    log_action("place", order, order_id=oid, status=st["status"])
    print(f"order_id={oid} status={st['status']} {st.get('status_message') or ''}")


if __name__ == "__main__":
    main()
