"""Taiwan exchange trading calendar.

Built from TWSE's published holiday schedule plus explicitly recorded ad-hoc closures
(e.g. typhoon days). Querying a year with no calendar file fails closed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DEFAULT_CALENDAR_DIR = Path(__file__).resolve().parents[3] / "config" / "calendar"

# Rows in the TWSE schedule that mark trading days rather than closures.
_TRADING_MARKERS = ("開始交易", "最後交易")


class CalendarError(Exception):
    """Calendar data is missing for the requested date."""


def parse_twse_holiday_schedule(payload: dict[str, Any]) -> tuple[int, list[date]]:
    """Return (year, closed weekdays/holidays) from a TWSE ``holidaySchedule`` reply."""
    if str(payload.get("stat", "")).lower() != "ok" or payload.get("fields", [None])[0] != "日期":
        raise ValueError("unexpected TWSE holiday schedule payload")
    year = int(payload["queryYear"])
    closed = sorted(
        {
            date.fromisoformat(row[0])
            for row in payload["data"]
            if not any(marker in row[1] for marker in _TRADING_MARKERS)
        }
    )
    return year, closed


@dataclass(frozen=True)
class TradingCalendar:
    years: frozenset[int]
    closed: frozenset[date] = field(default_factory=frozenset)

    def _check(self, day: date) -> None:
        if day.year not in self.years:
            raise CalendarError(f"no trading calendar loaded for {day.year}")

    def is_trading_day(self, day: date) -> bool:
        self._check(day)
        return day.weekday() < 5 and day not in self.closed

    def sessions(self, start: date, end: date) -> Iterator[date]:
        day = start
        while day <= end:
            if self.is_trading_day(day):
                yield day
            day += timedelta(days=1)

    def previous_session(self, day: date) -> date:
        """Latest trading day strictly before ``day``."""
        cur = day - timedelta(days=1)
        while not self.is_trading_day(cur):
            cur -= timedelta(days=1)
        return cur

    def next_session(self, day: date) -> date:
        """Earliest trading day strictly after ``day``."""
        cur = day + timedelta(days=1)
        while not self.is_trading_day(cur):
            cur += timedelta(days=1)
        return cur

    @classmethod
    def from_files(cls, paths: Iterable[Path]) -> TradingCalendar:
        years: set[int] = set()
        closed: set[date] = set()
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            years.add(int(raw["year"]))
            closed.update(date.fromisoformat(d) for d in raw["closed"])
            closed.update(date.fromisoformat(d["date"]) for d in raw.get("extra_closed", []))
        return cls(years=frozenset(years), closed=frozenset(closed))

    @classmethod
    def load_default(cls, directory: Path = DEFAULT_CALENDAR_DIR) -> TradingCalendar:
        paths = sorted(directory.glob("tw_*.json"))
        if not paths:
            raise CalendarError(f"no calendar files in {directory}")
        return cls.from_files(paths)
