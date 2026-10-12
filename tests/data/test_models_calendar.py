from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from quantforge.data.calendar import CalendarError, TradingCalendar, parse_twse_holiday_schedule
from quantforge.data.models import Bar, MalformedDataError
from tests.conftest import FIXTURES, RETRIEVED_AT


def _bar(**kw: Any) -> Bar:
    base: dict[str, Any] = {
        "symbol": "2330",
        "session_date": date(2026, 9, 1),
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 100,
        "provider": "twse",
        "retrieved_at": RETRIEVED_AT,
    }
    return Bar(**(base | kw))


@pytest.mark.parametrize(
    ("kw", "exc"),
    [
        ({"open": 0.0}, MalformedDataError),
        ({"close": float("nan")}, MalformedDataError),
        ({"high": 10.0}, MalformedDataError),
        ({"low": 10.6}, MalformedDataError),
        ({"volume": -1}, MalformedDataError),
        ({"session_date": date(2026, 10, 13)}, MalformedDataError),
        ({"retrieved_at": datetime(2026, 10, 12, 16)}, ValueError),
        ({"symbol": "TSMC"}, ValueError),
    ],
)
def test_bar_validation(kw: dict[str, Any], exc: type[Exception]) -> None:
    with pytest.raises(exc):
        _bar(**kw)


def test_valid_bar() -> None:
    assert _bar().close == 10.5


def test_holiday_schedule_parsing_keeps_trading_markers() -> None:
    payload = json.loads((FIXTURES / "calendar" / "twse_holidays_2026.json").read_text())
    year, closed = parse_twse_holiday_schedule(payload)
    assert year == 2026
    assert date(2026, 1, 1) in closed
    assert date(2026, 2, 12) in closed  # settlement-only, no trading
    assert date(2026, 1, 2) not in closed  # "開始交易" marker
    assert date(2026, 2, 11) not in closed  # "最後交易" marker
    with pytest.raises(ValueError):
        parse_twse_holiday_schedule({"stat": "error"})


def test_calendar_queries(calendar: TradingCalendar) -> None:
    assert calendar.is_trading_day(date(2026, 10, 12))
    assert not calendar.is_trading_day(date(2026, 10, 9))  # National Day (observed)
    assert not calendar.is_trading_day(date(2026, 10, 11))  # Sunday
    assert not calendar.is_trading_day(date(2024, 7, 24))  # ad-hoc typhoon closure
    assert calendar.previous_session(date(2026, 2, 23)) == date(2026, 2, 11)
    assert calendar.next_session(date(2026, 2, 11)) == date(2026, 2, 23)
    assert list(calendar.sessions(date(2026, 10, 8), date(2026, 10, 13))) == [
        date(2026, 10, 8),
        date(2026, 10, 12),
        date(2026, 10, 13),
    ]


def test_calendar_fails_closed_outside_loaded_years(calendar: TradingCalendar) -> None:
    with pytest.raises(CalendarError):
        calendar.is_trading_day(date(2030, 1, 2))
    with pytest.raises(CalendarError):
        TradingCalendar.load_default(Path("/nonexistent"))
