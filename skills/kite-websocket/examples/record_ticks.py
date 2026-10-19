#!/usr/bin/env python3
"""Record ticks to daily JSONL files until Ctrl+C or a stop time. Read-only.

UNOFFICIAL — not affiliated with Zerodha. Recorded data is for your own use — don't redistribute.

    python examples/record_ticks.py "NSE:NIFTY 50" NFO:NIFTY26OCTFUT --out ticks --until 15:31
"""

import argparse
from datetime import time

from _common import label, open_stream
from scripts.recorder import TickRecorder
from scripts.tick_utils import now_ist


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instruments", nargs="+")
    ap.add_argument("--mode", default="full", choices=["ltp", "quote", "full"])
    ap.add_argument("--out", default="ticks")
    ap.add_argument("--until", help="stop at HH:MM IST")
    a = ap.parse_args()

    stop_at = time.fromisoformat(a.until) if a.until else None
    _, stream, rows = open_stream(a.instruments, a.mode)
    print(f"Recording {', '.join(label(r) for r in rows.values())} → {a.out}/")
    with TickRecorder(a.out) as rec:
        try:
            for received_at, tick in stream.iter_ticks(timeout=1):
                rec.write(received_at, tick)
                if rec.rows_written % 5000 == 0:
                    print(f"{rec.rows_written:,} ticks, dropped {stream.stats['dropped']}")
                if stop_at and now_ist().time() >= stop_at:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            stream.close()
    print(f"Done: {rec.rows_written:,} ticks written.")


if __name__ == "__main__":
    main()
