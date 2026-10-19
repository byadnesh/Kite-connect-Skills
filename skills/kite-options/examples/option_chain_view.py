#!/usr/bin/env python3
"""Print an option chain with IV/Greeks, PCR, max pain, OI walls and expected move. Read-only.

UNOFFICIAL — not affiliated with Zerodha.

    python examples/option_chain_view.py NIFTY
    python examples/option_chain_view.py SENSEX --strikes 15
    python examples/option_chain_view.py BANKNIFTY --expiry 2026-10-27
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.kite_common import get_client  # noqa: E402
from scripts.option_chain import build_chain, find_by_delta, format_chain, list_expiries  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("underlying")
    ap.add_argument("--expiry", type=date.fromisoformat)
    ap.add_argument("--strikes", type=int, default=10)
    a = ap.parse_args()

    kite = get_client()
    print("Upcoming expiries:", ", ".join(d.isoformat() for d in list_expiries(kite, a.underlying)[:6]))
    chain = build_chain(kite, a.underlying, a.expiry, a.strikes)
    print(format_chain(chain))

    rows = chain["rows"]
    call_wall = max(rows, key=lambda r: r.get("ce_oi") or 0)["strike"]
    put_wall = max(rows, key=lambda r: r.get("pe_oi") or 0)["strike"]
    print(f"Call OI wall {call_wall:g}   Put OI wall {put_wall:g}")
    try:
        print(f"16Δ strikes: PE {find_by_delta(chain, 'PE', 0.16)['strike']:g}  "
              f"CE {find_by_delta(chain, 'CE', 0.16)['strike']:g}")
    except ValueError:
        pass


if __name__ == "__main__":
    main()
