"""Command-line entry point: ``quantforge``."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from quantforge import __version__
from quantforge.config import load_strategy_config
from quantforge.data.calendar import (
    DEFAULT_CALENDAR_DIR,
    TradingCalendar,
    parse_twse_holiday_schedule,
)
from quantforge.data.exchanges import TaiwanExchangeProvider, ThrottledJsonGetter
from quantforge.data.freshness import check_freshness
from quantforge.data.models import TAIPEI, MarketDataError, validate_symbol
from quantforge.data.provider import MarketDataProvider
from quantforge.data.store import BarStore

app = typer.Typer(
    help="QuantForge: daily Taiwan equity signals for manual execution only.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"quantforge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """QuantForge CLI."""


@app.command("validate-config")
def validate_config(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Validate a strategy YAML file and print a deterministic summary."""
    try:
        cfg = load_strategy_config(path)
    except (ValidationError, ValueError) as exc:
        typer.echo(f"INVALID {path}\n{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"strategy: {cfg.name}")
    typer.echo(f"version: {cfg.version}")
    typer.echo(f"enabled: {str(cfg.enabled).lower()}")
    typer.echo(f"watchlist: {','.join(cfg.watchlist)}")
    typer.echo(f"config_hash: {cfg.config_hash()}")


def _default_db() -> Path:
    url = os.environ.get("QF_DB_URL", "sqlite:///data/quantforge.db")
    if not url.startswith("sqlite:///"):
        raise typer.BadParameter(f"only sqlite:/// URLs are supported, got {url!r}")
    return Path(url.removeprefix("sqlite:///"))


def _make_provider() -> MarketDataProvider:
    return TaiwanExchangeProvider.default()


DbOption = Annotated[Path | None, typer.Option("--db", help="SQLite path (default: QF_DB_URL).")]


@app.command("fetch")
def fetch(
    symbols: Annotated[list[str], typer.Argument(help="Symbols, e.g. 2330 0050.")],
    start: Annotated[datetime, typer.Option(formats=["%Y-%m-%d"])],
    end: Annotated[datetime, typer.Option(formats=["%Y-%m-%d"])],
    db: DbOption = None,
) -> None:
    """Fetch raw daily bars from TWSE/TPEx and upsert them (idempotent)."""
    calendar = TradingCalendar.load_default()
    provider = _make_provider()
    store = BarStore(db or _default_db())
    failed = False
    try:
        for symbol in symbols:
            try:
                validate_symbol(symbol)
                bars = provider.fetch_daily(symbol, start.date(), end.date())
            except (ValueError, MarketDataError) as exc:
                typer.echo(f"{symbol}: ERROR {exc}", err=True)
                failed = True
                continue
            closed = [b.session_date for b in bars if not calendar.is_trading_day(b.session_date)]
            if closed:
                typer.echo(f"{symbol}: ERROR bars on non-trading days {closed}", err=True)
                failed = True
                continue
            result = store.upsert_bars(bars)
            security = provider.lookup(symbol)
            if security is not None:
                store.upsert_security(security)
            missing = store.missing_sessions(symbol, start.date(), end.date(), calendar)
            typer.echo(
                f"{symbol}: {len(bars)} bars from {bars[0].provider} "
                f"inserted={result.inserted} updated={result.updated} "
                f"unchanged={result.unchanged} missing_sessions={len(missing)}"
            )
            for day in missing:
                typer.echo(f"  missing {day.isoformat()}")
    finally:
        store.close()
    if failed:
        raise typer.Exit(code=1)


@app.command("data-status")
def data_status(
    symbols: Annotated[list[str], typer.Argument()],
    as_of: Annotated[
        datetime | None,
        typer.Option(
            "--as-of", formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"], help="Taipei time; default now."
        ),
    ] = None,
    db: DbOption = None,
) -> None:
    """Report freshness per symbol; exit 2 if any symbol is stale or missing."""
    now = as_of.replace(tzinfo=TAIPEI) if as_of else datetime.now(TAIPEI)
    calendar = TradingCalendar.load_default()
    store = BarStore(db or _default_db())
    try:
        reports = [check_freshness(s, store.latest_session(s), now, calendar) for s in symbols]
    finally:
        store.close()
    for r in reports:
        latest = r.latest_session.isoformat() if r.latest_session else "-"
        typer.echo(
            f"{r.symbol}: {r.status} latest={latest} expected={r.expected_session.isoformat()}"
        )
    if not all(r.ok for r in reports):
        raise typer.Exit(code=2)


@app.command("update-calendar")
def update_calendar(
    year: Annotated[int, typer.Argument()],
    out_dir: Annotated[Path, typer.Option()] = DEFAULT_CALENDAR_DIR,
) -> None:
    """Download TWSE's holiday schedule for YEAR into config/calendar/tw_YEAR.json.

    Ad-hoc closures (typhoons) are not in the schedule; add them to ``extra_closed``.
    """
    payload = ThrottledJsonGetter()(
        "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule",
        {"date": f"{year}0101", "response": "json"},
    )
    parsed_year, closed = parse_twse_holiday_schedule(payload)
    path = out_dir / f"tw_{parsed_year}.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc = {
        "year": parsed_year,
        "source": "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule",
        "retrieved": datetime.now(TAIPEI).date().isoformat(),
        "closed": [d.isoformat() for d in closed],
        "extra_closed": existing.get("extra_closed", []),
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"wrote {path} ({len(closed)} closures)")
