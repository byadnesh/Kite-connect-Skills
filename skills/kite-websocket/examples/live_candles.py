#!/usr/bin/env python3
"""Build live candles from ticks and print each bar as it closes. Read-only. Ctrl+C to stop.

UNOFFICIAL — not affiliated with Zerodha. Needs the Kite Connect plan.

    python examples/live_candles.py "NSE:NIFTY 50" INFY --interval 60
    python examples/live_candles.py NFO:NIFTY26OCTFUT --interval 300 --csv nifty_fut_5m.csv
    python examples/live_candles.py MCX:CRUDEOIL26NOVFUT --anchor 09:00
"""

import argparse
import csv
from datetime import time

from _common import label, open_stream
from scripts.bars import BarBuilder


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instruments", nargs="+")
    ap.add_argument("--interval", type=int, default=60, help="bar size in seconds")
    ap.add_argument("--anchor", default="09:15", help="session anchor HH:MM (MCX/CDS: 09:00)")
    ap.add_argument("--csv", help="append closed bars to this CSV")
    a = ap.parse_args()

    _, stream, rows = open_stream(a.instruments, "full")
    bb = BarBuilder(interval=a.interval, anchor=time.fromisoformat(a.anchor))
    writer, fh = None, None
    if a.csv:
        fh = open(a.csv, "a", newline="", encoding="utf-8")
        writer = csv.DictWriter(fh, fieldnames=["symbol", "start", "open", "high", "low", "close", "volume", "oi", "ticks"])
        if fh.tell() == 0:
            writer.writeheader()

    def emit(bar):
        sym = label(rows[bar["token"]])
        print(f"{bar['start']:%H:%M:%S} {sym:<26} O {bar['open']:>10.2f} H {bar['high']:>10.2f} "
              f"L {bar['low']:>10.2f} C {bar['close']:>10.2f} V {bar['volume']:>10,} ticks {bar['ticks']}")
        if writer:
            writer.writerow({"symbol": sym, "start": bar["start"].isoformat(),
                             **{k: bar[k] for k in ("open", "high", "low", "close", "volume", "oi", "ticks")}})
            fh.flush()

    print(f"Building {a.interval}s bars for {', '.join(label(r) for r in rows.values())} — first bar prints "
          "when its interval ends.")
    try:
        for received_at, tick in stream.iter_ticks(timeout=1):
            for bar in bb.update(tick, received_at):
                emit(bar)
            for bar in bb.flush():
                emit(bar)
    except KeyboardInterrupt:
        for bar in bb.flush(force=True):
            emit(bar)
    finally:
        stream.close()
        if fh:
            fh.close()


if __name__ == "__main__":
    main()
