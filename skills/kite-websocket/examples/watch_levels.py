#!/usr/bin/env python3
"""Local price alerts from the live feed — prints (and beeps) when a level is crossed. Places no orders.

UNOFFICIAL — not affiliated with Zerodha.

    python examples/watch_levels.py "NSE:NIFTY 50>=26000" "INFY<=1450" "NSE:NIFTY BANK>=57000"

Each alert fires once per crossing (re-arms after price moves back through the level).
For server-side alerts that work while your machine is off, use kite-connect's price_alert.py.
"""

import argparse
import re

from _common import label, open_stream
from scripts.kite_common import resolve_instrument
from scripts.tick_utils import tick_time

RULE = re.compile(r"^(?P<inst>.+?)\s*(?P<op>>=|<=)\s*(?P<level>[\d.]+)$")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rules", nargs="+", help='e.g. "INFY>=1500"')
    a = ap.parse_args()

    parsed = []
    for r in a.rules:
        m = RULE.match(r.strip())
        if not m:
            ap.error(f"bad rule {r!r}; use SYMBOL>=LEVEL or SYMBOL<=LEVEL")
        parsed.append((m["inst"].strip(), m["op"], float(m["level"])))

    kite, stream, rows = open_stream([p[0] for p in parsed], "quote")
    alerts = []
    for inst, op, level in parsed:
        tok = resolve_instrument(kite, inst)["instrument_token"]  # cached dump, no extra API call
        alerts.append({"token": tok, "label": label(rows[tok]), "op": op, "level": level, "armed": True})
    print("Watching:", ", ".join(f"{x['label']} {x['op']} {x['level']}" for x in alerts))

    try:
        for received_at, tick in stream.iter_ticks(timeout=1):
            px = tick["last_price"]
            for al in alerts:
                if al["token"] != tick["instrument_token"]:
                    continue
                hit = px >= al["level"] if al["op"] == ">=" else px <= al["level"]
                if hit and al["armed"]:
                    al["armed"] = False
                    print(f"\a[{tick_time(tick, received_at):%H:%M:%S}] ALERT {al['label']} {px:.2f} "
                          f"{al['op']} {al['level']}")
                elif not hit:
                    al["armed"] = True
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()


if __name__ == "__main__":
    main()
