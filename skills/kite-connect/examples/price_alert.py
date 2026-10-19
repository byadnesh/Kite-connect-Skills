#!/usr/bin/env python3
"""Create / list / delete Kite price alerts (simple type — notification only).

    python examples/price_alert.py create NSE INFY ">=" 1700
    python examples/price_alert.py create INDICES "NIFTY 50" "<=" 24500
    python examples/price_alert.py list
    python examples/price_alert.py delete <uuid>
"""

import argparse

from _common import confirm
from scripts.kite_client import alerts_request, get_client
from scripts.trade_journal import log_action

OPS = {">=", "<=", ">", "<", "=="}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["create", "list", "delete"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    argv = [a.cmd, *a.args]
    if (a.cmd == "create" and len(a.args) != 4) or (a.cmd == "delete" and len(a.args) != 1):
        ap.error("usage: create EXCHANGE SYMBOL OP VALUE | delete UUID | list")
    kite = get_client()
    if argv[0] == "list":
        for al in alerts_request(kite, "GET", params={"status": "enabled"}) or []:
            print(al["uuid"], al["name"], al["lhs_tradingsymbol"], al["operator"], al.get("rhs_constant"), al["status"])
        return
    if argv[0] == "delete":
        if confirm(f"Delete alert {argv[1]}? (yes): "):
            alerts_request(kite, "DELETE", params={"uuid": argv[1]})
            log_action("alert", {"delete": argv[1]})
        return
    if argv[0] == "create":
        exchange, symbol, op, value = argv[1], argv[2], argv[3], float(argv[4])
        if op not in OPS:
            raise SystemExit(f"operator must be one of {OPS}")
        params = {"name": f"{symbol} {op} {value}", "type": "simple", "lhs_exchange": exchange,
                  "lhs_tradingsymbol": symbol, "lhs_attribute": "LastTradedPrice",
                  "operator": op, "rhs_type": "constant", "rhs_constant": value}
        print(params)
        if confirm("Create alert? (yes): "):
            al = alerts_request(kite, "POST", params=params)
            log_action("alert", params, order_id=al.get("uuid"))
            print("created", al.get("uuid"))


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
