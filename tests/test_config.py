from pathlib import Path

import pytest
from pydantic import ValidationError

from quantforge.config import StrategyConfig, load_strategy_config

SAMPLE = Path(__file__).resolve().parents[1] / "config" / "strategies" / "ma_rsi.yaml"


def _base() -> dict[str, object]:
    return {
        "name": "t",
        "version": "1",
        "watchlist": ["2330", "0050"],
        "params": {"fast_ma": 20, "slow_ma": 60},
    }


def test_sample_config_loads() -> None:
    cfg = load_strategy_config(SAMPLE)
    assert cfg.name == "ma_cross_rsi"
    assert cfg.watchlist == ("2330", "2317", "0050")
    assert cfg.params.rsi_period == 14


def test_config_hash_is_stable_and_sensitive() -> None:
    a = StrategyConfig.model_validate(_base())
    b = StrategyConfig.model_validate(_base())
    assert a.config_hash() == b.config_hash()
    changed = _base() | {"version": "2"}
    assert StrategyConfig.model_validate(changed).config_hash() != a.config_hash()


@pytest.mark.parametrize(
    "patch",
    [
        {"watchlist": ["23A0"]},
        {"watchlist": []},
        {"watchlist": ["2330", "2330"]},
        {"params": {"fast_ma": 60, "slow_ma": 20}},
        {"params": {"fast_ma": 20, "slow_ma": 60, "rsi_oversold": 80, "rsi_overbought": 70}},
        {"unexpected": True},
    ],
)
def test_invalid_configs_rejected(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(_base() | patch)


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_strategy_config(p)
