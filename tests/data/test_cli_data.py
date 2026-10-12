from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from quantforge import cli
from quantforge.data.exchanges import TaiwanExchangeProvider

runner = CliRunner()


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch, provider: TaiwanExchangeProvider) -> None:
    monkeypatch.setattr(cli, "_make_provider", lambda: provider)


def _fetch(db: Path, *symbols: str) -> tuple[int, str]:
    args = ["fetch", *symbols, "--start", "2026-04-01", "--end", "2026-10-12", "--db", str(db)]
    result = runner.invoke(cli.app, args)
    return result.exit_code, result.output


def test_fetch_is_idempotent_and_reports_missing(tmp_path: Path) -> None:
    db = tmp_path / "qf.db"
    code, out = _fetch(db, "2330", "0050")
    assert code == 0, out
    assert "2330: 131 bars from twse inserted=131 updated=0 unchanged=0 missing_sessions=0" in out
    code, out = _fetch(db, "2330", "0050")
    assert code == 0
    assert "inserted=0 updated=0 unchanged=131 missing_sessions=0" in out


def test_fetch_fails_clearly_on_bad_symbols(tmp_path: Path) -> None:
    code, out = _fetch(tmp_path / "qf.db", "9999", "ABCD", "2330")
    assert code == 1
    assert "9999: ERROR" in out and "ABCD: ERROR" in out
    assert "2330: 131 bars" in out


def test_data_status_fresh_then_stale(tmp_path: Path) -> None:
    db = tmp_path / "qf.db"
    _fetch(db, "2330")
    fresh = runner.invoke(
        cli.app, ["data-status", "2330", "--as-of", "2026-10-12T16:00", "--db", str(db)]
    )
    assert fresh.exit_code == 0
    assert "2330: FRESH latest=2026-10-12 expected=2026-10-12" in fresh.output
    stale = runner.invoke(
        cli.app, ["data-status", "2330", "0050", "--as-of", "2026-10-13T16:00", "--db", str(db)]
    )
    assert stale.exit_code == 2
    assert "2330: STALE" in stale.output and "0050: NO_DATA latest=-" in stale.output


def test_db_url_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QF_DB_URL", f"sqlite:///{tmp_path / 'env.db'}")
    result = runner.invoke(cli.app, ["data-status", "2330", "--as-of", "2026-10-12"])
    assert result.exit_code == 2
    assert (tmp_path / "env.db").exists()
    monkeypatch.setenv("QF_DB_URL", "postgresql://x")
    assert runner.invoke(cli.app, ["data-status", "2330"]).exit_code != 0
