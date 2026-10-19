# Fetching Historical Data from Kite

`kite.historical_data(instrument_token, from_date, to_date, interval, continuous=False, oi=False)`

## Intervals & per-request span

| Interval | Max days per call (observed) | Typical use |
|---|---|---|
| `minute` | 60 | Execution research, ORB, scalping |
| `3minute` `5minute` `10minute` | 100 | Intraday systems |
| `15minute` `30minute` | 200 | Swing-intraday |
| `60minute` | 400 | Multi-day swing |
| `day` | 2000 | Positional, portfolio |

`scripts/fetch_history.chunk_ranges()` splits any range into compliant chunks; `fetch_candles()`
calls them at ≤ 3 req/s, retries transient errors, de-duplicates by timestamp and returns rows
sorted oldest → newest.

## Candle format

```python
{"date": datetime(2026, 9, 30, 9, 15, tzinfo=+05:30), "open": 1.0, "high": 1.0, "low": 1.0,
 "close": 1.0, "volume": 123, "oi": 456}   # "oi" only with oi=True
```

`date` is the candle **open** time in IST.

## Tokens

- Equity / index: `find_equity_token(kite, "RELIANCE")`, `find_equity_token(kite, "NIFTY 50")` → 256265.
- Futures: from `kite.instruments("NFO")` rows where `name == "NIFTY"` and `instrument_type == "FUT"`.
- Options: same with `CE`/`PE`, **only while live**.

## Continuous futures

`continuous=True` (with `interval="day"`) on a **live** futures token returns stitched day candles over
expired monthly contracts — the only way to get long futures history on Kite. Roll gaps are not
back-adjusted; for return-based signals use `close / prev_close` within the same contract or apply your
own roll adjustment.

## Caching

- Completed ranges (end date before today) are cached as JSON under `~/.kite-skills/history/`.
- `write_csv(rows, path)` / `read_csv(path)` for portable datasets you can version outside the repo.
- Never commit market data dumps to a public repo — redistribution of exchange data is restricted.

## Building a universe

```python
rows = load_instruments(kite, "NSE")
eq = [r for r in rows if r["segment"] == "NSE" and r["instrument_type"] == "EQ"]
```

That's every listed equity **today** (survivorship bias). For index-constituent universes, use the NSE
index constituent CSVs as of each rebalance date if you have them; otherwise state the bias.

## Throughput math

A 5-year 5-minute history = 1826 days / 100 ≈ 19 calls ≈ 7 s per symbol at 3 req/s. 200 symbols ≈ 25 min.
Run large pulls in the background and cache.
