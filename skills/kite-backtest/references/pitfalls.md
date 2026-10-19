# Backtesting Pitfalls & Going Live

## Biases

| Bias | How it sneaks in | Fix |
|---|---|---|
| Look-ahead | Using bar *i*'s close/high to trade at bar *i* | Engine fills at *i+1* open; compute indicators with data ≤ *i* only |
| Survivorship | Universe from today's instruments dump | Use point-in-time constituents or state the bias |
| Data snooping | Trying 500 parameter combos, reporting the best | Hold-out period, walk-forward, fewer free parameters |
| Corporate actions | Unadjusted split/bonus gaps look like crashes | Check events; adjust or exclude windows |
| Timezone/session | Mixing pre-open or post-close prints | Filter 09:15–15:30 IST for cash/F&O |
| Cost blindness | Ignoring STT/brokerage | Always use `scripts/charges.py` |
| Liquidity | Assuming fills in illiquid stocks/far OTM options | Volume filter; cap size at a % of bar volume |

## Validation recipe

1. Split: in-sample (first ~60–70 %) and out-of-sample (rest). Tune only on in-sample.
2. Walk-forward: roll a train window, test on the next window, stitch the OOS equity curves.
3. Parameter stability: neighbouring parameters should perform similarly (plateau, not spike).
4. Compare to buy-and-hold and to a random-entry baseline with the same holding period.
5. Report: CAGR, max drawdown, Sharpe/Sortino, trades, win rate, profit factor, charges % — and the
   number of variants tried.

## Indian-market specifics

- **Expiry effects:** index option prices and volumes behave differently on expiry days. Segment
  results by days-to-expiry.
- **Circuit limits:** stocks can lock at upper/lower circuit — no fills. Detect bars where high == low
  == close at a band and treat as untradeable.
- **Lot size changes:** exchanges revise F&O lot sizes periodically; backtests over long periods should
  use the lot size in force at the time.
- **Event days:** Union Budget, RBI policy, election results, index rebalancing, quarterly results.
- **Settlement:** delivery is T+1; sell proceeds are available for trading the same day (with limits)
  but withdrawable later. Not a modelling concern for most backtests.

## Paper → live checklist (with kite-connect)

1. Run the strategy in **dry-run** mode: compute signals live from KiteTicker / `historical_data`,
   log intended orders with `trade_journal.log_action("paper", ...)`, place nothing.
2. Compare paper fills vs actual market prices for 2–4 weeks (slippage reality check).
3. Go live with the smallest size (1 share / 1 lot), static IP registered, `tag` on every order.
4. Hard limits in code: max orders/day, max loss/day (stop trading when hit), max position size.
5. Kill switch: a single command that cancels open orders and flattens MIS positions
   (see kite-connect `references/common-workflows.md` §6).
6. Stay under 10 orders/second; higher-frequency strategies need exchange algo registration.
