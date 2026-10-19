#!/usr/bin/env python3
"""Build an option chain from Kite's instruments dump + quote API, with IV and Greeks.

UNOFFICIAL — not affiliated with Zerodha.

Kite Connect has no option-chain endpoint. This module:
  1. reads live contracts for the underlying from the NFO/BFO dump (cached daily),
  2. picks strikes around ATM,
  3. pulls full quotes in batches of ≤ 500 (quote API: 1 req/s),
  4. derives a synthetic forward from ATM put-call parity and computes IV + Greeks.

    from scripts.option_chain import build_chain, pcr, max_pain, format_chain
    chain = build_chain(kite, "NIFTY", strikes_each_side=10)
    print(format_chain(chain)); print(pcr(chain), max_pain(chain))

CLI:
    python scripts/option_chain.py NIFTY            # nearest expiry, ±10 strikes
    python scripts/option_chain.py BANKNIFTY --expiry 2026-10-27 --strikes 15
"""

from __future__ import annotations

import math
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.greeks import DEFAULT_R, bs_greeks, implied_carry, implied_vol, time_to_expiry  # noqa: E402
from scripts.kite_common import derivative_exchange, load_instruments, spot_key, today_ist  # noqa: E402

QUOTE_BATCH = 500


def list_expiries(kite, underlying: str) -> list[date]:
    u = underlying.upper()
    rows = load_instruments(kite, derivative_exchange(u))
    t = today_ist()
    return sorted({r["expiry"] for r in rows
                   if r.get("name") == u and r["instrument_type"] in ("CE", "PE") and r["expiry"] and r["expiry"] >= t})


