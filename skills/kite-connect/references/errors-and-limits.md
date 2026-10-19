# Errors, Rate Limits & Retry Policy

## Exception classes (pykiteconnect)

`from kiteconnect import exceptions as kex`

| Exception | HTTP | Meaning | Agent action |
|---|---|---|---|
| `TokenException` | 403 | Token expired / logged out / logged in elsewhere | Stop. Ask user to run `scripts/login.py`. No retry |
| `PermissionException` | 403 | Not allowed — e.g. market data on Personal plan, segment not enabled | Explain; no retry |
| `InputException` | 400 | Bad/missing param (lot size, tick size, product, trigger) | Fix params, re-validate, re-confirm |
| `OrderException` | 500 | Order placement/fetch failed at OMS | Check order book before anything else |
| `NetworkException` | 503 | API couldn't reach OMS / exchange | Reads: retry with backoff. Orders: check book first |
| `DataException` | 502 | Couldn't parse OMS response | Same as NetworkException |
| `GeneralException` | 500 | Everything else — **incl. margin and holding shortfalls** | Show message verbatim |

The REST API's `error_type` also includes `MarginException`, `HoldingException`, `UserException`; the Python
SDK surfaces unknown types as `GeneralException`. Inspect `str(e)` and `e.code`.

## HTTP codes

| Code | Meaning |
|---|---|
| 400 | Bad parameters |
| 403 | Session expired / no permission |
| 404 | Not found |
| 405 | Method not allowed |
| 410 | Resource gone |
| 429 | Rate limited |
| 500 | Server error |
| 502 | OMS down |
| 503 | Service unavailable |
| 504 | Gateway timeout |

## Rate limits

| Scope | Limit |
|---|---|
| Quote (`ltp`/`ohlc`/`quote`) | 1 req/s |
| Historical | 3 req/s |
| Orders | 10 req/s · 400/min · 5,000/day per user |
| Other endpoints | 10 req/s |
| Modifications per order | 25 |
| WebSocket | 3 connections × 3,000 instruments |
| Active alerts | 500 |

## Retry policy

```python
import time, random
from kiteconnect import exceptions as kex

RETRYABLE = (kex.NetworkException, kex.DataException)

def with_retry(fn, *a, attempts=4, **kw):
    """For READ calls only (quotes, history, orders(), positions())."""
    for i in range(attempts):
        try:
            return fn(*a, **kw)
        except RETRYABLE:
            if i == attempts - 1:
                raise
            time.sleep(min(8, 2 ** i) + random.random() / 2)
        except kex.GeneralException as e:
            if "Too many requests" in str(e) and i < attempts - 1:
                time.sleep(1 + i)
                continue
            raise
```

**Orders are never auto-retried.** On any exception from `place_order`:

1. `kite.orders()` → look for a matching `tag` + symbol + qty placed in the last minute.
2. If found, report its status. If not, tell the user it failed and ask before trying again.

## Frequent rejection messages → fix

| Message (contains) | Fix |
|---|---|
| `Markets are closed` / `outside market hours` | Offer `variety="amo"` |
| `lot size` / `multiple of` | Quantity must be N × `lot_size` |
| `tick size` | Round price to `tick_size` |
| `Insufficient funds` / `margin` | Show `basket_order_margins` vs `margins()` gap |
| `market protection` | Pass `market_protection=-1` for MARKET / SL-M |
| `IP` / `not whitelisted` | Add/verify static IP in developer console; requests must originate from it |
| `circuit` / `price band` | Price outside daily limits — use `quote()["lower/upper_circuit_limit"]` |
| `Trigger price` | BUY SL trigger must be above LTP; SELL SL below |
| `freeze` | Use `place_autoslice_order` |
| `not allowed` + product | Segment/product not enabled — user enables in Console |
| `holdings` / `authoris` | CDSL TPIN authorisation needed in Kite |
