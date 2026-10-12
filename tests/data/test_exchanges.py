from __future__ import annotations

import copy
from datetime import date
from typing import Any

import httpx
import pytest

from quantforge.data.calendar import TradingCalendar
from quantforge.data.exchanges import (
    FinLabProvider,
    TaiwanExchangeProvider,
    ThrottledJsonGetter,
    parse_tpex_month,
    parse_twse_month,
)
from quantforge.data.models import (
    MalformedDataError,
    MarketDataError,
    ProviderError,
    SymbolNotFoundError,
)
from quantforge.data.provider import MarketDataProvider
from tests.conftest import RETRIEVED_AT, FixtureHttp, load_market_fixture


def test_parse_twse_month_normalizes_rows() -> None:
    bars, security = parse_twse_month(
        load_market_fixture("twse_2330_202609.json"), "2330", 2026, 9, RETRIEVED_AT
    )
    assert len(bars) == 20
    first = bars[0]
    assert first.session_date == date(2026, 9, 1)
    assert (first.open, first.high, first.low, first.close) == (2395.0, 2440.0, 2390.0, 2440.0)
    assert first.volume == 31_855_287  # shares
    assert first.provider == "twse" and first.adjusted is False
    assert first.retrieved_at == RETRIEVED_AT
    assert security is not None and security.name == "台積電" and security.market == "twse"
    assert [b.session_date for b in bars] == sorted(b.session_date for b in bars)


def test_parse_tpex_month_converts_lots_to_shares() -> None:
    bars, security = parse_tpex_month(
        load_market_fixture("tpex_6488_202609.json"), "6488", 2026, 9, RETRIEVED_AT
    )
    assert bars[0].volume == 12_770_000  # 12,770 lots x 1,000
    assert bars[0].close == 994.0 and bars[0].provider == "tpex"
    assert security is not None and security.name == "環球晶" and security.market == "tpex"


def test_no_data_replies_yield_empty() -> None:
    assert parse_twse_month(
        load_market_fixture("twse_9999_202609.json"), "9999", 2026, 9, RETRIEVED_AT
    ) == ([], None)
    assert parse_tpex_month(
        load_market_fixture("tpex_9999_202609.json"), "9999", 2026, 9, RETRIEVED_AT
    ) == ([], None)


def _twse() -> dict[str, Any]:
    return copy.deepcopy(load_market_fixture("twse_2330_202609.json"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.__setitem__("fields", ["date", "volume"]),
        lambda p: p["data"][0].__setitem__(0, "115/08/31"),  # row outside requested month
        lambda p: p["data"][0].__setitem__(0, "not-a-date"),
        lambda p: p["data"][0].__setitem__(4, "abc"),
        lambda p: p["data"][0].__setitem__(4, "1.00"),  # high below open/close
        lambda p: p["data"].append(list(p["data"][0])),  # duplicate session
        lambda p: p["data"].append(["115/09/30", "1"]),  # short row
    ],
)
def test_malformed_twse_payloads_rejected(mutate: Any) -> None:
    payload = _twse()
    mutate(payload)
    with pytest.raises(MalformedDataError):
        parse_twse_month(payload, "2330", 2026, 9, RETRIEVED_AT)


def test_non_object_and_bad_tpex_payloads_rejected() -> None:
    with pytest.raises(MalformedDataError):
        parse_twse_month(["x"], "2330", 2026, 9, RETRIEVED_AT)
    with pytest.raises(MalformedDataError):
        parse_tpex_month({"stat": "error"}, "6488", 2026, 9, RETRIEVED_AT)
    with pytest.raises(MalformedDataError):
        parse_tpex_month({"stat": "ok", "tables": []}, "6488", 2026, 9, RETRIEVED_AT)
    payload = load_market_fixture("tpex_6488_202609.json")
    payload["tables"][0]["fields"] = ["x"]
    with pytest.raises(MalformedDataError):
        parse_tpex_month(payload, "6488", 2026, 9, RETRIEVED_AT)


