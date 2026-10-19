#!/usr/bin/env python3
"""Read-only dashboard: funds, holdings, open positions, today's orders. Places nothing.

    python examples/portfolio_dashboard.py
"""

import argparse

import _common  # noqa: F401  (adds the skill root to sys.path)
from scripts.kite_client import get_client


def inr(x):
    return f"₹{x:,.0f}"


def main():
    kite = get_client()
    eq = kite.margins("equity")
    print(f"Available margin {inr(eq['net'])}  (cash {inr(eq['available']['cash'])}, "
          f"collateral {inr(eq['available']['collateral'])})\n")

    holdings = kite.holdings()
    inv = cur = day = 0.0
    print(f"{'HOLDING':<14}{'QTY':>6}{'AVG':>10}{'LTP':>10}{'P&L':>12}{'DAY%':>7}")
    for h in sorted(holdings, key=lambda h: -h["last_price"] * (h["quantity"] + h["t1_quantity"])):
        q = h["quantity"] + h["t1_quantity"]
        inv += h["average_price"] * q
        cur += h["last_price"] * q
        day += h["day_change"] * q
        print(f"{h['tradingsymbol']:<14}{q:>6}{h['average_price']:>10.2f}{h['last_price']:>10.2f}"
              f"{h['pnl']:>12,.0f}{h['day_change_percentage']:>7.2f}")
    if inv:
        print(f"Invested {inr(inv)}  Current {inr(cur)}  P&L {inr(cur - inv)} "
              f"({(cur - inv) / inv * 100:.2f}%)  Today {inr(day)}\n")

    net = kite.positions()["net"]
    print(f"{'POSITION':<26}{'PROD':>6}{'QTY':>7}{'AVG':>10}{'LTP':>10}{'P&L':>12}")
    for p in (p for p in net if p["quantity"]):
        print(f"{p['tradingsymbol']:<26}{p['product']:>6}{p['quantity']:>7}{p['average_price']:>10.2f}"
              f"{p['last_price']:>10.2f}{p['pnl']:>12,.0f}")
    print(f"Positions P&L (incl. closed today) {inr(sum(p['pnl'] for p in net))}\n")

    by_status = {}
    for o in kite.orders():
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
    print("Orders today:", by_status or "none")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    main()
