---
name: kite-options
description: >
  Use for Indian index/stock options analysis and multi-leg strategies on a
  Zerodha Kite Connect account: build an option chain (Kite has no
  option-chain endpoint), compute implied volatility and Greeks, PCR, max
  pain, expected move, IV skew, pick strikes by delta, construct and
  evaluate straddles, strangles, spreads, iron condors and butterflies
  (payoff, breakevens, max profit/loss, basket margin), and execute the
  legs safely. Triggers on NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY /
  SENSEX options, "option chain", "Greeks", "IV", "PCR", "max pain",
  "iron condor", "straddle", "hedge my position" when the broker is
  Zerodha/Kite. UNOFFICIAL community skill — not affiliated with Zerodha.
compatibility: >
  Python 3.9+, `pip install kiteconnect`. Live chains need the Kite Connect
  (paid) plan for quotes. Greeks/payoff maths (scripts/greeks.py) are pure
  standard library and work offline. Order placement follows the
  kite-connect skill's rules (static IP, market protection, confirmation).
---

# Kite Options — Chains, Greeks & Strategies

> **Unofficial**, community-maintained, not affiliated with Zerodha. Options can lose more than the
> premium when sold. Analysis here is educational, not investment advice.

## Setup

```python
from scripts.kite_common import get_client          # KITE_API_KEY + KITE_ACCESS_TOKEN
from scripts.option_chain import build_chain, format_chain, pcr, max_pain, atm_iv, expected_move, find_by_delta
from scripts.greeks import bs_price, bs_greeks, implied_vol, time_to_expiry, strategy_payoff, strategy_stats

kite = get_client()
chain = build_chain(kite, "NIFTY", expiry=None, strikes_each_side=10)   # nearest expiry
print(format_chain(chain))
```

CLI: `python scripts/option_chain.py BANKNIFTY --strikes 15`

For login and order mechanics see the **kite-connect** skill (`scripts/login.py`, `validate_order.py`).

## Safety Rules

1. All kite-connect safety rules apply (preview → explicit "yes" → place → verify → journal).
2. **Never sell naked options without saying so loudly**: show max loss = "unlimited" (calls) or
   strike × qty (puts), and the margin required.
3. Multi-leg orders: show every leg, net premium, max profit/loss, breakevens and
   `basket_order_margins(...)["final"]["total"]` **before** asking for one confirmation.
4. **Execution order:** place long (hedge) legs first, then short legs — otherwise the shorts are
   margined naked and may be rejected or block far more capital. Exit in reverse: shorts first.
5. If a leg fails, **stop** and report the partial position — don't keep firing the rest.
6. Quantity = lots × `lot_size` from the instruments dump. Never hardcode lot sizes.
7. Use LIMIT orders at mid / near bid-ask; options spreads are wide away from ATM.
8. Expiry day: warn about gamma risk and physical settlement for **stock** options (ITM stock options
   are physically settled — the user may get/give delivery of shares).

## Chain row schema

`build_chain` returns `{"underlying", "exchange", "expiry", "spot", "forward", "atm_strike", "T_years",
"r", "q", "lot_size", "rows": [...]}`; each row has `strike` and, per side (`ce_` / `pe_`):
`tradingsymbol`, `instrument_token`, `lot_size`, `tick_size`, `ltp`, `bid`, `ask`, `oi`, `oi_day_high`,
`oi_day_low`, `volume`, `iv`, `delta`, `gamma`, `theta` (₹/day per unit), `vega` (per vol pt), `rho`.

These field names are this skill's own, not Kite's.

## Key facts

- Index options (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY on NFO; SENSEX, BANKEX on BFO) are **European,
  cash-settled**, expiring 15:30 IST. Stock options are European and **physically settled**.
- Expiry calendars (which index has weeklies, which weekday) are set by the exchanges and have changed
  several times — always read `expiry` from the dump: `scripts/option_chain.list_expiries(kite, "NIFTY")`.
- IV is computed off a **synthetic forward** from ATM put-call parity, so dividends/carry are absorbed
  (equivalent to Black-76). Default `r = 6 %`; pass `r=` to override.
- PCR / max pain are computed only over the strikes you fetched; use `strikes_each_side=None` for the
  full chain (slower: more quote calls at 1 req/s).
- Quote API: ≤ 500 instruments per call, 1 req/s. A ±10-strike chain = 42 instruments = 1 call.

## Core patterns

### Pick strikes by delta and evaluate an iron condor

```python
from scripts.option_chain import find_by_delta
short_ce = find_by_delta(chain, "CE", 0.16)
short_pe = find_by_delta(chain, "PE", 0.16)
width = 200                                            # wing width in points
lot = chain["lot_size"]
rows = {r["strike"]: r for r in chain["rows"]}
legs = [
    {"strike": short_pe["strike"] - width, "option_type": "PE", "side": "BUY",  "quantity": lot},
    {"strike": short_ce["strike"] + width, "option_type": "CE", "side": "BUY",  "quantity": lot},
    {"strike": short_pe["strike"],         "option_type": "PE", "side": "SELL", "quantity": lot},
    {"strike": short_ce["strike"],         "option_type": "CE", "side": "SELL", "quantity": lot},
]
for l in legs:
    r = rows[l["strike"]]; p = l["option_type"].lower()
    l["premium"] = r[f"{p}_ltp"]; l["tradingsymbol"] = r[f"{p}_tradingsymbol"]
print(strategy_stats(legs, chain["spot"] * 0.85, chain["spot"] * 1.15))
```

Full build + margin + confirmed execution: `examples/iron_condor.py`.

### Basket margin for the legs

```python
margin_legs = [dict(exchange=chain["exchange"], tradingsymbol=l["tradingsymbol"],
                    transaction_type=l["side"], variety="regular", product="NRML",
                    order_type="LIMIT", quantity=l["quantity"], price=l["premium"], trigger_price=0)
               for l in legs]
m = kite.basket_order_margins(margin_legs, consider_positions=True)
m["initial"]["total"], m["final"]["total"]          # final = with hedge benefit
```

### Position Greeks (portfolio)

```python
net = [p for p in kite.positions()["net"] if p["quantity"] and p["exchange"] in ("NFO", "BFO")]
# match each position's tradingsymbol to chain rows → sum(quantity × delta), etc.
```

See [references/strategies.md](references/strategies.md) for the full net-Greeks helper.

## Reference files

| Need | File |
|---|---|
| Building/normalising chains, expiries, OI analytics (PCR, max pain, OI build-up) | [references/option-chain.md](references/option-chain.md) |
| BSM / Black-76 maths, IV solver, Greeks interpretation, skew | [references/greeks-and-iv.md](references/greeks-and-iv.md) |
| Strategy catalogue, construction, execution order, adjustments, exits | [references/strategies.md](references/strategies.md) |
