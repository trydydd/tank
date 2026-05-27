"""Tank CLI — root command group."""

from __future__ import annotations

import sys

import click
from rich.console import Console

from synd.cli.add import add, pull
from synd.cli.build import build
from synd.cli.inspect import inspect_cmd
from synd.cli.query import query
from synd.cli.remove import remove
from synd.cli.serve import serve
from synd.cli.sync import sync
from synd.cli.verify import verify_cmd

console = Console()

cli = click.Group()


@cli.result_callback()
def _handle_errors(
    callback_result: object | None,
    **kwargs: object,
) -> None:
    """Catch SyndError and ClickException; print user-friendly messages."""
    from synd.errors import SyndError

    exc = kwargs.get("exc_info")
    if isinstance(exc, tuple) and len(exc) == 3:
        exc_type = exc[1]
    else:
        exc_type = None

    if isinstance(exc_type, SyndError):
        console.print(f"[red]error: {exc_type}[/red]")
        sys.exit(1)

    if isinstance(exc_type, click.ClickException):
        console.print(f"[red]error: {exc_type.message}[/red]")
        sys.exit(1)


cli.add_command(build)
cli.add_command(verify_cmd)
cli.add_command(add)
cli.add_command(sync)
cli.add_command(remove)
cli.add_command(query)
cli.add_command(inspect_cmd)
cli.add_command(serve)
cli.add_command(pull)  # deprecated alias, hidden=True set in add.py
