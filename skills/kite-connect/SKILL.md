---
name: kite-connect
description: >
  Use when the user mentions Zerodha, Kite, Kite Connect, KiteTicker,
  pykiteconnect, or wants to trade or pull data on Indian exchanges
  (NSE, BSE, NFO, BFO, MCX, CDS) through a Zerodha account. Triggers for:
  logging in / generating an access token; placing, modifying, cancelling
  or exiting orders (regular, AMO, iceberg, auction, autoslice); GTT
  (single / OCO) and price alerts; holdings, positions, position
  conversion; funds and margins (order, basket, contract-note charges);
  LTP / OHLC / full quotes; historical candles; resolving tradingsymbols
  and instrument tokens; streaming ticks or order updates over WebSocket;
  mutual fund orders and SIPs; any trading automation for a Zerodha
  account. UNOFFICIAL community skill — not affiliated with Zerodha.
compatibility: >
  Python 3.9+ and `pip install kiteconnect` (5.x). Needs a Kite Connect
  developer app (api_key + api_secret) and a daily access token. Market
  data (quotes, historical, WebSocket) needs the paid Connect plan; the
  free Personal plan covers orders, GTT, alerts, portfolio and margins
  only. Since 1 April 2026 order endpoints only accept requests from the
  static IP whitelisted in the Kite developer console.
---

# Kite Connect (Zerodha) — Indian Market Trading Skill

> **Unofficial.** Community-maintained. Not built, endorsed or supported by
> Zerodha Broking Ltd. Kite, Kite Connect and Zerodha are their trademarks.
> Every live order is real money — follow the safety rules below without exception.

## Setup

```bash
pip install --upgrade kiteconnect
```

Credentials come from the environment — never from code, chat, or files in the repo:

| Variable | Needed for | Lifetime |
|---|---|---|
| `KITE_API_KEY` | everything | permanent (per app) |
| `KITE_API_SECRET` | only the one-time `generate_session` step | permanent — keep secret |
| `KITE_ACCESS_TOKEN` | every API call | expires ~06:00 IST next day |

```python
import os
from kiteconnect import KiteConnect

kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
kite.set_access_token(os.environ["KITE_ACCESS_TOKEN"])
```

Inside this skill, prefer the helper — it also reads the token cached by the login script and fails with a clear message when the token is stale:

```python
from scripts.kite_client import get_client
kite = get_client()
```

### Getting the daily access token

The login is **interactive by regulation** (2FA in a browser). Run:

```bash
python scripts/login.py
```

It opens the Kite login page, captures `request_token` from the redirect,
calls `generate_session`, and caches the token at `~/.kite-skills/session.json`
(mode 600). Full flow and the manual variant: [references/auth.md](references/auth.md).

**Never** automate the login with the user's password or TOTP secret, and never
ask the user to paste their Zerodha password, PIN or TOTP seed into the chat.

## Safety Rules — Always Enforce

1. **Preview, then confirm.** Before any call that changes state (`place_order`,
   `modify_order`, `cancel_order`, `exit_order`, `convert_position`, `place_gtt`,
   `modify_gtt`, `delete_gtt`, MF orders/SIPs, alerts with type `ato`), print a
   readable preview and wait for an explicit "yes" from the user. One approval = one action.
2. **Run `scripts/validate_order.py` first.** Do not place an order with errors; show every warning.
3. **Default to `LIMIT`.** Use `MARKET` / `SL-M` only when the user asks, and then always pass
   `market_protection` (`-1` = exchange-auto, or `1–100` %). Orders with `0` / missing protection are rejected.
4. **Default quantity = 1 share or 1 lot.** Never guess bigger.
5. **F&O quantity must be a multiple of `lot_size`** from the instruments dump — never hardcode lot sizes.
6. **Product rules:** `CNC`/`MTF` only on NSE/BSE cash; `NRML` only on F&O/commodity/currency; `MIS` anywhere.
7. **Warn** when notional > ₹50,000 (override with `KITE_MAX_ORDER_VALUE`), when the limit price is > 5 % away from LTP, and for any naked option sell.
8. **Market closed?** Say so and offer `variety="amo"` instead of silently placing.
9. **Tag every order** (`tag="kiteskill"` or user-provided, ≤ 20 alphanumeric chars) so agent orders are traceable.
10. **Never** print, log or commit the API secret or access token. Mask them as `abcd…wxyz`.
11. **Log** every placed/modified/cancelled order with `scripts/trade_journal.py`.
12. A successful `place_order` only returns an `order_id` — **always re-check status** with `order_history()` before telling the user it executed.

