# Compliance: SEBI Retail Algo Framework (as applied by Zerodha, 2026)

> Not legal advice. Summary of public Zerodha/Kite Connect developer-forum notices; check the latest
> SEBI/NSE circulars and Zerodha announcements before relying on it.

SEBI's February 2025 circular on safer retail participation in algorithmic trading was implemented by
brokers with an enforcement date of **1 April 2026**. For Kite Connect that means:

| Rule | What changes for your code |
|---|---|
| **Static IP whitelisting** | Order endpoints (place / modify / cancel, GTT, alerts-with-orders) only accept requests from the IP(s) registered under *IP Whitelist* in the developer console. One primary + one backup. Data endpoints, WebSocket and portfolio reads work from any IP |
| **Order rate cap** | 10 orders/second per user. Exceeding → HTTP 429. Strategies above this must be registered with the exchange (via the broker) and carry an `algo_id` |
| **Market protection** | `MARKET` and `SL-M` orders must include `market_protection` (`-1` auto or `1–100` %). `0`/missing → rejected |
| **Autoslice cap** | `place_autoslice_order` creates at most 10 slices |
| **Daily login** | Access tokens die ~06:00 IST. The account holder logs in personally (2FA) every day |

## Practical guidance for the agent

- If an order fails with an IP-related message, explain the static-IP rule — don't retry from a
  different network or suggest proxies through third-party IPs the user doesn't control.
- Running on a laptop with a dynamic IP? Options for the user: ISP static IP, a VPS with a fixed public
  IP (run the bot there), or a cloud NAT gateway / elastic IP. Register that IP in the console.
- Personal-use scripts (the user's own account, below 10 orders/sec) don't need exchange algo
  registration. Selling/sharing a strategy to others is a different regime (research analyst / algo
  provider rules) — flag it, don't build it.
- `tag` every order so the user can audit what the agent did.
- Keep the trade journal (`scripts/trade_journal.py`) — useful for the user's own records and tax.

## Things this skill will not help with

- Bypassing static-IP checks, rate limits, or 2FA login.
- Sharing one api_key across multiple people's accounts.
- Front-running, spoofing, layering, wash trades or any manipulative order pattern.
