# #3 — Market data provider and normalized daily OHLCV

Issue: https://github.com/appletiger0704/QuantForge/issues/3 · Parent: #1 · Status: In review

## Plan
- Vendor-neutral `MarketDataProvider` protocol + typed `Bar`/`Security` models with sanity validation.
- `TwseProvider` + `TpexProvider` (public monthly JSON), `TaiwanExchangeProvider` (TWSE → TPEx fallback), `FinLabProvider` stub. Shioaji is out of scope (moved to #9).
- Throttled/retrying HTTP getter; all tests use recorded fixtures (no network, no keys).
- Trading calendar from TWSE holiday schedule + recorded ad-hoc closures; fails closed for unknown years.
- SQLite `BarStore`: idempotent upsert, provenance (`provider`, `retrieved_at`), revision detection, missing-session detection, securities table (for #10 search).
- Freshness check with publish cutoff (14:30 Taipei); split back-adjustment layer.
- CLI: `fetch`, `data-status`, `update-calendar`. Docs: `docs/DATA_SOURCES.md`.

## Acceptance criteria
- [x] Load sample equity and ETF daily candles over a configurable date range (`fetch 2330 0050 --start --end`; TPEx via 6488)
- [x] Normalized schema: symbol, session date, OHLC, volume, provider, retrieved_at, adjustment flag
- [x] Repeated import idempotent; detects missing days; rejects malformed or stale inputs
- [x] Provider contract tests using fixtures; no FinLab account needed

## Findings while building (real data)
- 0050 split 1→4 effective 2025-06-18 with a halt 06-11..06-17 → raw prices drop ~75%. Added split adjustment + `config/corporate_actions.yaml`.
- Ad-hoc closures absent from the official schedule: 2024 typhoon days and 2026-07-10 (no TWSE or TPEx trading). Recorded as `extra_closed`; caught by the test that compares fixture sessions to the calendar.
- TPEx volume is in lots; normalized to shares.

## Verification (2026-10-12, Python 3.12.13)
```
ruff check / format   -> pass
mypy --strict         -> Success: no issues found in 20 source files
pytest --cov          -> 61 passed, total coverage 97% (uncovered: network-only update-calendar)
```
Live run (real TWSE/TPEx, scratch DB):
```
$ quantforge fetch 2330 0050 6488 9999 --start 2026-09-01 --end 2026-10-12
2330: 27 bars from twse inserted=27 updated=0 unchanged=0 missing_sessions=0
0050: 27 bars from twse inserted=27 updated=0 unchanged=0 missing_sessions=0
6488: 27 bars from tpex inserted=27 updated=0 unchanged=0 missing_sessions=0
9999: ERROR twse: no data for 9999 ...; tpex: no data for 9999 ...      (exit 1)
$ quantforge fetch 2330 ...   -> inserted=0 updated=0 unchanged=27
$ quantforge data-status 2330 0050 6488 -> all FRESH latest=2026-10-12 (exit 0)
```

## Audit
- No credentials; no broker/order code.
- Raw data only in storage; adjustments are derived, never persisted.
- Data licensing/terms caveat documented in DATA_SOURCES.md.

## Interface notes for downstream (#4/#5/#10)
- Read bars via `BarStore.load_bars(symbol, start, end)` → apply `adjust_for_splits(bars, load_corporate_actions())` before indicators.
- Gate any signal on `check_freshness(...).ok`.
- `BarStore.securities()` provides symbol/name for UI search.
