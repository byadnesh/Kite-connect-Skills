# Market Data: Quotes & Historical Candles

All endpoints here need the **Connect** (paid) plan.

## Quote keys

`"EXCHANGE:TRADINGSYMBOL"` — e.g. `"NSE:INFY"`, `"BSE:500325"` or `"BSE:RELIANCE"`, `"NFO:NIFTY25OCT25000CE"`,
`"NSE:NIFTY 50"`, `"NSE:NIFTY BANK"`, `"BSE:SENSEX"`, `"MCX:CRUDEOIL25NOVFUT"`.

You may also pass instrument tokens as strings, but the response is keyed by what you sent.

## LTP / OHLC / full quote

| Method | Max instruments/call | Returns |
|---|---|---|
| `kite.ltp(*keys)` | 1000 | `instrument_token`, `last_price` |
| `kite.ohlc(*keys)` | 1000 | + `ohlc{open,high,low,close}` (close = previous close) |
| `kite.quote(*keys)` | 500 | full snapshot incl. 5-level depth |

All three share the **1 request/second** limit. Batch keys into one call instead of looping.

```python
q = kite.quote("NSE:INFY", "NSE:TCS")["NSE:INFY"]
q["last_price"], q["volume"], q["average_price"], q["net_change"]
q["ohlc"]                      # day open/high/low + previous close
q["oi"], q["oi_day_high"], q["oi_day_low"]   # F&O
q["lower_circuit_limit"], q["upper_circuit_limit"]
q["buy_quantity"], q["sell_quantity"]
q["depth"]["buy"][0]           # {"price", "quantity", "orders"} × 5
q["last_trade_time"], q["timestamp"]
```

Day change % = `(last_price - ohlc.close) / ohlc.close * 100`.

### Batched snapshot helper

```python
import time
def batched_quotes(kite, keys, method="quote", size=None):
    size = size or (500 if method == "quote" else 1000)
    out = {}
    for i in range(0, len(keys), size):
        out.update(getattr(kite, method)(*keys[i:i + size]))
        time.sleep(1.05)                 # respect 1 req/s
    return out
```

## Historical candles

```python
kite.historical_data(instrument_token, from_date, to_date, interval, continuous=False, oi=False)
```

- `instrument_token`: int (from instruments dump). Not the tradingsymbol.
- `from_date` / `to_date`: `datetime`, `date`, or `"YYYY-MM-DD HH:MM:SS"` (IST).
- `interval`: `minute`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`, `60minute`, `day`.
- `continuous=True`: stitched day candles across expired monthly futures (NFO/MCX futures only, `day` interval).
- `oi=True`: adds `oi` to each candle (F&O).
- Returns `[{"date": datetime(tz=+05:30), "open", "high", "low", "close", "volume"[, "oi"]}, ...]`.
- Rate limit: **3 requests/second**.

### Max range per request (observed; chunk longer ranges)

| Interval | Max days / call |
|---|---|
| minute | 60 |
| 3/5/10minute | 100 |
| 15/30minute | 200 |
| 60minute | 400 |
| day | 2000 |

Chunked fetcher with pandas output: see the **kite-backtest** skill (`scripts/fetch_history.py`).

### Gotchas

- Expired option/futures contracts disappear from the instruments dump — you can't look up their token
  later. Save tokens you care about. Only futures have `continuous` history.
- Daily candles for the current day form only after close; intraday `day` candle reflects live values.
- Volume for indices is 0.
- Timestamps are candle **open** times in IST.
- Corporate actions: historical equity prices are not adjusted for every action — sanity-check around
  splits/bonuses.

## Example: 6 months daily OHLC for RELIANCE

```python
from datetime import date, timedelta
from scripts.instruments import find_equity
tok = find_equity(kite, "RELIANCE")["instrument_token"]
rows = kite.historical_data(tok, date.today() - timedelta(days=182), date.today(), "day")
```
