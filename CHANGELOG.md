# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/).

## [1.1.0] — 2026-10-19

### Added
- `kite-websocket` skill: `TickStream` (thread-safe subscriptions via the Twisted reactor, sharding over
  3 connections × 3,000 tokens, bounded drop-oldest queue, latest snapshot, de-duplicated order
  updates, health/stale checks), `BarBuilder` (session-anchored live candles with cumulative-volume
  diffing), `TickRecorder` (daily JSONL), IST timestamp fixes, 4 reference docs and 5 examples.
- `resolve_instrument()` in the shared `kite_common.py`.
- README redesign: Kite mark logo (vector, transparent), animated SVG header, ticker and safety-flow
  diagrams; emojis removed.

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
