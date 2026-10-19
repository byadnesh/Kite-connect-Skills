# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-10-19

### Added
- `kite-connect` skill: auth/login helper with daily token cache, order validation and preview,
  instruments resolver with daily cache, market-hours checks, trade journal, Alerts REST helper,
  12 reference docs and 9 runnable examples.
- `kite-options` skill: option-chain builder, BSM/Black-76 IV and Greeks, PCR, max pain, expected move,
  delta strike picker, strategy payoff/breakevens, iron-condor example with basket margin and
  hedge-first execution.
- `kite-backtest` skill: chunked/cached history fetcher, Zerodha charges model (Oct 2026 rates),
  no-look-ahead backtester with MIS square-off, SMA crossover and opening-range-breakout examples.
- Offline test suite, CI (Linux/macOS/Windows, Python 3.9–3.13), Claude Code marketplace manifest,
  npx installer.
