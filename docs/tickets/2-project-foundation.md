# #2 — Project foundation and CI

Issue: https://github.com/appletiger0704/QuantForge/issues/2 · Parent: #1 · Status: In review

## Plan
- `uv`-managed Python 3.12 project, `src/quantforge` layout, `uv.lock` committed for reproducible installs.
- Tooling: ruff (lint + format), mypy `--strict`, pytest + coverage.
- Minimal deterministic CLI: `quantforge --version`, `quantforge validate-config <yaml>`.
- Strategy YAML loaded with `yaml.safe_load` + strict pydantic model (no code evaluation); stable `config_hash` for later audit/dedup keys (#5, #7).
- GitHub Actions CI: lint, format check, mypy, tests, CLI smoke test.
- `.env.example` + `.gitignore` (secrets, local data never committed).

Deferred on purpose: pandas/data deps (#3), full strategy params semantics (#5).

## Acceptance criteria
- [x] Fresh clone installs with documented commands (`uv sync`)
- [x] Unit tests and lint run locally and in CI
- [x] Sample CLI command exits cleanly with deterministic output
- [x] This ticket documents verification

## Verification (2026-10-12, macOS arm64, Python 3.12.13)
```
$ uv run ruff check .        -> All checks passed!
$ uv run ruff format --check -> 8 files already formatted
$ uv run mypy                -> Success: no issues found in 5 source files
$ uv run pytest --cov        -> 12 passed, coverage 100%
$ uv run quantforge validate-config config/strategies/ma_rsi.yaml
strategy: ma_cross_rsi
version: 0.1.0
enabled: true
watchlist: 2330,2317,0050
config_hash: 6dd239300f65fb9c7be57eb312ce6f1906293101c578ba0acf55827815452ca9
```
Determinism: `test_validate_config_is_deterministic` asserts identical output across runs; hash is fixed across machines (canonical JSON, sorted keys).
Fresh clone: verified with `git clone` into an empty dir + `uv sync --locked` + `uv run pytest`.
CI: see PR checks.

## Audit
- No secrets in repo; `.env` ignored, only `.env.example` with empty values.
- No broker / order code.
- YAML is data only (`safe_load`, `extra="forbid"`).
