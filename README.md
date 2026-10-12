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
```

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
src/quantforge/       core package (config, CLI; data/indicators/strategy to come)
config/strategies/    validated YAML strategy configs (data only, never executed)
tests/                pytest suite
docs/tickets/         per-issue local tickets with verification evidence
```

## Configuration

Strategy YAML is validated strictly (unknown keys rejected, symbol format checked, `fast_ma < slow_ma`). Each config has a stable `config_hash` used for audit trails. Secrets live only in a local `.env` (see `.env.example` and [docs/USER_SETUP.md](docs/USER_SETUP.md)).
