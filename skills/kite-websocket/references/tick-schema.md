# Tick Schema

`on_ticks(ws, ticks)` receives a **list** of dicts. Fields depend on mode and on whether the instrument
is tradable (`tradable: False` for indices).

## Tradable instruments (equity, F&O, commodity, currency)

| Field | ltp | quote | full | Notes |
|---|:-:|:-:|:-:|---|
| `tradable` | ✓ | ✓ | ✓ | `True` |
| `mode` | ✓ | ✓ | ✓ | `"ltp"` / `"quote"` / `"full"` |
| `instrument_token` | ✓ | ✓ | ✓ | int |
| `last_price` | ✓ | ✓ | ✓ | float |
| `last_traded_quantity` | | ✓ | ✓ | |
| `average_traded_price` | | ✓ | ✓ | VWAP for the day |
| `volume_traded` | | ✓ | ✓ | **cumulative** day volume |
| `total_buy_quantity` / `total_sell_quantity` | | ✓ | ✓ | pending quantity across the book |
| `ohlc` | | ✓ | ✓ | `{open, high, low, close}` — `close` = previous close |
| `change` | | ✓ | ✓ | % vs previous close |
| `last_trade_time` | | | ✓ | naive datetime, **machine local tz** |
| `exchange_timestamp` | | | ✓ | naive datetime, **machine local tz** |
| `oi`, `oi_day_high`, `oi_day_low` | | | ✓ | F&O open interest |
| `depth` | | | ✓ | `{"buy": [5 × {price, quantity, orders}], "sell": [5 × ...]}` |

## Indices (`NIFTY 50` 256265, `NIFTY BANK` 260105, `SENSEX` 265, …)

| Field | ltp | quote | full |
|---|:-:|:-:|:-:|
| `tradable` (`False`), `mode`, `instrument_token`, `last_price` | ✓ | ✓ | ✓ |
| `ohlc`, `change` | | ✓ | ✓ |
| `exchange_timestamp` | | | ✓ |

No volume, OI or depth for indices.

## Timestamps

The SDK does `datetime.fromtimestamp(epoch)` → naive datetime in the **host's** timezone. Convert:

```python
from scripts.tick_utils import to_ist
to_ist(tick["exchange_timestamp"])        # aware datetime in +05:30, correct on any server
```

`tick_utils.tick_time(tick, received_at)` returns `exchange_timestamp` → `last_trade_time` → receive time,
whichever exists first, always in IST.

## Prices

Prices arrive as integers on the wire and are divided by the segment divisor: 100 for most segments,
10,000,000 for NSE currency (`cds`), 10,000 for BSE currency (`bcd`) and NCO. The SDK handles this.

## Binary packet layout (for reference)

```
message  = [num_packets: uint16] { [packet_len: uint16] [packet bytes] } × num_packets
packet sizes: ltp 8 · index quote 28 · index full 32 · quote 44 · full 184 bytes
token (bytes 0–4, big-endian uint32); segment = token & 0xff
  1 nse · 2 nfo · 3 cds · 4 bse · 5 bfo · 6 bcd · 7 mcx · 8 mcxsx · 9 indices · 12 nco
```

A 1-byte message is a heartbeat (ignored by the SDK).

## Text messages

| `type` | Payload | SDK callback |
|---|---|---|
| `order` | `data` = order postback (same fields as an order-book row: `order_id`, `status`, `status_message`, `filled_quantity`, `average_price`, `tradingsymbol`, `tag`, …) | `on_order_update(ws, data)` |
| `error` | `data` = message string | `on_error(ws, 0, message)` |
| `message` | broker notices | only via `on_message(ws, payload, is_binary)` |

Order updates arrive for **all** orders on the account (Kite web/app too), not only API orders —
filter by `tag` if you only care about the agent's orders.

## Example full-mode tick (equity)

```python
{
  "tradable": True, "mode": "full", "instrument_token": 408065,
  "last_price": 1512.35, "last_traded_quantity": 12, "average_traded_price": 1508.77,
  "volume_traded": 4561230, "total_buy_quantity": 512000, "total_sell_quantity": 498765,
  "ohlc": {"open": 1500.0, "high": 1519.9, "low": 1497.15, "close": 1503.4},
  "change": 0.595, "last_trade_time": datetime(...), "exchange_timestamp": datetime(...),
  "oi": 0, "oi_day_high": 0, "oi_day_low": 0,
  "depth": {"buy":  [{"price": 1512.3, "quantity": 45, "orders": 3}, ...],
            "sell": [{"price": 1512.35, "quantity": 120, "orders": 5}, ...]},
}
```
