#!/usr/bin/env python3
"""Buy/sell an index or stock option by underlying + strike, with lot-size and margin checks.

    python examples/place_fno_order.py NIFTY 25000 CE BUY --lots 1
    python examples/place_fno_order.py BANKNIFTY 56000 PE SELL --lots 1 --expiry 2026-10-27 --price 210
"""

import argparse
import time
from datetime import date

from _common import confirm
from scripts.instruments import find_option, quote_key
from scripts.kite_client import get_client
from scripts.trade_journal import log_action
from scripts.validate_order import format_preview, validate_order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("underlying")
    ap.add_argument("strike", type=float)
    ap.add_argument("option_type", choices=["CE", "PE"])
    ap.add_argument("side", choices=["BUY", "SELL"])
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--expiry", type=date.fromisoformat)
    ap.add_argument("--price", type=float)
    ap.add_argument("--product", default="NRML", choices=["NRML", "MIS"])
    a = ap.parse_args()

    kite = get_client()
    inst = find_option(kite, a.underlying, a.expiry, a.strike, a.option_type)
    key = quote_key(inst)
    q = kite.quote(key)[key]
    ltp = q["last_price"]
    bid = q["depth"]["buy"][0]["price"] or ltp
    ask = q["depth"]["sell"][0]["price"] or ltp
    price = a.price or (ask if a.side == "BUY" else bid)

    order = dict(variety="regular", exchange=inst["exchange"], tradingsymbol=inst["tradingsymbol"],
                 transaction_type=a.side, quantity=a.lots * inst["lot_size"], product=a.product,
                 order_type="LIMIT", price=price, validity="DAY", tag="kiteskill")
    report = validate_order(order, instrument=inst, ltp=ltp)

    leg = {k: order[k] for k in ("exchange", "tradingsymbol", "transaction_type", "variety",
                                  "product", "order_type", "quantity", "price")}
    leg["trigger_price"] = 0
    need = kite.order_margins([leg])[0]["total"]
    have = kite.margins("equity")["net"]

    print(f"{inst['tradingsymbol']}  expiry {inst['expiry']}  lot {inst['lot_size']}  "
          f"LTP {ltp}  bid {bid}  ask {ask}  OI {q.get('oi')}")
    print(format_preview(order, report))
    print(f"Margin required ₹{need:,.0f}  available ₹{have:,.0f}")
    if need > have:
        print("Insufficient margin — not placing.")
        return
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