def test_no_trade_rows_are_skipped() -> None:
    payload = _twse()
    payload["data"][0][3:7] = ["--", "--", "--", "--"]
    bars, _ = parse_twse_month(payload, "2330", 2026, 9, RETRIEVED_AT)
    assert len(bars) == 19 and bars[0].session_date == date(2026, 9, 2)


def test_session_after_retrieval_rejected() -> None:
    early = RETRIEVED_AT.replace(month=9, day=15)
    with pytest.raises(MalformedDataError, match="after retrieval"):
        parse_twse_month(_twse(), "2330", 2026, 9, early)


def test_fetch_daily_spans_months_and_filters_range(
    provider: TaiwanExchangeProvider, http: FixtureHttp
) -> None:
    bars = provider.fetch_daily("2330", date(2026, 8, 15), date(2026, 9, 10))
    assert bars[0].session_date == date(2026, 8, 17)
    assert bars[-1].session_date == date(2026, 9, 10)
    assert len({b.session_date for b in bars}) == len(bars)
    assert len(http.calls) == 2  # one request per month


def test_composite_falls_back_to_tpex_and_memoizes(
    provider: TaiwanExchangeProvider, http: FixtureHttp
) -> None:
    bars = provider.fetch_daily("6488", date(2026, 9, 1), date(2026, 9, 30))
    assert bars[0].provider == "tpex"
    assert provider.lookup("6488") is not None
    calls = len(http.calls)
    provider.fetch_daily("6488", date(2026, 9, 1), date(2026, 9, 30))
    assert len(http.calls) == calls + 1  # goes straight to TPEx


def test_unknown_symbol_fails_clearly(provider: TaiwanExchangeProvider) -> None:
    with pytest.raises(SymbolNotFoundError, match="9999"):
        provider.fetch_daily("9999", date(2026, 9, 1), date(2026, 9, 30))
    assert provider.lookup("9999") is None
    with pytest.raises(ValueError):
        provider.fetch_daily("23X0", date(2026, 9, 1), date(2026, 9, 30))
    with pytest.raises(ValueError):
        provider.fetch_daily("2330", date(2026, 9, 2), date(2026, 9, 1))


@pytest.mark.parametrize("symbol", ["2330", "2317", "0050"])
def test_fixture_sessions_match_trading_calendar(
    provider: TaiwanExchangeProvider, calendar: TradingCalendar, symbol: str
) -> None:
    start, end = date(2026, 4, 1), date(2026, 10, 12)
    bars = provider.fetch_daily(symbol, start, end)
    assert [b.session_date for b in bars] == list(calendar.sessions(start, end))


def test_providers_satisfy_contract(provider: TaiwanExchangeProvider) -> None:
    assert isinstance(provider, MarketDataProvider)
    finlab = FinLabProvider()
    assert isinstance(finlab, MarketDataProvider)
    assert finlab.lookup("2330") is None
    with pytest.raises(MarketDataError):
        finlab.fetch_daily("2330", date(2026, 1, 1), date(2026, 1, 31))


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def test_throttled_getter_spaces_requests_and_retries() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"stat": "OK"})

    clock = _Clock()
    getter = ThrottledJsonGetter(
        min_interval=3.0,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        transport=httpx.MockTransport(handler),
    )
    assert getter("https://example.test/a", {"q": "1"}) == {"stat": "OK"}
    assert getter("https://example.test/b", {}) == {"stat": "OK"}
    assert attempts["n"] == 3
    assert all(s > 0 for s in clock.sleeps)


def test_throttled_getter_gives_up_with_provider_error() -> None:
    clock = _Clock()
    getter = ThrottledJsonGetter(
        retries=2,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>blocked")),
    )
    with pytest.raises(ProviderError, match="2 attempts"):
        getter("https://example.test/a", {})
