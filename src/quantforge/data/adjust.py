"""Split adjustment of raw bars.

Policy: the store keeps raw exchange prices. Analysis code back-adjusts prices *and*
volumes for recorded splits so indicators see a continuous series. Cash dividends are
not adjusted in the MVP (documented in docs/DATA_SOURCES.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from quantforge.data.models import Bar

DEFAULT_ACTIONS_PATH = Path(__file__).resolve().parents[3] / "config" / "corporate_actions.yaml"


class Split(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    ex_date: date  # first session trading on the new share basis
    ratio: float = Field(gt=0)  # new shares per old share, e.g. 4.0 for a 1-to-4 split
    note: str = ""


class CorporateActions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    splits: tuple[Split, ...] = ()


def load_corporate_actions(path: Path = DEFAULT_ACTIONS_PATH) -> CorporateActions:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return CorporateActions.model_validate(raw)


def adjust_for_splits(bars: Sequence[Bar], actions: CorporateActions) -> list[Bar]:
    """Return bars back-adjusted to the latest share basis; input order is preserved."""
    if not bars:
        return []
    symbol = bars[0].symbol
    splits = [s for s in actions.splits if s.symbol == symbol]
    out: list[Bar] = []
    for bar in bars:
        if bar.symbol != symbol:
            raise ValueError("adjust_for_splits expects bars for a single symbol")
        ratio = 1.0
        for s in splits:
            if bar.session_date < s.ex_date:
                ratio *= s.ratio
        out.append(
            replace(
                bar,
                open=round(bar.open / ratio, 6),
                high=round(bar.high / ratio, 6),
                low=round(bar.low / ratio, 6),
                close=round(bar.close / ratio, 6),
                volume=round(bar.volume * ratio),
                adjusted=bool(splits),
            )
        )
    return out
