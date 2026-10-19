#!/usr/bin/env python3
"""Black-Scholes(-Merton) pricing, Greeks, implied volatility and payoff maths.

UNOFFICIAL — not affiliated with Zerodha. Pure standard library.

Conventions
- T in years (calendar: days / 365). Indian index options are European, expiring 15:30 IST.
- r: continuously-compounded risk-free rate (default 6 %), q: carry/dividend yield.
  Pass `q = implied_carry(spot, forward, r, T)` to price off a synthetic forward
  (equivalent to Black-76) — this is what option_chain.py does.
- theta is per calendar day, vega per 1 vol point (0.01), rho per 1 % rate move.

    >>> round(bs_price(100, 100, 1, 0.05, 0.2, "CE"), 4)
    10.4506
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
SQRT2 = math.sqrt(2.0)
DEFAULT_R = 0.06


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def time_to_expiry(expiry: date, now: datetime | None = None, expiry_time: time = time(15, 30)) -> float:
    """Years until expiry_time IST on the expiry date (floored at ~1 minute)."""
    now = (now or datetime.now(IST)).astimezone(IST)
    exp_dt = datetime.combine(expiry, expiry_time, IST)
    return max((exp_dt - now).total_seconds(), 60.0) / (365.0 * 24 * 3600)


def implied_carry(spot: float, forward: float, r: float, T: float) -> float:
    """q such that forward = spot * exp((r - q) T)."""
    return r - math.log(forward / spot) / T


def _d1_d2(S, K, T, r, sigma, q):
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    return d1, d1 - vt


def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str, q: float = 0.0) -> float:
    cp = option_type.upper()
    if T <= 0 or sigma <= 0:
        fwd_disc = S * math.exp(-q * max(T, 0)) - K * math.exp(-r * max(T, 0))
        return max(fwd_disc, 0.0) if cp == "CE" else max(-fwd_disc, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if cp == "CE":
        return S * math.exp(-q * T) * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * math.exp(-q * T) * norm_cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str, q: float = 0.0) -> dict:
    cp = option_type.upper()
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    eqt, ert, sq = math.exp(-q * T), math.exp(-r * T), math.sqrt(T)
    pdf = norm_pdf(d1)
    gamma = eqt * pdf / (S * sigma * sq)
    vega = S * eqt * pdf * sq / 100.0
    if cp == "CE":
        delta = eqt * norm_cdf(d1)
        theta = (-S * eqt * pdf * sigma / (2 * sq) - r * K * ert * norm_cdf(d2) + q * S * eqt * norm_cdf(d1))
        rho = K * T * ert * norm_cdf(d2) / 100.0
    else:
        delta = -eqt * norm_cdf(-d1)
        theta = (-S * eqt * pdf * sigma / (2 * sq) + r * K * ert * norm_cdf(-d2) - q * S * eqt * norm_cdf(-d1))
        rho = -K * T * ert * norm_cdf(-d2) / 100.0
    return {"delta": delta, "gamma": gamma, "theta": theta / 365.0, "vega": vega, "rho": rho}


def implied_vol(price: float, S: float, K: float, T: float, r: float, option_type: str, q: float = 0.0,
                lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-6, max_iter: int = 200) -> float | None:
    """Bisection IV. Returns None when price is outside no-arbitrage bounds or missing."""
    if not price or price <= 0 or T <= 0:
        return None
    lower = bs_price(S, K, T, r, lo, option_type, q)
    upper = bs_price(S, K, T, r, hi, option_type, q)
    if price < lower - 1e-9 or price > upper:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, r, mid, option_type, q) > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------- payoff
# A leg: {"strike": float, "option_type": "CE"|"PE"|"FUT", "side": "BUY"|"SELL",
#         "quantity": int (units, i.e. lots * lot_size), "premium": float (entry price)}

def leg_payoff(leg: dict, spot_at_expiry: float) -> float:
    s = 1 if leg["side"].upper() == "BUY" else -1
    t = leg["option_type"].upper()
    if t == "CE":
        value = max(spot_at_expiry - leg["strike"], 0.0)
    elif t == "PE":
        value = max(leg["strike"] - spot_at_expiry, 0.0)
    else:  # FUT: strike = entry price
        value = spot_at_expiry
    return s * (value - leg["premium"]) * leg["quantity"]


def strategy_payoff(legs: list[dict], spot_at_expiry: float) -> float:
    return sum(leg_payoff(leg, spot_at_expiry) for leg in legs)


def strategy_stats(legs: list[dict], low: float, high: float, steps: int = 2000) -> dict:
    """Max profit / loss, breakevens on [low, high]; flags unbounded wings by edge slope."""
    xs = [low + (high - low) * i / steps for i in range(steps + 1)]
    ks = sorted({leg["strike"] for leg in legs if leg["option_type"].upper() in ("CE", "PE")})
    xs = sorted(set(xs + [k for k in ks if low <= k <= high]))
    ys = [strategy_payoff(legs, x) for x in xs]
    breakevens = []
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if y0 == 0:
            breakevens.append(x0)
        elif y0 * y1 < 0:
            breakevens.append(x0 + (x1 - x0) * (-y0) / (y1 - y0))
    # Price is floored at 0, so only the upside can be unbounded; the downside extreme is the payoff at 0.
    slope_hi = ys[-1] - ys[-2]
    extremes = ys + [strategy_payoff(legs, 0.0)]
    return {
        "max_profit": "unlimited" if slope_hi > 1e-9 else max(extremes),
        "max_loss": "unlimited" if slope_hi < -1e-9 else min(extremes),
        "breakevens": [round(b, 2) for b in breakevens],
        "net_premium": sum((-1 if l["side"].upper() == "BUY" else 1) * l["premium"] * l["quantity"]
                           for l in legs if l["option_type"].upper() in ("CE", "PE")),
    }


if __name__ == "__main__":
    import doctest

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    doctest.testmod(verbose=False)
    S, K, T, r, v = 25000, 25000, 7 / 365, DEFAULT_R, 0.12
    for cp in ("CE", "PE"):
        p = bs_price(S, K, T, r, v, cp)
        print(cp, round(p, 2), {k: round(x, 4) for k, x in bs_greeks(S, K, T, r, v, cp).items()},
              "iv", round(implied_vol(p, S, K, T, r, cp), 4))
