# Option Strategies on Kite

Legs use this skill's leg dict:

```python
{"strike": 25000.0, "option_type": "CE" | "PE" | "FUT", "side": "BUY" | "SELL",
 "quantity": lots * lot_size, "premium": entry_price, "tradingsymbol": "..."}
```

`strategy_stats(legs, low, high)` → `max_profit`, `max_loss` (number or `"unlimited"`),
`breakevens`, `net_premium` (+ = credit received).

## Catalogue

| Strategy | Legs | View | Max loss |
|---|---|---|---|
| Long call / put | BUY CE / BUY PE | Directional, long vol | Premium |
| Bull call spread | BUY CE K1, SELL CE K2 (K2>K1) | Moderately bullish | Net debit |
| Bear put spread | BUY PE K2, SELL PE K1 | Moderately bearish | Net debit |
| Bull put spread (credit) | SELL PE K2, BUY PE K1 | Neutral-bullish | Width − credit |
| Bear call spread (credit) | SELL CE K1, BUY CE K2 | Neutral-bearish | Width − credit |
| Long straddle | BUY CE + BUY PE ATM | Big move either way | Total premium |
| Short straddle | SELL CE + SELL PE ATM | Range-bound, short vol | **Unlimited** |
| Short strangle | SELL OTM CE + SELL OTM PE | Range-bound | **Unlimited** |
| Iron condor | Short strangle + long wings | Range-bound, defined risk | Wing width − credit |
| Iron butterfly | Short straddle + long wings | Pin near ATM | Wing width − credit |
| Calendar | SELL near expiry, BUY far expiry same K | Low near-term move, IV rise | Net debit (approx.) |
| Covered call | Long stock/future + SELL OTM CE | Mildly bullish, income | Stock downside |
| Protective put | Long stock/future + BUY PE | Hedge | Stock − K + premium |

## Building legs from a chain

```python
rows = {r["strike"]: r for r in chain["rows"]}
def leg(strike, cp, side, lots=1):
    r = rows[strike]; p = cp.lower()
    return {"strike": strike, "option_type": cp, "side": side,
            "quantity": lots * r[f"{p}_lot_size"], "premium": r[f"{p}_ltp"],
            "tradingsymbol": r[f"{p}_tradingsymbol"]}

atm = chain["atm_strike"]
straddle = [leg(atm, "CE", "SELL"), leg(atm, "PE", "SELL")]
```

Strike selection heuristics:
- By delta: `find_by_delta(chain, "PE", 0.16)` (≈ 1σ OTM), 0.25–0.30 for closer shorts.
- By expected move: `atm ± expected_move(chain)` rounded to the strike grid.
- Wings: fixed points (e.g. 100–300 on NIFTY) or ~0.05-delta.

## Net position Greeks

```python
def net_greeks(legs, chain):
    rows = {r["strike"]: r for r in chain["rows"]}
    tot = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for l in legs:
        s = 1 if l["side"] == "BUY" else -1
        if l["option_type"] == "FUT":
            tot["delta"] += s * l["quantity"]
            continue
        r = rows[l["strike"]]; p = l["option_type"].lower()
        for g in tot:
            tot[g] += s * l["quantity"] * (r.get(f"{p}_{g}") or 0)
    return tot   # delta in units of underlying; theta ₹/day; vega ₹/vol-pt
```

## Execution protocol (multi-leg)

1. Build legs → `strategy_stats` → `net_greeks` → basket margin (`final.total`) vs `margins("equity")["net"]`.
2. Show one table: leg, symbol, side, qty, limit price; totals; max P/L; breakevens; margin; charges
   (≈ ₹20 × legs × 2 + taxes).
3. One explicit confirmation for the whole structure.
4. Place **BUY legs first**, wait for `COMPLETE` on each (or at least `OPEN` with a fill plan), then SELL legs.
5. LIMIT at mid (rounded to tick); if unfilled after N seconds, step toward the touch by 1 tick, up to a
   user-approved max slippage. Never convert to MARKET silently.
6. On any leg failure → stop, report the partial position and what's needed to flatten.
7. Journal every leg (`kite-connect/scripts/trade_journal.py`).

Exit: reverse order — buy back shorts first, then sell longs.

## Adjustments (iron condor / strangle)

| Trigger | Typical adjustment |
|---|---|
| Spot approaches short strike (|Δ| of short > ~0.35) | Roll the untested side closer (collect more credit) or roll the tested side out |
| IV spike | Hold if within plan; close if max-loss rule hit |
| 50–70 % of max profit captured | Close early — remaining reward rarely worth gamma risk |
| Expiry day | Close or let worthless wings expire; avoid holding shorts into the last hour |

Always restate new max loss and margin after an adjustment and confirm again.

## Stock options: physical settlement

ITM stock options at expiry are **physically settled**. Long ITM call → you must buy lot_size shares;
short ITM put → same. Zerodha raises margin requirements progressively in expiry week and may square
off positions that can't be settled. Warn users holding stock options into expiry week.

## STT on exercise

Long index options that expire ITM are exercised automatically and STT is charged on the **intrinsic
value** (0.15 %), not on premium. For deep-ITM long options near expiry, selling before expiry is
usually cheaper.
