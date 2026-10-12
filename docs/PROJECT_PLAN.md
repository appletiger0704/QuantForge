# QuantForge — Project Completion Plan

Source of truth: GitHub Epic [#1](https://github.com/appletiger0704/QuantForge/issues/1) and issues #2–#10 (read 2026-10-12).
Repo state at planning time: only `README.md` (initial commit). Everything below is still to build.

Goal: a self-hosted Taiwan equity/ETF research tool that produces **daily BUY / SELL / HOLD signals after market close, for manual execution only** (no broker orders, ever, in MVP).

---

## 1. Dependency graph

```
#2 Foundation ──► #3 Market data ──► #4 Indicators ──► #5 Strategy/Signals ──┬─► #6 Backtest
                       │              (fixtures can start                    ├─► #7 Airflow pipeline (thin, optional)
                       │               right after #2)                       ├─► #8 Dashboard + Notion digest
                       │                                                     └─► #10 On-demand analysis UI
                       └─► #9 Shioaji adapter (optional, needs YOUR credentials, never blocks MVP)
```

Critical path: **#2 → #3 → #4 → #5 → (#6, #10) → #8 → #7**. Once the #5 signal schema is stable, #6/#7/#8/#10 can run in parallel.

## 2. Tech decisions (proposed defaults)

| Area | Decision | Why |
|---|---|---|
| Python | 3.12, managed by `uv` | System Python is 3.9; `uv` is already installed |
| Layout | `src/quantforge/`, `tests/`, `config/strategies/*.yaml`, `docs/tickets/` | Required by #2 / #1 workflow |
| Quality | `ruff` (lint+format), `mypy`, `pytest` | Lint/type/test CI per #2 |
| CI | GitHub Actions (`.github/workflows/ci.yml`) | #2 |
| Data | pandas + NumPy; **SQLite** for dev, PostgreSQL (Docker) optional for deploy | #3 allows SQLite first |
| Config | YAML validated with `pydantic` — no code evaluation | #5 |
| CLI | `typer` → `quantforge fetch / analyze / backtest / run-daily` | #7 needs CLI runnable without Airflow |
| UI | Streamlit multipage app, thin over core services | #8, #10 |
| Charts | plotly | candlestick + indicators |
| Orchestration | Airflow DAG calling the CLI, in Docker (optional) | #7 |
| Primary data source | TWSE (`STOCK_DAY`) + TPEx public daily endpoints, cached & rate-limited | free, no key; #3 |

## 3. Milestones

Each milestone follows the epic workflow: **local ticket `docs/tickets/{n}-{slug}.md` → plan → implement → test → verify → audit → PR (links issue) → merge → close**.

### M1 — #2 Foundation & CI
- `pyproject.toml` (uv), package skeleton, `quantforge --version` / `quantforge hello` deterministic CLI
- `.env.example`, `.gitignore` (incl. `.env`, `data/`, `*.db`)
- ruff + mypy + pytest; GitHub Actions running all three
- README quickstart
- **Done when:** fresh clone → `uv sync && uv run pytest` passes locally and in CI.

### M2 — #3 Market data provider & persistence
- `MarketDataProvider` protocol; `TwseProvider` (listed) + `TpexProvider` (OTC); `FinLabProvider` stub
- Normalized `Bar` schema: symbol, session_date, open/high/low/close, volume, provider, retrieved_at, adjusted flag
- Trading calendar (TWSE holiday list + "data exists" check), symbol/date validation, staleness detection
- SQLite repository with idempotent upsert + provenance; missing-day detection; reject malformed rows
- Recorded JSON fixtures for 2330, 2317, 0050 → contract tests run offline
- `docs/DATA_SOURCES.md`: availability, licensing, adjusted vs unadjusted policy
- **Done when:** `quantforge fetch 2330 0050 --start ... --end ...` loads, re-run changes nothing, tests offline green.

### M3 — #4 Indicator engine
- Pure functions: SMA, EMA, RSI(14, Wilder), MACD(12,26,9)
- Explicit warmup → NaN (never fake values); sorts/validates input; deterministic
- Reference tests vs hand-computed / published values with documented tolerance; edge cases: empty, flat, NaN, unsorted
- Can start on fixtures as soon as the `Bar` schema from M2 is agreed.

### M4 — #5 Strategy & signal engine (the key contract)
- `config/strategies/ma_rsi.yaml` (watchlist, MA20/MA60, RSI thresholds, enabled flag) validated by pydantic
- `Strategy` interface; `MaCrossRsiStrategy` implementation
- Separate **condition** (bullish/bearish/neutral) vs **position state** (flat/long) vs **action** (BUY/SELL/HOLD) vs **NO_SIGNAL** (warmup/stale/insufficient data)
- `Signal` schema: symbol, strategy, strategy_version, config_hash, data_as_of, generated_at, action, condition, position_assumption, reasons[], indicator_values, next_eligible_session, run_id
- Persist signals; dedup key = strategy+symbol+as_of+version
- **Done when:** fixtures produce deterministic BUY/SELL/HOLD; same input → same logical output; disabled strategy → nothing.

### M5 — #6 Backtesting & risk report  ‖  M6 — #10 On-demand analysis UI (parallel)
**#6:** event loop reusing the *same* strategy code; T-close signal → T+1 open fill; TW costs (commission 0.1425% w/ discount, sell tax 0.3% stock / 0.1% ETF, slippage) configurable; cash/position ledger that reconciles; CAGR, total return, max drawdown, win rate, trades, benchmark (0050); in-sample / out-of-sample split; persisted runs; caveats doc (survivorship, corporate actions).

**#10 Phase 1:** Streamlit page — symbol/name search + watchlist, as-of date, lookback, strategy select → *Analyze* calls core service; candlestick + SMA/EMA/RSI/MACD; signal card with reasons, as-of, version, next session, run ID; persisted backtest summary; explicit invalid-symbol / non-trading-day / stale / warmup states; "informational only, manual trading" banner. Phase 2 (visual polish) deferred.

### M7 — #8 Dashboard & optional Notion digest
- Pages: daily watchlist signals, historical run/signal explorer (version + as-of), backtest equity/drawdown/ledger vs benchmark — all from DB
- Opt-in `NotionDigest` adapter: upsert by date+strategy into a *digest* database only (never touch research master)

### M8 — #7 Airflow daily pipeline (thin)
- `quantforge run-daily` does: trading-day check → fetch → freshness validation (fail closed) → indicators → signals → snapshot/report
- Airflow DAG (Docker compose) scheduled ~ 15:00 Asia/Taipei on weekdays that just calls the CLI; skip non-trading days explicitly; idempotent reruns; artifacts with run_id, source timestamp, config hash, signal date, next session
- Failure notifications (log + optional webhook)

### M9 — #9 Shioaji adapter (optional, blocked on you)
- `ShioajiProvider` behind same protocol, read-only (`subscribe_trade=False`, no order APIs anywhere — enforced by a test that greps for order methods)
- Fixture contract tests run without keys; live test only when `SJ_API_KEY` / `SJ_SECRET_KEY` present; compare vs TWSE bars; TWSE fallback

### M10 — Release / Epic DoD
- End-to-end reproducible daily signal on sample universe (2330, 2317, 0050)
- Fail-closed on stale data verified, T+1 fills verified
- README: quick start, configuration, limitations; screenshots of UI
- Close #2–#10, tick the Epic checklist

## 4. What I (Claude) will do vs. what you must do

I can do all code, tests, docs, tickets, CI config, Docker files and commits/branches locally.
Things only you can do are listed in **[USER_SETUP.md](USER_SETUP.md)** — mainly: install GitHub CLI + auth (so I can open PRs and close issues), approve/merge PRs, and optionally Shioaji / Notion credentials.

## 5. Risks

| Risk | Mitigation |
|---|---|
| TWSE/TPEx rate limits / format changes | cache to DB, throttle (~3 s/request), recorded fixtures for tests |
| Adjusted prices not provided by TWSE | MVP uses unadjusted + documented policy; flag dividend/split days |
| Look-ahead bugs | dedicated tests: signal at T uses bars ≤ T; fills ≥ T+1 |
| Scope creep in UI | Phase 2 polish explicitly deferred |
| Shioaji access denied | optional; core MVP never depends on it |
