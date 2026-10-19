#!/usr/bin/env python3
"""Live quote table refreshed every second. Read-only. Ctrl+C to stop.

UNOFFICIAL — not affiliated with Zerodha. Needs the Kite Connect plan.

    python examples/stream_quotes.py INFY RELIANCE "NSE:NIFTY 50" "NSE:NIFTY BANK"
    python examples/stream_quotes.py NFO:NIFTY26OCTFUT --mode full
"""

import argparse
import time

from _common import label, open_stream
from scripts.tick_utils import best_bid_ask, spread_bps, tick_time


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instruments", nargs="+", help="NSE symbol, EXCH:SYMBOL, or instrument_token")
    ap.add_argument("--mode", default="full", choices=["ltp", "quote", "full"])
    ap.add_argument("--refresh", type=float, default=1.0)
    a = ap.parse_args()

    _, stream, rows = open_stream(a.instruments, a.mode)
    try:
        while True:
            time.sleep(a.refresh)
            print("\033[2J\033[H", end="")  # clear screen
            print(f"{'INSTRUMENT':<28}{'LTP':>11}{'CHG%':>8}{'BID':>11}{'ASK':>11}{'SPRD bps':>9}"
                  f"{'VOLUME':>13}{'OI':>11}  TIME")
            for tok, row in rows.items():
                t = stream.latest.get(tok)
                if not t:
                    print(f"{label(row):<28}{'waiting…':>11}")
                    continue
                bid, ask = best_bid_ask(t)
                sp = spread_bps(t)
                print(f"{label(row):<28}{t['last_price']:>11.2f}{t.get('change', 0):>+8.2f}"
                      f"{bid or 0:>11.2f}{ask or 0:>11.2f}{sp if sp is not None else 0:>9.1f}"
                      f"{t.get('volume_traded') or 0:>13,}{t.get('oi') or 0:>11,}  "
                      f"{tick_time(t):%H:%M:%S}")
            h = stream.health()
            print(f"\nticks {h['ticks']}  dropped {h['dropped']}  "
                  f"connected {[c['connected'] for c in h['connections']]}")
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()


if __name__ == "__main__":
    main()
