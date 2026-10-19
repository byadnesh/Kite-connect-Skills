# Instruments & Symbols

## The instruments dump

```python
rows = kite.instruments()        # every exchange (~100k+ rows, slow)
rows = kite.instruments("NFO")   # one exchange — preferred
```

Generated once a day (~08:30 IST). Cache it (see `scripts/instruments.py`, which caches per IST day under
`~/.kite-skills/cache`). Each row:

| Field | Example | Notes |
|---|---|---|
| `instrument_token` | `256265` | int — used for historical + WebSocket |
| `exchange_token` | `1001` | exchange-side id |
| `tradingsymbol` | `NIFTY25OCT25000CE` | used for orders / quote keys |
| `name` | `NIFTY` | underlying for F&O; company name for equity |
| `last_price` | `0.0` | stale — don't use |
| `expiry` | `date(2025,10,28)` | `None` for cash |
| `strike` | `25000.0` | 0 for non-options |
| `tick_size` | `0.05` | price step |
| `lot_size` | `75` | contract multiplier — **always read from here** |
| `instrument_type` | `EQ` `FUT` `CE` `PE` | |
| `segment` | `NSE` `BSE` `NFO-OPT` `NFO-FUT` `BFO-OPT` `MCX-FUT` `CDS-OPT` `INDICES` | |
| `exchange` | `NSE` `NFO` … | |

## Helper API (`scripts/instruments.py`)

```python
from scripts.instruments import (load_instruments, find_equity, search, list_expiries,
                                 find_future, find_option, option_strikes, quote_key,
                                 derivative_exchange, INDEX_TOKENS, UNDERLYING_SPOT)

find_equity(kite, "HDFCBANK")                     # exact NSE cash symbol
find_equity(kite, "NIFTY 50")                     # index row (segment INDICES, not tradable)
search(kite, "tata motors")                        # fuzzy on symbol + name
list_expiries(kite, "NIFTY")                       # [date, ...] options expiries, NFO
list_expiries(kite, "SENSEX")                      # auto-routes to BFO
find_future(kite, "RELIANCE")                      # nearest month future
find_option(kite, "BANKNIFTY", None, 56000, "PE")  # nearest expiry
quote_key(row)                                     # "NFO:BANKNIFTY..."
```

`find_option` raises `LookupError` with the nearest listed strike if the strike doesn't exist.

## Symbol formats (for reading, never for building)

| Kind | Pattern | Example |
|---|---|---|
| Equity | `SYMBOL` | `INFY`, `M&M`, `BAJAJ-AUTO` |
| Monthly future | `UNDERLYING YY MON FUT` | `NIFTY25OCTFUT` |
| Monthly option | `UNDERLYING YY MON STRIKE CE/PE` | `NIFTY25OCT25000CE` |
| Weekly option | `UNDERLYING YY M DD STRIKE CE/PE` (M = 1–9, O, N, D) | `NIFTY25O2125000CE` |
| MCX future | `COMMODITY YY MON FUT` | `CRUDEOIL25NOVFUT` |
| Currency | `PAIR YY MON FUT` | `USDINR25OCTFUT` |

The last weekly expiry of a month uses the monthly format. Because of this, **always resolve from the dump.**

## Index reference

| Index | Quote key | Token | F&O name | F&O exchange |
|---|---|---|---|---|
| NIFTY 50 | `NSE:NIFTY 50` | 256265 | `NIFTY` | NFO |
| NIFTY BANK | `NSE:NIFTY BANK` | 260105 | `BANKNIFTY` | NFO |
| NIFTY FIN SERVICE | `NSE:NIFTY FIN SERVICE` | 257801 | `FINNIFTY` | NFO |
| NIFTY MID SELECT | `NSE:NIFTY MID SELECT` | 288009 | `MIDCPNIFTY` | NFO |
| INDIA VIX | `NSE:INDIA VIX` | 264969 | – | – |
| SENSEX | `BSE:SENSEX` | 265 | `SENSEX` | BFO |

Expiry calendars and lot sizes are revised by exchanges from time to time (e.g. weekly expiries are now
limited to one benchmark index per exchange). Read `expiry` and `lot_size` from the dump every day
instead of relying on memory.

## Mutual fund instruments

`kite.mf_instruments()` — separate list keyed by ISIN-style `tradingsymbol` (e.g. `INF209K01VA3`), with
`fund_house`, `scheme_type`, `plan`, `dividend_type`, `minimum_purchase_amount`, `purchase_allowed`, `last_price` (NAV).
