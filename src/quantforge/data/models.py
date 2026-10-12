"""Normalized, vendor-neutral daily market data types."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
SYMBOL_RE = re.compile(r"^\d{4,6}[A-Z]?$")


class MarketDataError(Exception):
    """Base class for market data failures."""


class ProviderError(MarketDataError):
    """Transport/availability failure (network, throttling, non-JSON reply)."""


class MalformedDataError(MarketDataError):
    """Provider returned data that fails schema or sanity validation."""


class SymbolNotFoundError(MarketDataError):
    """No provider knows this symbol for the requested range."""


def validate_symbol(symbol: str) -> str:
    if not SYMBOL_RE.match(symbol):
        raise ValueError(f"invalid Taiwan security symbol: {symbol!r}")
    return symbol


@dataclass(frozen=True, slots=True)
class Bar:
    """One daily OHLCV bar.

    Prices are in TWD; ``volume`` is in shares (not lots). ``adjusted`` is False for
    raw exchange prices and True only for bars produced by :mod:`quantforge.data.adjust`.
    """

    symbol: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    provider: str
    retrieved_at: datetime
    adjusted: bool = False

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        prices = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise MalformedDataError(f"{self.symbol} {self.session_date}: non-positive price")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close
        ):
            raise MalformedDataError(f"{self.symbol} {self.session_date}: inconsistent OHLC")
        if self.volume < 0:
            raise MalformedDataError(f"{self.symbol} {self.session_date}: negative volume")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.session_date > self.retrieved_at.astimezone(TAIPEI).date():
            raise MalformedDataError(
                f"{self.symbol} {self.session_date}: session after retrieval time"
            )


@dataclass(frozen=True, slots=True)
class Security:
    symbol: str
    name: str
    market: str  # "twse" (listed) or "tpex" (OTC)
