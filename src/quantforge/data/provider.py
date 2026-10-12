"""Vendor-neutral market data provider contract."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from quantforge.data.models import Bar, Security


@runtime_checkable
class MarketDataProvider(Protocol):
    name: str

    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        """Unadjusted daily bars for ``symbol`` with ``start <= session_date <= end``.

        Bars are sorted by date. Raises ``SymbolNotFoundError`` if the provider has no
        data for the symbol in the range, ``MalformedDataError`` on invalid payloads and
        ``ProviderError`` on transport failures.
        """
        ...

    def lookup(self, symbol: str) -> Security | None:
        """Name/market for a symbol seen by this provider, if known."""
        ...
