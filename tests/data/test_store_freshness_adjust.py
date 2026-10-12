from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from quantforge.data.adjust import CorporateActions, adjust_for_splits, load_corporate_actions
from quantforge.data.calendar import TradingCalendar
from quantforge.data.exchanges import TaiwanExchangeProvider, parse_twse_month
from quantforge.data.freshness import Freshness, check_freshness, expected_latest_session
from quantforge.data.models import TAIPEI, Security
from quantforge.data.store import BarStore
from tests.conftest import RETRIEVED_AT, load_market_fixture

START, END = date(2026, 4, 1), date(2026, 10, 12)


@pytest.fixture
def store(tmp_path: Path) -> BarStore:
    return BarStore(tmp_path / "qf.db")


def test_repeated_import_is_idempotent(
    store: BarStore, provider: TaiwanExchangeProvider, calendar: TradingCalendar
) -> None:
    bars = provider.fetch_daily("2330", START, END)
    first = store.upsert_bars(bars)
    assert (first.inserted, first.updated, first.unchanged) == (len(bars), 0, 0)
    later = [replace(b, retrieved_at=b.retrieved_at + timedelta(days=1)) for b in bars]
    second = store.upsert_bars(later)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, len(bars))
    assert store.load_bars("2330") == bars  # provenance untouched by no-op re-import
    assert store.missing_sessions("2330", START, END, calendar) == []
    assert store.latest_session("2330") == date(2026, 10, 12)


def test_revision_updates_and_missing_days_detected(
    store: BarStore, provider: TaiwanExchangeProvider, calendar: TradingCalendar
) -> None:
    bars = provider.fetch_daily("0050", START, END)
    dropped = bars[10]
    store.upsert_bars(b for b in bars if b is not dropped)
    assert store.missing_sessions("0050", START, END, calendar) == [dropped.session_date]
    revised = replace(bars[0], close=bars[0].close + 0.05, high=bars[0].high + 0.05)
    result = store.upsert_bars([revised])
    assert result.updated == 1
    assert store.load_bars("0050", bars[0].session_date, bars[0].session_date) == [revised]


def test_store_rejects_adjusted_and_ambiguous_providers(
    store: BarStore, provider: TaiwanExchangeProvider
) -> None:
    bars = provider.fetch_daily("2317", date(2026, 9, 1), date(2026, 9, 30))
    with pytest.raises(ValueError, match="raw"):
        store.upsert_bars([replace(bars[0], adjusted=True)])
    store.upsert_bars(bars)
    store.upsert_bars([replace(bars[0], provider="shioaji")])
    with pytest.raises(ValueError, match="multiple providers"):
        store.load_bars("2317")
    assert len(store.load_bars("2317", provider="twse")) == len(bars)


def test_securities_and_empty_store(store: BarStore) -> None:
    assert store.latest_session("2330") is None
    store.upsert_security(Security("2330", "台積電", "twse"))
    store.upsert_security(Security("2330", "台積電", "twse"))
    assert store.securities() == [Security("2330", "台積電", "twse")]
    memory = BarStore(":memory:")
    assert memory.securities() == []
    memory.close()


def _taipei(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TAIPEI)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (_taipei(2026, 10, 12, 16), date(2026, 10, 12)),  # trading day after cutoff
        (_taipei(2026, 10, 12, 13), date(2026, 10, 8)),  # before cutoff -> previous session
        (_taipei(2026, 10, 11, 16), date(2026, 10, 8)),  # Sunday after National Day
        (_taipei(2026, 2, 20, 16), date(2026, 2, 11)),  # Lunar New Year closure
    ],
)
def test_expected_latest_session(
    calendar: TradingCalendar, now: datetime, expected: date
) -> None:
    assert expected_latest_session(now, calendar) == expected


def test_freshness_states(calendar: TradingCalendar) -> None:
    now = _taipei(2026, 10, 13, 16)
    assert check_freshness("2330", date(2026, 10, 13), now, calendar).ok
    stale = check_freshness("2330", date(2026, 10, 12), now, calendar)
    assert stale.status is Freshness.STALE and not stale.ok
    assert stale.expected_session == date(2026, 10, 13)
    assert check_freshness("2330", None, now, calendar).status is Freshness.NO_DATA


def test_split_adjustment_makes_0050_continuous() -> None:
    raw, _ = parse_twse_month(
        load_market_fixture("twse_0050_202506.json"), "0050", 2025, 6, RETRIEVED_AT
    )
    actions = load_corporate_actions()
    adjusted = adjust_for_splits(raw, actions)
    by_day = {b.session_date: b for b in adjusted}
    raw_by_day = {b.session_date: b for b in raw}
    pre, post = by_day[date(2025, 6, 10)], by_day[date(2025, 6, 18)]
    assert pre.close == pytest.approx(188.65 / 4)
    assert pre.volume == raw_by_day[date(2025, 6, 10)].volume * 4
    assert post.close == raw_by_day[date(2025, 6, 18)].close  # on new basis already
    assert abs(post.close / pre.close - 1) < 0.05  # no artificial -75% "crash"
    assert all(b.adjusted for b in adjusted)
    # Halt days are absent from raw data (symbol-specific suspension, not a market holiday).
    assert date(2025, 6, 11) not in raw_by_day


def test_adjustment_noop_without_actions(provider: TaiwanExchangeProvider) -> None:
    bars = provider.fetch_daily("2330", date(2026, 9, 1), date(2026, 9, 30))
    assert adjust_for_splits(bars, CorporateActions()) == bars
    assert adjust_for_splits([], CorporateActions()) == []
    other = provider.fetch_daily("0050", date(2026, 9, 1), date(2026, 9, 30))
    with pytest.raises(ValueError, match="single symbol"):
        adjust_for_splits([*bars, *other], CorporateActions())
