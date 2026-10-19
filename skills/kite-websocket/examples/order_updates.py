#!/usr/bin/env python3
"""Print order status changes in real time (all orders on the account, or one tag). Read-only.

UNOFFICIAL — not affiliated with Zerodha. Ctrl+C to stop.

    python examples/order_updates.py
    python examples/order_updates.py --tag kiteskill
"""

import argparse
import queue

from _common import open_stream


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="only show orders with this tag")
    a = ap.parse_args()

    _, stream, _ = open_stream([], "ltp")
    print("Listening for order updates…")
    try:
        while True:
            try:
                u = stream.order_updates.get(timeout=1)
            except queue.Empty:
                continue
            if a.tag and u.get("tag") != a.tag:
                continue
            print(f"{u.get('exchange_update_timestamp') or u.get('order_timestamp')}  {u['order_id']}  "
                  f"{u.get('transaction_type')} {u.get('filled_quantity', 0)}/{u.get('quantity')} "
                  f"{u.get('exchange')}:{u.get('tradingsymbol')}  {u['status']:<16} "
                  f"avg {u.get('average_price')}  {u.get('status_message') or ''}")
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()


if __name__ == "__main__":
    main()
