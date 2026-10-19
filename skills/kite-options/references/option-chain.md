# Option Chains on Kite

Kite Connect has **no option-chain API**. A chain is assembled from:

1. `kite.instruments("NFO")` (or `"BFO"` for SENSEX/BANKEX) — every live contract with `name`,
   `expiry`, `strike`, `instrument_type` (`CE`/`PE`), `lot_size`, `tick_size`, `tradingsymbol`.
2. `kite.quote(...)` — LTP, depth, OI, volume for the selected contracts (≤ 500 per call, 1 req/s).
3. Spot from `kite.ltp("NSE:NIFTY 50")` etc.

`scripts/option_chain.build_chain()` does all three and adds IV + Greeks.

## Underlyings

| `name` in dump | Spot key | Exchange |
|---|---|---|
| `NIFTY` | `NSE:NIFTY 50` | NFO |
| `BANKNIFTY` | `NSE:NIFTY BANK` | NFO |
| `FINNIFTY` | `NSE:NIFTY FIN SERVICE` | NFO |
| `MIDCPNIFTY` | `NSE:NIFTY MID SELECT` | NFO |
| `NIFTYNXT50` | `NSE:NIFTY NEXT 50` | NFO |
| `SENSEX` | `BSE:SENSEX` | BFO |
| `BANKEX` | `BSE:BANKEX` | BFO |
| stock, e.g. `RELIANCE` | `NSE:RELIANCE` | NFO |

## Expiries

```python
from scripts.option_chain import list_expiries
list_expiries(kite, "NIFTY")      # [date(...), ...] sorted
```

- "Weekly" vs "monthly": the monthly is the last expiry of the calendar month. Kite's tradingsymbol
  format differs (`NIFTY25O21…` vs `NIFTY25OCT…`) — don't parse it, use the `expiry` field.
- When the expiry day is a holiday, the exchange moves it to the previous trading day; the dump already
  reflects that.

## Choosing the strike window

| Use | `strikes_each_side` | Quote calls |
|---|---|---|
| Quick look, ATM trades | 5–10 | 1 |
| Condor / strangle selection | 15–25 | 1 |
| PCR / max pain over the whole series | `None` | many (≈ contracts / 500) |

## OI analytics

### PCR

`pcr(chain)` → `{"pcr_oi", "pcr_volume", "ce_oi", "pe_oi"}`.

Rough reading (context-dependent, not a signal on its own): PCR(OI) well above 1 means heavy put
writing, often read as support below. Well below ~0.7 means call writing dominates. Compare to the
same underlying's own history, not a universal threshold.

### Max pain

`max_pain(chain)` — strike minimising total intrinsic payout to option buyers. Tends to matter only
close to expiry and in low-volatility sessions. Treat it as descriptive.

### OI walls / support-resistance

```python
rows = chain["rows"]
call_wall = max(rows, key=lambda r: r.get("ce_oi") or 0)["strike"]
put_wall  = max(rows, key=lambda r: r.get("pe_oi") or 0)["strike"]
```

### OI build-up (needs two snapshots)

Kite's quote has `oi`, `oi_day_high`, `oi_day_low` but no "change in OI since yesterday". Store a
snapshot (e.g. at 09:20) and diff it later, or use `historical_data(token, ..., "day", oi=True)` for
the previous close OI.

| Price | OI | Interpretation |
|---|---|---|
| ↑ | ↑ | Long build-up |
| ↓ | ↑ | Short build-up |
| ↑ | ↓ | Short covering |
| ↓ | ↓ | Long unwinding |

## Live chain via WebSocket

For a continuously updating chain, subscribe the `ce_instrument_token` / `pe_instrument_token` of the
rows in `MODE_FULL` with KiteTicker and update `ltp`, `oi`, depth from ticks; recompute IV lazily (e.g.
once per second), not on every tick.

## Expired contracts

Expired options vanish from the dump and Kite has no expired-options history endpoint. For backtests on
options, record tokens + candles while contracts are live (see kite-backtest).
