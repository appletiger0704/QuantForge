from pathlib import Path

from typer.testing import CliRunner

from quantforge import __version__
from quantforge.cli import app

runner = CliRunner()
SAMPLE = Path(__file__).resolve().parents[1] / "config" / "strategies" / "ma_rsi.yaml"


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"quantforge {__version__}"


def test_validate_config_is_deterministic() -> None:
    first = runner.invoke(app, ["validate-config", str(SAMPLE)])
    second = runner.invoke(app, ["validate-config", str(SAMPLE)])
    assert first.exit_code == 0
    assert first.output == second.output
    assert "watchlist: 2330,2317,0050" in first.output


def test_validate_config_invalid_exits_nonzero(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nversion: '1'\nwatchlist: []\nparams: {fast_ma: 1, slow_ma: 2}\n")
    result = runner.invoke(app, ["validate-config", str(bad)])
    assert result.exit_code == 1
