"""Shared fixtures: recorded TWSE/TPEx replies replayed without network access."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from quantforge.data.calendar import TradingCalendar
from quantforge.data.exchanges import (
    TPEX_FIELDS,
    TaiwanExchangeProvider,
    TpexProvider,
    TwseProvider,
)
from quantforge.data.models import TAIPEI

FIXTURES = Path(__file__).parent / "fixtures"
MARKET = FIXTURES / "market"
# All market fixtures were recorded on 2026-10-12 around 15:20 Taipei time.
RETRIEVED_AT = datetime(2026, 10, 12, 16, 0, tzinfo=TAIPEI)


class FixtureHttp:
    """Maps exchange URL + params to a recorded JSON file; unknown -> 'no data' reply."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: Mapping[str, str]) -> Any:
        self.calls.append((url, dict(params)))
        if "twse" in url:
            path = MARKET / f"twse_{params['stockNo']}_{params['date'][:6]}.json"
            if not path.exists():
                return {"stat": "很抱歉，沒有符合條件的資料!", "total": 0}  # noqa: RUF001
        else:
            path = MARKET / f"tpex_{params['code']}_{params['date'].replace('/', '')[:6]}.json"
            if not path.exists():
                return {
                    "stat": "ok",
                    "name": "",
                    "tables": [{"data": [], "fields": TPEX_FIELDS}],
                }
        return json.loads(path.read_text(encoding="utf-8"))


def load_market_fixture(name: str) -> Any:
    return json.loads((MARKET / name).read_text(encoding="utf-8"))


@pytest.fixture
def http() -> FixtureHttp:
    return FixtureHttp()


@pytest.fixture
def provider(http: FixtureHttp) -> TaiwanExchangeProvider:
    clock = lambda: RETRIEVED_AT  # noqa: E731
    return TaiwanExchangeProvider([TwseProvider(http, clock), TpexProvider(http, clock)])


@pytest.fixture(scope="session")
def calendar() -> TradingCalendar:
    return TradingCalendar.load_default()
