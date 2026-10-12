"""TWSE (listed) and TPEx (OTC) public daily-bar providers.

Both exchanges publish one JSON document per symbol per calendar month. Prices are
unadjusted. TWSE reports volume in shares; TPEx in lots of 1,000 shares, which we
convert to shares. Network access goes through a throttled, retrying ``JsonGetter``
so tests can substitute recorded fixtures.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Protocol

import httpx

from quantforge.data.models import (
    TAIPEI,
    Bar,
    MalformedDataError,
    MarketDataError,
    ProviderError,
    Security,
    SymbolNotFoundError,
    validate_symbol,
)

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
TWSE_FIELDS = [
    "日期",
    "成交股數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌價差",
    "成交筆數",
    "註記",
]
TPEX_FIELDS = ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"]


class JsonGetter(Protocol):
    def __call__(self, url: str, params: Mapping[str, str]) -> Any: ...


class ThrottledJsonGetter:
    """HTTP GET returning decoded JSON, with a minimum interval and retry/backoff."""

    def __init__(
        self,
        min_interval: float = 3.0,
        retries: int = 3,
        timeout: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._min_interval = min_interval
        self._retries = retries
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: float | None = None
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "QuantForge/0.1 (research)"},
            transport=transport,
        )

    def __call__(self, url: str, params: Mapping[str, str]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            if self._last is not None:
                wait = self._min_interval - (self._monotonic() - self._last)
                if wait > 0:
                    self._sleep(wait)
            self._last = self._monotonic()
            try:
                resp = self._client.get(url, params=dict(params))
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                self._sleep(self._min_interval * (2**attempt))
        raise ProviderError(f"GET {url} failed after {self._retries} attempts: {last_exc}")


def _now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def _roc_date(text: str) -> date:
    cleaned = re.sub(r"[^0-9/]", "", text)
    try:
        y, m, d = (int(p) for p in cleaned.split("/"))
        return date(y + 1911, m, d)
    except ValueError as exc:
        raise MalformedDataError(f"unparseable ROC date {text!r}") from exc


def _number(text: str) -> float | None:
    cleaned = text.replace(",", "").strip()
    if cleaned in {"", "--", "---", "X"}:
        return None
    try:
        return float(cleaned)
    except ValueError as exc:
        raise MalformedDataError(f"unparseable number {text!r}") from exc


def _rows_to_bars(
    rows: Sequence[Sequence[str]],
    symbol: str,
    year: int,
    month: int,
    provider: str,
    retrieved_at: datetime,
    volume_multiplier: int,
) -> list[Bar]:
    bars: list[Bar] = []
    for row in rows:
        if len(row) < 7:
            raise MalformedDataError(f"{provider} {symbol}: short row {row!r}")
        session = _roc_date(row[0])
        if (session.year, session.month) != (year, month):
            raise MalformedDataError(f"{provider} {symbol}: {session} outside {year}-{month:02d}")
        volume, o, h, low, c = (_number(x) for x in (row[1], *row[3:7]))
        if o is None or h is None or low is None or c is None or volume is None:
            continue  # no trades that session; surfaced later as a missing session
        bars.append(
            Bar(
                symbol=symbol,
                session_date=session,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=round(volume * volume_multiplier),
                provider=provider,
                retrieved_at=retrieved_at,
            )
        )
    bars.sort(key=lambda b: b.session_date)
    if len({b.session_date for b in bars}) != len(bars):
        raise MalformedDataError(f"{provider} {symbol}: duplicate sessions in {year}-{month:02d}")
    return bars


def parse_twse_month(
    payload: Any, symbol: str, year: int, month: int, retrieved_at: datetime
) -> tuple[list[Bar], Security | None]:
    if not isinstance(payload, dict):
        raise MalformedDataError("twse: payload is not a JSON object")
    if payload.get("stat") != "OK":
        return [], None  # e.g. "很抱歉，沒有符合條件的資料!" — unknown symbol or no sessions
    if payload.get("fields") != TWSE_FIELDS:
        raise MalformedDataError(f"twse: unexpected fields {payload.get('fields')!r}")
    title = str(payload.get("title", "")).split()
    security = None
    if len(title) >= 3 and title[1] == symbol:
        security = Security(symbol=symbol, name=title[2], market="twse")
    bars = _rows_to_bars(payload.get("data", []), symbol, year, month, "twse", retrieved_at, 1)
    return bars, security


def parse_tpex_month(
    payload: Any, symbol: str, year: int, month: int, retrieved_at: datetime
) -> tuple[list[Bar], Security | None]:
    if not isinstance(payload, dict) or str(payload.get("stat", "")).lower() != "ok":
        raise MalformedDataError(f"tpex: unexpected payload stat {payload!r:.200}")
    tables = payload.get("tables") or []
    if not tables:
        raise MalformedDataError("tpex: missing tables")
    table = tables[0]
    if not table.get("data"):
        return [], None
    if table.get("fields") != TPEX_FIELDS:
        raise MalformedDataError(f"tpex: unexpected fields {table.get('fields')!r}")
    name = str(payload.get("name", "")).strip()
    security = Security(symbol=symbol, name=name, market="tpex") if name else None
    bars = _rows_to_bars(table["data"], symbol, year, month, "tpex", retrieved_at, 1000)
    return bars, security


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class _MonthlyExchangeProvider:
    name = ""

    def __init__(
        self,
        http: JsonGetter | None = None,
        clock: Callable[[], datetime] = _now_taipei,
    ) -> None:
        self._http: JsonGetter = http if http is not None else ThrottledJsonGetter()
        self._clock = clock
        self._securities: dict[str, Security] = {}

    def _get_month(self, symbol: str, year: int, month: int) -> Any:
        raise NotImplementedError

    def _parse(
        self, payload: Any, symbol: str, year: int, month: int, retrieved_at: datetime
    ) -> tuple[list[Bar], Security | None]:
        raise NotImplementedError

    def fetch_month(self, symbol: str, year: int, month: int) -> list[Bar]:
        validate_symbol(symbol)
        payload = self._get_month(symbol, year, month)
        bars, security = self._parse(payload, symbol, year, month, self._clock())
        if security is not None:
            self._securities[symbol] = security
        return bars

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        if start > end:
            raise ValueError("start must be on or before end")
        bars = [
            bar
            for y, m in _months(start, end)
            for bar in self.fetch_month(symbol, y, m)
            if start <= bar.session_date <= end
        ]
        if not bars:
            raise SymbolNotFoundError(f"{self.name}: no data for {symbol} in {start}..{end}")
        return bars

    def lookup(self, symbol: str) -> Security | None:
        return self._securities.get(symbol)


class TwseProvider(_MonthlyExchangeProvider):
    name = "twse"

    def _get_month(self, symbol: str, year: int, month: int) -> Any:
        params = {"date": f"{year}{month:02d}01", "stockNo": symbol, "response": "json"}
        return self._http(TWSE_URL, params)

    def _parse(
        self, payload: Any, symbol: str, year: int, month: int, retrieved_at: datetime
    ) -> tuple[list[Bar], Security | None]:
        return parse_twse_month(payload, symbol, year, month, retrieved_at)


class TpexProvider(_MonthlyExchangeProvider):
    name = "tpex"

    def _get_month(self, symbol: str, year: int, month: int) -> Any:
        params = {"code": symbol, "date": f"{year}/{month:02d}/01", "response": "json"}
        return self._http(TPEX_URL, params)

    def _parse(
        self, payload: Any, symbol: str, year: int, month: int, retrieved_at: datetime
    ) -> tuple[list[Bar], Security | None]:
        return parse_tpex_month(payload, symbol, year, month, retrieved_at)


class TaiwanExchangeProvider:
    """Tries TWSE then TPEx per symbol and remembers which market answered."""

    name = "tw-exchange"

    def __init__(self, providers: Sequence[_MonthlyExchangeProvider]) -> None:
        self._providers = list(providers)
        self._market: dict[str, _MonthlyExchangeProvider] = {}

    @classmethod
    def default(cls, http: JsonGetter | None = None) -> TaiwanExchangeProvider:
        shared = http if http is not None else ThrottledJsonGetter()
        return cls([TwseProvider(shared), TpexProvider(shared)])

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        if symbol in self._market:
            return self._market[symbol].fetch_daily(symbol, start, end)
        errors: list[str] = []
        for provider in self._providers:
            try:
                bars = provider.fetch_daily(symbol, start, end)
            except SymbolNotFoundError as exc:
                errors.append(str(exc))
                continue
            self._market[symbol] = provider
            return bars
        raise SymbolNotFoundError("; ".join(errors) or f"no provider for {symbol}")

    def lookup(self, symbol: str) -> Security | None:
        for provider in self._providers:
            sec = provider.lookup(symbol)
            if sec is not None:
                return sec
        return None


class FinLabProvider:
    """Placeholder for an optional FinLab adapter (requires a paid FinLab account)."""

    name = "finlab"

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        raise MarketDataError("FinLab adapter is not implemented; use TaiwanExchangeProvider")

    def lookup(self, symbol: str) -> Security | None:
        return None
