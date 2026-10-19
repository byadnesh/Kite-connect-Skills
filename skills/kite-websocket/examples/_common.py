"""Shared bootstrap for the kite-websocket examples (UNOFFICIAL — not affiliated with Zerodha)."""

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

import scripts  # noqa: E402,F401  (UTF-8 console setup)
from scripts.kite_common import get_client, resolve_instrument  # noqa: E402
from scripts.tick_stream import TickStream  # noqa: E402


def open_stream(specs, mode="quote", timeout=15):
    """Resolve 'NSE:INFY'-style specs, start a TickStream, wait for the connection.

    Returns (kite, stream, {token: instrument_row}).
    """
    kite = get_client()
    rows = {}
    for s in specs:
        r = resolve_instrument(kite, s)
        rows[r["instrument_token"]] = r
    stream = TickStream(kite.api_key, kite.access_token)
    if rows:
        stream.subscribe(rows, mode=mode)
    stream.start()
    if not stream.wait_connected(timeout):
        stream.close()
        raise SystemExit("Could not connect to the Kite WebSocket — check the token (Connect plan needed).")
    return kite, stream, rows


def label(row):
    return f"{row['exchange']}:{row['tradingsymbol']}"
