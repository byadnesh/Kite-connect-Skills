# Security Policy

Kite Skills helps agents act on real brokerage accounts, so we take these issues seriously:

- credentials (API secret, access token) being printed, logged, cached insecurely or sent anywhere
  other than `api.kite.trade`;
- any path where an order, modification, cancellation, GTT or MF order can be placed **without** the
  preview and confirmation step;
- prompt-injection vectors (e.g. instrument names or alert text that could steer the agent);
- validation bypasses in `validate_order.py`.

## Reporting

Please **do not open a public issue** for vulnerabilities. Use GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab → "Report a vulnerability"). Include steps to reproduce and impact.
We aim to acknowledge within 7 days.

Issues in Zerodha's own platform or API should be reported to Zerodha directly, not here.

## For users

- Keep `KITE_API_SECRET` out of shell history and repos (use a `.env` file excluded by `.gitignore`, or a
  secrets manager).
- `~/.kite-skills/session.json` holds a live access token until ~06:00 IST. Run
  `kite.invalidate_access_token()` if you think it leaked.
- Review every order preview. Confirm only what you intend to trade.