## Plans & Access (2026)

| Capability | Personal (free) | Connect (₹500/mo per app) |
|---|:-:|:-:|
| Orders, GTT, alerts, MF | Yes | Yes |
| Holdings, positions, margins, charges | Yes | Yes |
| `ltp` / `ohlc` / `quote` | No | Yes |
| `historical_data` | No | Yes (included since Feb 2025) |
| WebSocket ticks (`KiteTicker`) | No | Yes |

If a data call fails with a permission error, the user is on the Personal plan — tell them, don't retry.

Compliance (SEBI retail-algo framework, enforced by Zerodha from 1 Apr 2026): static IP for order
endpoints, max 10 orders/sec, mandatory market protection, autoslice capped at 10 slices.
Details: [references/compliance.md](references/compliance.md).

## SDK Constants

| Category | Constant | Value |
|---|---|---|
| Exchange | `kite.EXCHANGE_NSE` / `EXCHANGE_BSE` | `NSE` / `BSE` (cash) |
| | `kite.EXCHANGE_NFO` / `EXCHANGE_BFO` | `NFO` / `BFO` (F&O) |
| | `kite.EXCHANGE_MCX` | `MCX` (commodity) |
| | `kite.EXCHANGE_CDS` / `EXCHANGE_BCD` | `CDS` / `BCD` (currency) |
| Transaction | `TRANSACTION_TYPE_BUY` / `_SELL` | `BUY` / `SELL` |
| Order type | `ORDER_TYPE_LIMIT` / `_MARKET` / `_SL` / `_SLM` | `LIMIT` / `MARKET` / `SL` / `SL-M` |
| Product | `PRODUCT_CNC` / `_MIS` / `_NRML` | `CNC` / `MIS` / `NRML` (also `"MTF"` as a string) |
| Variety | `VARIETY_REGULAR` / `_AMO` / `_ICEBERG` / `_AUCTION` / `_CO` | `regular` / `amo` / `iceberg` / `auction` / `co` |
| Validity | `VALIDITY_DAY` / `_IOC` / `_TTL` | `DAY` / `IOC` / `TTL` |
| Market protection | `MARKET_PROTECTION_AUTO` | `-1` |
| GTT | `GTT_TYPE_SINGLE` / `GTT_TYPE_OCO` | `single` / `two-leg` |
| Margin segment | `MARGIN_EQUITY` / `MARGIN_COMMODITY` | `equity` / `commodity` |

## SDK Methods To Use

| Task | Method |
|---|---|
| Login URL / session | `kite.login_url()`, `kite.generate_session(request_token, api_secret)` |
| Profile / logout | `kite.profile()`, `kite.invalidate_access_token()` |
| Funds | `kite.margins()` / `kite.margins("equity")` |
| Place order | `kite.place_order(variety, exchange, tradingsymbol, transaction_type, quantity, product, order_type, price=, trigger_price=, validity=, tag=, market_protection=)` |
| Place > freeze qty | `kite.place_autoslice_order(...)` (same args) |
| Modify / cancel / exit | `kite.modify_order(variety, order_id, ...)`, `kite.cancel_order(variety, order_id)`, `kite.exit_order(...)` |
| Order book / history | `kite.orders()`, `kite.order_history(order_id)` |
| Trades | `kite.trades()`, `kite.order_trades(order_id)` |
| Holdings / positions | `kite.holdings()`, `kite.positions()` → `{"net": [...], "day": [...]}` |
| Convert position | `kite.convert_position(exchange, tradingsymbol, transaction_type, position_type, quantity, old_product, new_product)` |
| Quotes | `kite.ltp(*keys)`, `kite.ohlc(*keys)`, `kite.quote(*keys)` — keys like `"NSE:INFY"` |
| Historical candles | `kite.historical_data(instrument_token, from_date, to_date, interval, continuous=False, oi=False)` |
| Instruments dump | `kite.instruments("NFO")` (list of dicts; call once per day, cache) |
| Order margin | `kite.order_margins([order_dict, ...])` |
| Basket margin | `kite.basket_order_margins([...], consider_positions=True)` |
| Exact charges | `kite.get_virtual_contract_note([...])` |
| GTT | `kite.place_gtt(...)`, `get_gtts()`, `get_gtt(id)`, `modify_gtt(...)`, `delete_gtt(id)` |
| Alerts | REST only (`/alerts`) — use `scripts/kite_client.py: alerts_request()` |
| Mutual funds | `place_mf_order`, `mf_orders`, `place_mf_sip`, `mf_sips`, `mf_holdings`, `mf_instruments` |
| Live ticks / order updates | `KiteTicker(api_key, access_token)` → `on_ticks`, `on_order_update` |

