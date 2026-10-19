# Contributing to Kite Skills

Thanks for helping! This is an **unofficial** community project. Please keep that notice intact in every
skill and in the README.

## Ground rules

- **Safety first.** Never weaken the confirmation, validation or no-secrets rules. Any code path that
  places, modifies or cancels orders must go through a preview plus explicit confirmation.
- **No credentials or market data** in commits, tests, fixtures or screenshots. Use fake values.
- **Verify against the source.** When you change API details, check them against the
  [Kite Connect docs](https://kite.trade/docs/connect/v3/) and the
  [pykiteconnect source](https://github.com/zerodha/pykiteconnect) and link them in the PR.
- **Dates matter.** Regulations, charges, lot sizes and expiry calendars change. Write "as of
  <month year>" next to such facts.

## Skill authoring conventions

- `SKILL.md`: YAML frontmatter with `name` (equal to the directory name, kebab-case) and `description`
  (≤ 1024 chars, says *when* to trigger, ends with the UNOFFICIAL note). Keep the body short, around
  300 lines at most: setup, safety rules, constants, gotchas, core patterns, and a reference table.
- `references/*.md`: deep detail, one topic per file, linked from `SKILL.md`.
- `scripts/*.py`: importable as `from scripts.x import y` with the skill root on `sys.path`. Prefer the
  standard library, keep the `kiteconnect` import lazy where possible, and add type hints.
- `examples/*.py`: complete, runnable, and argparse-driven. State-changing examples must ask for a
  typed `yes`.
- `kite_common.py` is **byte-identical** in `kite-options` and `kite-backtest` so each skill installs on
  its own. Edit both, and CI checks they match.

## Development

```bash
python -m unittest discover -s tests -v
```

Add or extend tests in `tests/` for every script change. Tests must run offline. Use the fake Kite
classes in the existing tests as a pattern.

## Pull requests

1. Fork and create a branch.
2. Make the change, with tests and docs.
3. `python -m unittest discover -s tests` passes.
4. Describe what changed and how you verified it (doc links, or a live check on your own account with
   small size and the Personal plan where possible).
