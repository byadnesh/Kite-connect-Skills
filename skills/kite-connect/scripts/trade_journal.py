#!/usr/bin/env python3
"""Append-only local journal of every order action the agent takes.

UNOFFICIAL — not affiliated with Zerodha.

Writes JSON Lines to ~/.kite-skills/journal.jsonl (override with KITE_SKILLS_HOME).
Never stores credentials.

    from scripts.trade_journal import log_action
    log_action("place", order_params, order_id=oid, note="user confirmed in chat")

CLI:
    python scripts/trade_journal.py            # last 20 entries
    python scripts/trade_journal.py --today
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
JOURNAL = Path(os.environ.get("KITE_SKILLS_HOME", Path.home() / ".kite-skills")) / "journal.jsonl"
_SENSITIVE = {"access_token", "api_secret", "api_key", "request_token", "password", "totp", "pin"}


def log_action(action: str, params: dict[str, Any] | None = None, *, order_id: str | None = None,
               status: str | None = None, error: str | None = None, note: str | None = None) -> dict[str, Any]:
    """action: place | modify | cancel | exit | convert | gtt_place | gtt_modify | gtt_delete | alert | mf"""
    clean = {k: v for k, v in (params or {}).items() if k.lower() not in _SENSITIVE}
    entry = {
        "ts": datetime.now(IST).isoformat(timespec="seconds"),
        "action": action,
        "order_id": order_id,
        "status": status,
        "params": clean,
        "error": error,
        "note": note,
    }
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return entry


def read_journal(today_only: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    if not JOURNAL.exists():
        return []
    rows = [json.loads(line) for line in JOURNAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    if today_only:
        today = datetime.now(IST).date().isoformat()
        rows = [r for r in rows if r["ts"].startswith(today)]
    return rows[-limit:] if limit else rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("-n", type=int, default=20)
    a = ap.parse_args()
    for r in read_journal(a.today, a.n):
        p = r["params"]
        print(f"{r['ts']} {r['action']:<10} {r.get('order_id') or '-':<20} "
              f"{p.get('transaction_type', '')} {p.get('quantity', '')} {p.get('tradingsymbol', '')} "
              f"{r.get('status') or ''} {r.get('error') or ''}")
