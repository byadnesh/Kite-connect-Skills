#!/usr/bin/env python3
"""Margin + estimated charges for a hypothetical order. Places nothing.

    python examples/margin_check.py NFO NIFTY25OCT25000CE SELL 75 --price 120 --product NRML
    python examples/margin_check.py NSE INFY BUY 10 --price 1500 --product CNC
"""

import argparse

import _common  # noqa: F401  (adds the skill root to sys.path)
from scripts.kite_client import get_client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exchange")
    ap.add_argument("tradingsymbol")
    ap.add_argument("side", choices=["BUY", "SELL"])
    ap.add_argument("quantity", type=int)
    ap.add_argument("--price", type=float, default=0)
    ap.add_argument("--product", default="CNC")
    ap.add_argument("--order-type", default="LIMIT")
    a = ap.parse_args()

    kite = get_client()
    leg = dict(exchange=a.exchange, tradingsymbol=a.tradingsymbol, transaction_type=a.side,
               variety="regular", product=a.product, order_type=a.order_type,
               quantity=a.quantity, price=a.price, trigger_price=0)
    m = kite.order_margins([leg])[0]
    have = kite.margins("commodity" if a.exchange == "MCX" else "equity")["net"]
    print(f"Required ₹{m['total']:,.2f}  (SPAN {m.get('span', 0):,.0f}, exposure {m.get('exposure', 0):,.0f}, "
          f"premium {m.get('option_premium', 0):,.0f})")
    verdict = "OK" if have >= m["total"] else f"SHORT by ₹{m['total'] - have:,.0f}"
    print(f"Available ₹{have:,.2f}  →  {verdict}")
    ch = m.get("charges") or {}
    if ch:
        print(f"Est. charges ₹{ch.get('total', 0):,.2f}  (brokerage {ch.get('brokerage', 0)}, "
              f"STT {ch.get('transaction_tax', 0)}, exch {ch.get('exchange_turnover_charge', 0)}, "
              f"stamp {ch.get('stamp_duty', 0)}, GST {(ch.get('gst') or {}).get('total', 0)})")


if __name__ == "__main__":
    main()
