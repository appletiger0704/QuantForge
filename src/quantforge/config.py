"""Strategy configuration loading and validation.

YAML is parsed with ``yaml.safe_load`` and validated by pydantic; it is data only,
never evaluated as code. Strategy-specific parameters are refined in issue #5.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Taiwan listed/OTC codes: 4-6 digits, optionally followed by an uppercase letter (e.g. 00631L).
Symbol = Annotated[str, StringConstraints(pattern=r"^\d{4,6}[A-Z]?$")]


class StrategyParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fast_ma: int = Field(gt=0)
    slow_ma: int = Field(gt=0)
    rsi_period: int = Field(default=14, gt=0)
    rsi_overbought: float = Field(default=70.0, gt=0, lt=100)
    rsi_oversold: float = Field(default=30.0, gt=0, lt=100)

    @model_validator(mode="after")
    def _check_ordering(self) -> StrategyParams:
        if self.fast_ma >= self.slow_ma:
            raise ValueError("fast_ma must be smaller than slow_ma")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("rsi_oversold must be smaller than rsi_overbought")
        return self


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    enabled: bool = True
    watchlist: tuple[Symbol, ...] = Field(min_length=1)
    params: StrategyParams

    @model_validator(mode="after")
    def _check_unique_watchlist(self) -> StrategyConfig:
        if len(set(self.watchlist)) != len(self.watchlist):
            raise ValueError("watchlist contains duplicate symbols")
        return self

    def config_hash(self) -> str:
        """Stable SHA-256 of the normalized config, used for audit/dedup keys."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_strategy_config(path: Path) -> StrategyConfig:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    return StrategyConfig.model_validate(raw)