def _quotes(kite, keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i in range(0, len(keys), QUOTE_BATCH):
        if i:
            time.sleep(1.05)
        out.update(kite.quote(*keys[i:i + QUOTE_BATCH]))
    return out


def _side(q: dict | None) -> dict[str, Any]:
    if not q:
        return {"ltp": None, "oi": None, "volume": None, "bid": None, "ask": None}
    depth = q.get("depth") or {}
    bid = (depth.get("buy") or [{}])[0].get("price") or None
    ask = (depth.get("sell") or [{}])[0].get("price") or None
    return {"ltp": q.get("last_price"), "oi": q.get("oi"), "volume": q.get("volume"), "bid": bid, "ask": ask,
            "oi_day_high": q.get("oi_day_high"), "oi_day_low": q.get("oi_day_low")}


def _mid(side: dict) -> float | None:
    if side.get("bid") and side.get("ask"):
        return (side["bid"] + side["ask"]) / 2
    return side.get("ltp") or None


def build_chain(kite, underlying: str, expiry: date | None = None, strikes_each_side: int | None = 10,
                r: float = DEFAULT_R, with_greeks: bool = True) -> dict[str, Any]:
    u = underlying.upper()
    exch = derivative_exchange(u)
    t = today_ist()
    contracts = [x for x in load_instruments(kite, exch)
                 if x.get("name") == u and x["instrument_type"] in ("CE", "PE") and x["expiry"] and x["expiry"] >= t]
    if not contracts:
        raise LookupError(f"No live options for {u} on {exch}")
    expiry = expiry or min(c["expiry"] for c in contracts)
    contracts = [c for c in contracts if c["expiry"] == expiry]
    if not contracts:
        raise LookupError(f"No {u} options expiring {expiry}")

    skey = spot_key(u)
    spot = kite.ltp(skey)[skey]["last_price"]
    time.sleep(1.05)

    strikes = sorted({c["strike"] for c in contracts})
    atm = min(strikes, key=lambda k: abs(k - spot))
    if strikes_each_side is not None:
        i = strikes.index(atm)
        strikes = strikes[max(0, i - strikes_each_side): i + strikes_each_side + 1]
    by_key = {(c["strike"], c["instrument_type"]): c for c in contracts if c["strike"] in set(strikes)}
    keys = [f"{c['exchange']}:{c['tradingsymbol']}" for c in by_key.values()]
    quotes = _quotes(kite, keys)

    rows = []
    for k in strikes:
        row: dict[str, Any] = {"strike": k}
        for cp in ("CE", "PE"):
            c = by_key.get((k, cp))
            q = quotes.get(f"{c['exchange']}:{c['tradingsymbol']}") if c else None
            side = _side(q)
            if c:
                side.update(tradingsymbol=c["tradingsymbol"], instrument_token=c["instrument_token"],
                            lot_size=c["lot_size"], tick_size=c["tick_size"])
            row.update({f"{cp.lower()}_{name}": v for name, v in side.items()})
        rows.append(row)

    T = time_to_expiry(expiry)
    atm_row = next(rw for rw in rows if rw["strike"] == atm)
    c_mid, p_mid = _mid({k[3:]: v for k, v in atm_row.items() if k.startswith("ce_")}), \
        _mid({k[3:]: v for k, v in atm_row.items() if k.startswith("pe_")})
    forward = atm + math.exp(r * T) * (c_mid - p_mid) if c_mid and p_mid else spot * math.exp(r * T)
    q = implied_carry(spot, forward, r, T)

    if with_greeks:
        for rw in rows:
            for cp in ("ce", "pe"):
                px = _mid({k[3:]: v for k, v in rw.items() if k.startswith(f"{cp}_")})
                iv = implied_vol(px, spot, rw["strike"], T, r, cp.upper(), q) if px else None
                rw[f"{cp}_iv"] = iv
                if iv:
                    for g, val in bs_greeks(spot, rw["strike"], T, r, iv, cp.upper(), q).items():
                        rw[f"{cp}_{g}"] = val

    return {"underlying": u, "exchange": exch, "expiry": expiry, "spot": spot, "spot_key": skey,
            "forward": forward, "atm_strike": atm, "T_years": T, "r": r, "q": q, "rows": rows,
            "lot_size": contracts[0]["lot_size"], "full_strike_range": strikes_each_side is None}


def pcr(chain: dict) -> dict[str, float | None]:
    ce_oi = sum(rw.get("ce_oi") or 0 for rw in chain["rows"])
    pe_oi = sum(rw.get("pe_oi") or 0 for rw in chain["rows"])
    ce_v = sum(rw.get("ce_volume") or 0 for rw in chain["rows"])
    pe_v = sum(rw.get("pe_volume") or 0 for rw in chain["rows"])
    return {"pcr_oi": pe_oi / ce_oi if ce_oi else None, "pcr_volume": pe_v / ce_v if ce_v else None,
            "ce_oi": ce_oi, "pe_oi": pe_oi}


def max_pain(chain: dict) -> float:
    """Strike at which option writers pay out the least (only over strikes present in the chain)."""
    rows = chain["rows"]

    def payout(s):
        return sum((rw.get("ce_oi") or 0) * max(s - rw["strike"], 0) +
                   (rw.get("pe_oi") or 0) * max(rw["strike"] - s, 0) for rw in rows)

    return min((rw["strike"] for rw in rows), key=payout)


def atm_iv(chain: dict) -> float | None:
    rw = next(x for x in chain["rows"] if x["strike"] == chain["atm_strike"])
    ivs = [v for v in (rw.get("ce_iv"), rw.get("pe_iv")) if v]
    return sum(ivs) / len(ivs) if ivs else None


def expected_move(chain: dict) -> float | None:
    """1-σ move to expiry from ATM IV: spot · σ · √T."""
    iv = atm_iv(chain)
    return chain["spot"] * iv * math.sqrt(chain["T_years"]) if iv else None


def find_by_delta(chain: dict, option_type: str, target_delta: float) -> dict:
    """Row whose |delta| is closest to target (e.g. 0.16 for a ~1-σ short strike)."""
    cp = option_type.lower()
    rows = [rw for rw in chain["rows"] if rw.get(f"{cp}_delta") is not None]
    return min(rows, key=lambda rw: abs(abs(rw[f"{cp}_delta"]) - target_delta))


def format_chain(chain: dict) -> str:
    def f(v, nd=2, w=8):
        return f"{v:>{w}.{nd}f}" if isinstance(v, (int, float)) else f"{'-':>{w}}"

    def oi(v):
        return f"{v / 1e5:>7.1f}L" if isinstance(v, (int, float)) else f"{'-':>8}"

    head = (f"{chain['underlying']} {chain['expiry']}  spot {chain['spot']:.2f}  fwd {chain['forward']:.2f}  "
            f"ATM {chain['atm_strike']:g}  lot {chain['lot_size']}")
    cols = f"{'CE OI':>8}{'CE IV%':>8}{'CE Δ':>7}{'CE LTP':>9} │{'STRIKE':^10}│{'PE LTP':>9}{'PE Δ':>7}{'PE IV%':>8}{'PE OI':>8}"
    lines = [head, cols, "─" * len(cols)]
    for rw in chain["rows"]:
        mark = "*" if rw["strike"] == chain["atm_strike"] else " "
        lines.append(
            f"{oi(rw.get('ce_oi'))}{f((rw.get('ce_iv') or 0) * 100 or None, 1)}{f(rw.get('ce_delta'), 2, 7)}"
            f"{f(rw.get('ce_ltp'), 2, 9)} │{mark}{rw['strike']:^8g}{mark}│{f(rw.get('pe_ltp'), 2, 9)}"
            f"{f(rw.get('pe_delta'), 2, 7)}{f((rw.get('pe_iv') or 0) * 100 or None, 1)}{oi(rw.get('pe_oi'))}"
        )
    p = pcr(chain)
    em = expected_move(chain)
    lines.append("─" * len(cols))
    lines.append(f"PCR(OI) {p['pcr_oi'] or 0:.2f}  max pain {max_pain(chain):g}  ATM IV "
                 f"{(atm_iv(chain) or 0) * 100:.1f}%  1σ move ±{em or 0:.0f}"
                 + ("" if chain["full_strike_range"] else "  (PCR/max-pain over displayed strikes only)"))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    from scripts.kite_common import get_client

    ap = argparse.ArgumentParser()
    ap.add_argument("underlying")
    ap.add_argument("--expiry", type=date.fromisoformat)
    ap.add_argument("--strikes", type=int, default=10)
    a = ap.parse_args()
    print(format_chain(build_chain(get_client(), a.underlying, a.expiry, a.strikes)))