## High-Value Gotchas

- **Instrument keys are `EXCHANGE:TRADINGSYMBOL`** for quotes (`"NSE:RELIANCE"`, `"NSE:NIFTY 50"`, `"BSE:SENSEX"`),
  but `historical_data` and `KiteTicker` take the integer **`instrument_token`**.
- **Never construct F&O tradingsymbols by hand** (weekly and monthly formats differ: `NIFTY25O2125000CE` vs
  `NIFTY25OCT25000CE`). Resolve from `kite.instruments("NFO"/"BFO")` via `scripts/instruments.py`.
- Instruments dump is regenerated daily ~08:30 IST. Cache per day; tokens of expired contracts disappear.
- Index tokens are stable: NIFTY 50 `256265`, NIFTY BANK `260105`, NIFTY FIN SERVICE `257801`,
  NIFTY MID SELECT `288009`, INDIA VIX `264969`, SENSEX `265`. Indices are not tradable — trade their F&O.
- `quote()` takes up to 500 instruments per call; `ltp()` / `ohlc()` up to 1000. Quote APIs: **1 req/s**.
- `historical_data` returns `date` as tz-aware IST `datetime`. Max range per call depends on interval
  (minute ≈ 60 days, day ≈ 2000 days) — chunk long ranges.
- `positions()["net"]` is the cumulative position; `["day"]` is today's activity only. Use `net` for P&L.
- MIS positions are auto-squared off by Zerodha near close (equity ~15:20, F&O ~15:25 IST) with a charge. Warn the user.
- `exit_order` is for CO legs; for normal positions place an opposite order.
- Python SDK errors map from `error_type`: `TokenException` (re-login), `InputException`, `OrderException`,
  `PermissionException`, `NetworkException`, `DataException`, `GeneralException`. Margin / holding shortfalls
  arrive as `GeneralException`/`InputException` with the reason in the message — show it verbatim.
- An order may be modified at most 25 times; after that cancel and re-place.
- Zerodha caps 5,000 orders/day and 400/min per user; exchange rule caps 10/sec.

## Instrument Resolution

```python
from scripts.instruments import find_equity, find_option, find_future, list_expiries

eq  = find_equity(kite, "RELIANCE")                              # NSE by default
exp = list_expiries(kite, "NIFTY", exchange="NFO")[0]            # nearest expiry (date)
ce  = find_option(kite, "NIFTY", expiry=exp, strike=25000, option_type="CE")
fut = find_future(kite, "BANKNIFTY")                              # nearest month
print(ce["tradingsymbol"], ce["instrument_token"], ce["lot_size"], ce["tick_size"])
```

## Core Patterns

### 1. Health check before live work

```python
from scripts.kite_client import get_client, session_summary
kite = get_client()
print(session_summary(kite))   # user, broker, enabled exchanges/products, equity margin available
```

### 2. Validated, confirmed LIMIT order

```python
from scripts.validate_order import validate_order, format_preview
from scripts.instruments import find_equity

inst = find_equity(kite, "INFY")
ltp = kite.ltp("NSE:INFY")["NSE:INFY"]["last_price"]
order = dict(variety="regular", exchange="NSE", tradingsymbol="INFY",
             transaction_type="BUY", quantity=1, product="CNC",
             order_type="LIMIT", price=round(ltp * 0.995 / inst["tick_size"]) * inst["tick_size"],
             validity="DAY", tag="kiteskill")

report = validate_order(order, instrument=inst, ltp=ltp)
print(format_preview(order, report))
# -> show to user, wait for "yes", only then:
if report["ok"]:
    order_id = kite.place_order(**order)
    status = kite.order_history(order_id)[-1]["status"]
```

