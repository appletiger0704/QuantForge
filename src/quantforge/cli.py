"""Command-line entry point: ``quantforge``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from quantforge import __version__
from quantforge.config import load_strategy_config

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
