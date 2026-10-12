"""Calendar-aware data freshness: decide whether stored bars are safe to act on."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from quantforge.data.calendar import TradingCalendar
from quantforge.data.models import TAIPEI

# TWSE closes 13:30; daily STOCK_DAY data is reliably published by mid-afternoon.
DEFAULT_PUBLISH_CUTOFF = time(14, 30)


class Freshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class FreshnessReport:
    symbol: str
    status: Freshness
    latest_session: date | None
    expected_session: date
    checked_at: datetime

    @property
    def ok(self) -> bool:
        return self.status is Freshness.FRESH


def expected_latest_session(
    now: datetime, calendar: TradingCalendar, cutoff: time = DEFAULT_PUBLISH_CUTOFF
) -> date:
    """Most recent session whose official daily bar should be published at ``now``."""
    local = now.astimezone(TAIPEI)
    today = local.date()
    if calendar.is_trading_day(today) and local.time() >= cutoff:
        return today
    return calendar.previous_session(today)


def check_freshness(
    symbol: str,
    latest_session: date | None,
    now: datetime,
    calendar: TradingCalendar,
    cutoff: time = DEFAULT_PUBLISH_CUTOFF,
) -> FreshnessReport:
    expected = expected_latest_session(now, calendar, cutoff)
    if latest_session is None:
        status = Freshness.NO_DATA
    elif latest_session >= expected:
        status = Freshness.FRESH
    else:
        status = Freshness.STALE
    return FreshnessReport(symbol, status, latest_session, expected, now)