### 3. Market order (only when asked)

```python
kite.place_order(variety="regular", exchange="NFO", tradingsymbol=ce["tradingsymbol"],
                 transaction_type="BUY", quantity=ce["lot_size"], product="NRML",
                 order_type="MARKET", market_protection=-1, tag="kiteskill")
```

### 4. Margin + charges before a trade

```python
legs = [dict(exchange="NFO", tradingsymbol=ce["tradingsymbol"], transaction_type="SELL",
             variety="regular", product="NRML", order_type="LIMIT",
             quantity=ce["lot_size"], price=120.0, trigger_price=0)]
need = kite.basket_order_margins(legs, consider_positions=True)["final"]["total"]
free = kite.margins("equity")["net"]
```

### 5. Historical candles

```python
from datetime import date, timedelta
candles = kite.historical_data(256265, date.today() - timedelta(days=30), date.today(), "15minute")
# [{'date': datetime(..., tzinfo=+05:30), 'open':..., 'high':..., 'low':..., 'close':..., 'volume':...}, ...]
```

### 6. Live ticks

```python
from kiteconnect import KiteTicker
kws = KiteTicker(os.environ["KITE_API_KEY"], os.environ["KITE_ACCESS_TOKEN"])
kws.on_ticks = lambda ws, ticks: print(ticks)
kws.on_connect = lambda ws, resp: (ws.subscribe([256265]), ws.set_mode(ws.MODE_QUOTE, [256265]))
kws.connect(threaded=True)
```

## Rate Limits

| Endpoint group | Limit |
|---|---|
| Quote (`ltp`, `ohlc`, `quote`) | 1 req/s |
| Historical candles | 3 req/s |
| Order placement | 10 req/s, 400/min, 5,000/day |
| Everything else | 10 req/s |
| WebSocket | 3 connections per api_key, 3,000 instruments each |

HTTP 429 = slow down; back off and retry reads only. **Never auto-retry an order placement** — check the
order book first, the order may have gone through.

## Market Hours (IST)

| Segment | Session |
|---|---|
| NSE/BSE equity | pre-open 09:00–09:08, normal 09:15–15:30 |
| NFO/BFO | 09:15–15:30 |
| CDS/BCD | 09:00–17:00 |
| MCX | 09:00–23:30 (23:55 when US is on DST) |

`scripts/market_hours.py` checks weekday + session time. Kite has no holiday API — tell the user to check
the NSE holiday list when it matters.

## Reference Files

| Need | File |
|---|---|
| Login flow, token lifecycle, session hook | [references/auth.md](references/auth.md) |
| Every order parameter, varieties, statuses, autoslice, iceberg | [references/orders.md](references/orders.md) |
| GTT single/OCO and Alerts (simple / ATO) | [references/gtt-and-alerts.md](references/gtt-and-alerts.md) |
| Holdings, positions, conversion, auctions | [references/portfolio.md](references/portfolio.md) |
| Funds, order/basket margins, contract-note charges | [references/margins-and-charges.md](references/margins-and-charges.md) |
| LTP / OHLC / quote / historical candles | [references/market-data.md](references/market-data.md) |
| Instruments dump, symbol formats, index tokens | [references/instruments.md](references/instruments.md) |
| KiteTicker quick start (full streaming toolkit: **kite-websocket** skill) | [references/websocket.md](references/websocket.md) |
| Mutual funds and SIPs | [references/mutual-funds.md](references/mutual-funds.md) |
| Exceptions, HTTP codes, retry policy | [references/errors-and-limits.md](references/errors-and-limits.md) |
| SEBI 2026 retail-algo rules, static IP | [references/compliance.md](references/compliance.md) |
| Multi-step workflows (rebalance, bracket-like exits, EOD report) | [references/common-workflows.md](references/common-workflows.md) |

Related skills in this repo: **kite-options** (option chain, Greeks, strategies — Kite has no option-chain
endpoint), **kite-backtest** (historical data + Zerodha cost model) and **kite-websocket** (production-grade
streaming: thread-safe `TickStream`, live candles, tick recording, order-update monitor).
