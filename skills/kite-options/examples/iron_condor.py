#!/usr/bin/env python3
"""Build, analyse and (optionally) execute an iron condor.

UNOFFICIAL — not affiliated with Zerodha. Educational; not investment advice.

    python examples/iron_condor.py NIFTY --delta 0.16 --width 200            # analysis only
    python examples/iron_condor.py NIFTY --delta 0.16 --width 200 --execute  # asks for "yes"

Execution: BUY wings first, then SELL shorts, LIMIT at mid. Stops on the first failure.
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.greeks import strategy_stats  # noqa: E402
from scripts.kite_common import get_client  # noqa: E402
from scripts.option_chain import build_chain, expected_move, find_by_delta  # noqa: E402

FINAL = {"COMPLETE", "REJECTED", "CANCELLED"}


def tick_round(x, tick):
    return round(round(x / tick) * tick, 2)


def mid(row, p):
    b, a = row.get(f"{p}_bid"), row.get(f"{p}_ask")
    return (b + a) / 2 if b and a else row.get(f"{p}_ltp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("underlying")
    ap.add_argument("--expiry", type=date.fromisoformat)
    ap.add_argument("--delta", type=float, default=0.16)
    ap.add_argument("--width", type=float, default=200)
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()

    kite = get_client()
    chain = build_chain(kite, a.underlying, a.expiry, strikes_each_side=30)
    rows = {r["strike"]: r for r in chain["rows"]}
    sp = find_by_delta(chain, "PE", a.delta)["strike"]
    sc = find_by_delta(chain, "CE", a.delta)["strike"]
    lp, lc = sp - a.width, sc + a.width
    missing = [k for k in (lp, lc) if k not in rows]
    if missing:
        raise SystemExit(f"Wing strikes {missing} not in fetched chain; reduce --width or widen the chain")

    spec = [(lp, "PE", "BUY"), (lc, "CE", "BUY"), (sp, "PE", "SELL"), (sc, "CE", "SELL")]  # buys first
    legs = []
    for k, cp, side in spec:
        r, p = rows[k], cp.lower()
        price = mid(r, p)
        if not price:
            raise SystemExit(f"No price for {k}{cp}")
        legs.append({"strike": k, "option_type": cp, "side": side, "quantity": a.lots * r[f"{p}_lot_size"],
                     "premium": tick_round(price, r[f"{p}_tick_size"]), "tradingsymbol": r[f"{p}_tradingsymbol"],
                     "delta": r.get(f"{p}_delta")})

    stats = strategy_stats(legs, chain["spot"] * 0.8, chain["spot"] * 1.2)
    margin_legs = [dict(exchange=chain["exchange"], tradingsymbol=l["tradingsymbol"], transaction_type=l["side"],
                        variety="regular", product="NRML", order_type="LIMIT", quantity=l["quantity"],
                        price=l["premium"], trigger_price=0) for l in legs]
    m = kite.basket_order_margins(margin_legs, consider_positions=True)
    avail = kite.margins("equity")["net"]

    print(f"{chain['underlying']} {chain['expiry']} spot {chain['spot']:.2f}  1σ ±{expected_move(chain) or 0:.0f}")
    print(f"{'#':<3}{'SIDE':<6}{'SYMBOL':<26}{'QTY':>6}{'LIMIT':>9}{'Δ':>7}")
    for i, l in enumerate(legs, 1):
        print(f"{i:<3}{l['side']:<6}{l['tradingsymbol']:<26}{l['quantity']:>6}{l['premium']:>9.2f}"
              f"{(l['delta'] or 0):>7.2f}")
    print(f"Net credit ₹{stats['net_premium']:,.0f}  max profit {stats['max_profit']}  "
          f"max loss {stats['max_loss']}  breakevens {stats['breakevens']}")
    print(f"Margin: without hedge ₹{m['initial']['total']:,.0f}  with hedge ₹{m['final']['total']:,.0f}  "
          f"available ₹{avail:,.0f}")

    if not a.execute:
        print("\nAnalysis only. Re-run with --execute to place (you will be asked to confirm).")
        return
    if m["final"]["total"] > avail:
        raise SystemExit("Insufficient margin.")
    if input("Place all 4 legs (wings first)? Type 'yes': ").strip().lower() != "yes":
        print("Not placed.")
        return

    for l in legs:
        oid = kite.place_order(variety="regular", exchange=chain["exchange"], tradingsymbol=l["tradingsymbol"],
                               transaction_type=l["side"], quantity=l["quantity"], product="NRML",
                               order_type="LIMIT", price=l["premium"], validity="DAY", tag="kiteskillic")
        status = None
        for _ in range(20):
            status = kite.order_history(oid)[-1]
            if status["status"] in FINAL:
                break
            time.sleep(0.5)
        print(f"{l['side']} {l['tradingsymbol']} → {oid} {status['status']} {status.get('status_message') or ''}")
        if status["status"] != "COMPLETE":
            print("Leg not filled — stopping. Review open orders/positions before doing anything else.")
            return
    print("All legs filled.")


if __name__ == "__main__":
    main()
