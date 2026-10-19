# Authentication & Session Lifecycle

## One-time app setup (user does this)

1. Sign in at <https://developers.kite.trade> → **Create new app**.
2. Pick **Personal** (free: orders/portfolio, no market data) or **Connect** (₹500/month: adds quotes,
   historical candles, WebSocket).
3. Set **Redirect URL**. For `scripts/login.py` use `http://127.0.0.1:5678/kite/callback`.
4. Set the **Postback URL** only if you run a public HTTPS server (optional; WebSocket order updates are easier).
5. Add your **static IP** under *IP Whitelist* (mandatory for order endpoints since 1 Apr 2026; one primary +
   one backup). See [compliance.md](compliance.md).
6. Copy `api_key` and `api_secret` into environment variables:

```bash
export KITE_API_KEY=xxxxxxxxxxxxxxxx
export KITE_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

```powershell
$env:KITE_API_KEY = "xxxxxxxxxxxxxxxx"
$env:KITE_API_SECRET = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Daily login flow (OAuth-like)

```
login_url()  ──►  user signs in on kite.zerodha.com (password + 2FA)
                    │
                    ▼
redirect_url?action=login&status=success&request_token=XXXX
                    │
generate_session(request_token, api_secret)  ──►  {access_token, refresh_token?, user_id, ...}
```

- `request_token` is single-use and valid for a few minutes.
- `access_token` is valid until **~06:00 IST the next day** (regulatory daily logout), or until the user
  logs out / invalidates it. Re-login every trading day.
- `refresh_token` is only issued to specially approved platforms; retail apps don't get one.

```python
from kiteconnect import KiteConnect
kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
print(kite.login_url())                       # https://kite.zerodha.com/connect/login?api_key=...&v=3
data = kite.generate_session(request_token, api_secret=os.environ["KITE_API_SECRET"])
kite.set_access_token(data["access_token"])
```

The `generate_session` checksum is `SHA-256(api_key + request_token + api_secret)`; the SDK computes it.

### Helper script

```bash
python scripts/login.py            # local callback on 127.0.0.1:5678
python scripts/login.py --paste    # any redirect URL; paste it back
python scripts/login.py --no-save  # don't cache, print token once
```

Cached token: `~/.kite-skills/session.json` (owner-only). `scripts/kite_client.get_client()` ignores it
automatically after 06:00 IST the next day.

## What the agent must NOT do

- Do not ask for, store, or type the user's Zerodha **password, PIN, or TOTP secret**.
- Do not automate the browser login (Selenium/TOTP scripts). Exchange rules require the account holder to
  log in personally; automated logins can get the API key blocked.
- Do not echo `api_secret` or `access_token` in chat or logs — use `mask()` from `kite_client.py`.

## REST auth header (when not using the SDK)

```
X-Kite-Version: 3
Authorization: token <api_key>:<access_token>
```

Base URL: `https://api.kite.trade`

## Session expiry handling

```python
from kiteconnect import exceptions as kex

kite.set_session_expiry_hook(lambda: print("Token expired — run scripts/login.py"))
try:
    kite.profile()
except kex.TokenException:
    ...  # stop; ask the user to log in again. Never loop-retry.
```

## Logout

```python
kite.invalidate_access_token()    # kills the current token immediately
```

Also logs the user out of Kite sessions opened via that token.
