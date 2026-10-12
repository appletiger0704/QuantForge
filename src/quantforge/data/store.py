"""SQLite persistence for daily bars with idempotent upsert and provenance."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from quantforge.data.calendar import TradingCalendar
from quantforge.data.models import Bar, Security

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_bars (
    symbol        TEXT    NOT NULL,
    session_date  TEXT    NOT NULL,
    open          REAL    NOT NULL,
    high          REAL    NOT NULL,
    low           REAL    NOT NULL,
    close         REAL    NOT NULL,
    volume        INTEGER NOT NULL,
    provider      TEXT    NOT NULL,
    retrieved_at  TEXT    NOT NULL,
    adjusted      INTEGER NOT NULL,
    PRIMARY KEY (symbol, session_date, provider)
);
CREATE TABLE IF NOT EXISTS securities (
    symbol  TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    market  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


class BarStore:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def upsert_bars(self, bars: Iterable[Bar]) -> UpsertResult:
        """Insert new bars; update only when OHLCV differs (a provider revision).

        Re-importing identical data leaves rows (including ``retrieved_at``) untouched.
        """
        inserted = updated = unchanged = 0
        with self._conn:
            for b in bars:
                if b.adjusted:
                    raise ValueError("only raw (unadjusted) bars are persisted")
                key = (b.symbol, b.session_date.isoformat(), b.provider)
                row = self._conn.execute(
                    "SELECT open, high, low, close, volume FROM daily_bars "
                    "WHERE symbol=? AND session_date=? AND provider=?",
                    key,
                ).fetchone()
                values = (b.open, b.high, b.low, b.close, b.volume)
                if row is None:
                    self._conn.execute(
                        "INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (*key[:2], *values, b.provider, b.retrieved_at.isoformat(), 0),
                    )
                    inserted += 1
                elif tuple(row) != values:
                    self._conn.execute(
                        "UPDATE daily_bars SET open=?, high=?, low=?, close=?, volume=?, "
                        "retrieved_at=? WHERE symbol=? AND session_date=? AND provider=?",
                        (*values, b.retrieved_at.isoformat(), *key),
                    )
                    updated += 1
                else:
                    unchanged += 1
        return UpsertResult(inserted, updated, unchanged)

    def upsert_security(self, security: Security) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO securities VALUES (?,?,?) ON CONFLICT(symbol) "
                "DO UPDATE SET name=excluded.name, market=excluded.market",
                (security.symbol, security.name, security.market),
            )

    def securities(self) -> list[Security]:
        rows = self._conn.execute("SELECT symbol, name, market FROM securities ORDER BY symbol")
        return [Security(*r) for r in rows]

    def load_bars(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        provider: str | None = None,
    ) -> list[Bar]:
        sql = "SELECT * FROM daily_bars WHERE symbol=?"
        args: list[str] = [symbol]
        if start is not None:
            sql += " AND session_date>=?"
            args.append(start.isoformat())
        if end is not None:
            sql += " AND session_date<=?"
            args.append(end.isoformat())
        if provider is not None:
            sql += " AND provider=?"
            args.append(provider)
        sql += " ORDER BY session_date, provider"
        bars = [
            Bar(
                symbol=r[0],
                session_date=date.fromisoformat(r[1]),
                open=r[2],
                high=r[3],
                low=r[4],
                close=r[5],
                volume=r[6],
                provider=r[7],
                retrieved_at=datetime.fromisoformat(r[8]),
                adjusted=bool(r[9]),
            )
            for r in self._conn.execute(sql, args)
        ]
        if provider is None and len({b.session_date for b in bars}) != len(bars):
            raise ValueError(f"{symbol}: multiple providers stored; pass provider explicitly")
        return bars

    def latest_session(self, symbol: str) -> date | None:
        row = self._conn.execute(
            "SELECT MAX(session_date) FROM daily_bars WHERE symbol=?", (symbol,)
        ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def missing_sessions(
        self, symbol: str, start: date, end: date, calendar: TradingCalendar
    ) -> list[date]:
        have = {b.session_date for b in self.load_bars(symbol, start, end)}
        return [d for d in calendar.sessions(start, end) if d not in have]
