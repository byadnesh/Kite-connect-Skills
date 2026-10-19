# Greeks & Implied Volatility

`scripts/greeks.py` — pure standard library.

## Model

Black-Scholes-Merton with continuous carry `q`:

```
d1 = [ln(S/K) + (r − q + σ²/2)T] / (σ√T),   d2 = d1 − σ√T
C  = S e^{−qT} N(d1) − K e^{−rT} N(d2)
P  = K e^{−rT} N(−d2) − S e^{−qT} N(−d1)
```

Setting `q = r − ln(F/S)/T` for a forward `F` makes this identical to **Black-76** on the forward.
`build_chain` gets `F` from ATM put-call parity: `F = K_atm + e^{rT}(C_atm − P_atm)`, which absorbs
dividends, carry and the futures basis without needing a dividend forecast.

## Units

| Greek | Unit returned |
|---|---|
| `delta` | per ₹1 move in spot (per unit of underlying) |
| `gamma` | change in delta per ₹1 |
| `theta` | ₹ per **calendar day** per unit |
| `vega` | ₹ per **1 vol point** (σ + 0.01) per unit |
| `rho` | ₹ per 1 % rate change per unit |

Multiply by `quantity` (lots × lot_size) for position Greeks. Signs flip for short legs.

## Time to expiry

`time_to_expiry(expiry_date)` → years until 15:30 IST on expiry, `seconds / (365·24·3600)`.
Calendar-day convention means theta keeps accruing over weekends — consistent with how option prices
actually decay into Monday. For intraday expiry-day work, T is tiny; IV becomes noisy and Greeks
explode. Prefer price-based reasoning on expiry day.

## IV solver

`implied_vol(price, S, K, T, r, "CE", q)` — bisection on σ ∈ [0.01 %, 500 %]. Returns `None` when:
- price ≤ 0 or missing,
- price below the no-arbitrage lower bound (stale LTP on illiquid strikes is the usual cause),
- price above the σ=500 % value.

Use **mid price** (bid+ask)/2 when both sides exist; fall back to LTP. `build_chain` does this.

## Reading the numbers

- **ATM IV** — `atm_iv(chain)`. Compare with INDIA VIX (`NSE:INDIA VIX`, a 30-day NIFTY IV index) and
  with the series' own recent range.
- **Expected move** — `expected_move(chain)` = S·σ·√T, ~68 % one-sigma range to expiry. Short strikes
  outside ±1σ correspond roughly to 16-delta.
- **Skew** — puts usually trade at higher IV than equidistant calls in Indian indices. Compute
  `pe_iv(K_otm_put) − ce_iv(K_otm_call)` at equal |delta| (e.g. 25-delta risk reversal).
- **Term structure** — build chains for two expiries, compare ATM IV. Near > far (inverted) often
  around events (budget, RBI policy, elections, results).

## Sanity checks

```python
from scripts.greeks import bs_price, implied_vol
p = bs_price(25000, 25000, 7/365, 0.06, 0.12, "CE")
assert abs(implied_vol(p, 25000, 25000, 7/365, 0.06, "CE") - 0.12) < 1e-4
```

Put-call parity check on a chain row (should be ≈ 0 with the chain's `q`):

```python
import math
lhs = row["ce_ltp"] - row["pe_ltp"]
rhs = chain["spot"] * math.exp(-chain["q"] * chain["T_years"]) - row["strike"] * math.exp(-chain["r"] * chain["T_years"])
```

Large deviations = stale quotes or illiquid strike; don't trade off them.
