# Market data sources, policies and limitations

## Sources

| Provider | Market | Endpoint (one JSON per symbol per month) | Volume unit in reply | Key needed |
|---|---|---|---|---|
| `twse` | TWSE listed stocks/ETFs | `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=YYYYMM01&stockNo=XXXX&response=json` | shares | no |
| `tpex` | TPEx (OTC) stocks/ETFs | `https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code=XXXX&date=YYYY/MM/01&response=json` | lots (×1,000 shares) | no |
| `finlab` | — | stub only, optional / replaceable | — | paid |
| `shioaji` | — | planned, optional (#9) | — | broker API key |

`TaiwanExchangeProvider` tries TWSE first, then TPEx, and remembers which market a symbol belongs to. Requests are throttled (≥ 3 s apart) and retried with exponential backoff; the exchanges block clients that request too fast.

Trading calendar: `config/calendar/tw_YYYY.json`, generated from TWSE's
`/rwd/zh/holidaySchedule/holidaySchedule` (`quantforge update-calendar YYYY`).

## Normalized schema (`daily_bars`)

`symbol, session_date, open, high, low, close, volume (shares), provider, retrieved_at (tz-aware ISO), adjusted (always 0 in storage)` — primary key `(symbol, session_date, provider)`.

Validation on ingestion rejects: unexpected field headers (format change), unparsable numbers/dates, rows outside the requested month, duplicate sessions, non-positive or inconsistent OHLC, negative volume, sessions dated after retrieval, and bars on non-trading days. Rows with no trades (`--`) are skipped and surface as missing sessions.

## Policies

- **Idempotency:** re-importing identical data changes nothing (not even `retrieved_at`). Differing OHLCV for an existing key is treated as a provider revision and updated.
- **Freshness / fail closed:** the expected latest session is today if it is a trading day and Taipei time ≥ 14:30, else the previous trading day. `quantforge data-status` exits 2 when any symbol is `STALE` or `NO_DATA`; downstream signal generation must refuse to publish in that case. Years without a calendar file raise `CalendarError` rather than guessing.
- **Adjusted vs unadjusted:** storage is always raw exchange prices. Analysis back-adjusts prices and volumes for splits recorded in `config/corporate_actions.yaml` (`quantforge.data.adjust`). **Cash dividends are not adjusted in the MVP**, so ex-dividend days show a price drop that indicators will see; total-return comparisons are understated accordingly.

## Known data events (verified against exchange data, 2026-10-12)

| Date(s) | Event | Handling |
|---|---|---|
| 2024-07-24, 07-25, 10-02, 10-03, 10-31 | Ad-hoc typhoon market closures (not in the published schedule) | `extra_closed` in `tw_2024.json` |
| 2026-07-10 | Ad-hoc market-wide closure (no TWSE or TPEx sessions) | `extra_closed` in `tw_2026.json` |
| 2025-06-11 … 06-17 | 0050 trading halted for 1→4 split; resumes 06-18 (~188.65 → ~47.5) | split in `corporate_actions.yaml`; the halt days are reported by `missing_sessions` for 0050 only |

New ad-hoc closures or splits must be added by hand; `quantforge fetch` will report them as missing sessions or the price series will show a discontinuity.

## Limitations

- **Survivorship:** only symbols you request are fetched; delisted securities are not discovered automatically. Universe selection for backtests must account for this.
- **Coverage:** daily bars only; no intraday, no block trades (TPEx explicitly excludes 鉅額交易).
- **Foreign-currency ETFs on TPEx** (6th character K/C) use different lot sizes; not supported.
- **Licensing / terms of use:** data comes from the exchanges' public websites. You are responsible for complying with TWSE's and TPEx's terms of use. QuantForge stores data locally for personal research only — do not redistribute raw data; commercial use or redistribution may require a data license from the exchange.
