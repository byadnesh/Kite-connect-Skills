#!/usr/bin/env python3
"""Stream live ticks + order updates. Ctrl+C to stop. Needs the Connect plan.

    python examples/live_ticker.py RELIANCE INFY "NIFTY 50" --mode quote
"""

import argparse
import signal
import sys

import _common  # noqa: F401  (adds the skill root to sys.path)
from kiteconnect import KiteTicker
from scripts.instruments import find_equity
from scripts.kite_client import get_client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--mode", default="quote", choices=["ltp", "quote", "full"])
    a = ap.parse_args()

    kite = get_client()
    tokens = {find_equity(kite, s)["instrument_token"]: s for s in a.symbols}
    kws = KiteTicker(kite.api_key, kite.access_token)

    def on_connect(ws, _):
        ws.subscribe(list(tokens))
        ws.set_mode(a.mode, list(tokens))
        print("subscribed", list(tokens.values()))

    def on_ticks(ws, ticks):
        for t in ticks:
            print(f"{tokens.get(t['instrument_token'], t['instrument_token']):<12} {t['last_price']:>10.2f} "
                  f"chg {t.get('change', 0):+.2f}%  vol {t.get('volume_traded', '-')}")

    def on_order_update(ws, d):
        print(f"[ORDER] {d['order_id']} {d['tradingsymbol']} {d['status']} {d.get('status_message') or ''}")

    kws.on_connect = on_connect
    kws.on_ticks = on_ticks
    kws.on_order_update = on_order_update
    kws.on_error = lambda ws, code, reason: print("error", code, reason, file=sys.stderr)
    kws.on_close = lambda ws, code, reason: print("closed", code, reason)

    def stop(*_):
        kws.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    kws.connect()


if __name__ == "__main__":
    main()
