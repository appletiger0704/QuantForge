# QuantForge

Self-hosted Taiwan equity/ETF quantitative research that produces **daily BUY / SELL / HOLD signals after market close, for manual execution only**. QuantForge never submits broker orders.

> ⚠️ Informational research tool, not investment advice. You place every order yourself.

Status: MVP in progress — see Epic [#1](https://github.com/appletiger0704/QuantForge/issues/1) and [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you).

```bash
git clone https://github.com/appletiger0704/QuantForge.git
cd QuantForge
uv sync
cp .env.example .env   # optional; fill in locally, never commit
uv run quantforge --version
uv run quantforge validate-config config/strategies/ma_rsi.yaml

# Market data (public TWSE/TPEx, no key needed; requests are throttled ~3 s each)
uv run quantforge fetch 2330 2317 0050 --start 2026-04-01 --end 2026-10-12
uv run quantforge data-status 2330 2317 0050   # exit 2 if stale -> do not act
```

Data sources, adjustment policy and limitations: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Development

```bash
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy              # type check (strict)
```

CI (GitHub Actions) runs lint, format check, mypy, tests and a CLI smoke test on every PR.

## Layout

```
src/quantforge/       core package (config, CLI, data/; indicators/strategy to come)
config/strategies/    validated YAML strategy configs (data only, never executed)
config/calendar/      TWSE trading calendar per year (+ ad-hoc closures)
config/corporate_actions.yaml  recorded splits for price adjustment
tests/                pytest suite (offline; recorded exchange fixtures)
docs/tickets/         per-issue local tickets with verification evidence
```

## Configuration

Strategy YAML is validated strictly (unknown keys rejected, symbol format checked, `fast_ma < slow_ma`). Each config has a stable `config_hash` used for audit trails. Secrets live only in a local `.env` (see `.env.example` and [docs/USER_SETUP.md](docs/USER_SETUP.md)).
