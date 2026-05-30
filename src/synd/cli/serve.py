"""synd serve — start the MCP server (stdio transport)."""

from __future__ import annotations

import sys

import click
from rich.console import Console

from synd.cli.exit_codes import EXIT_ERROR

console = Console()


@click.command()
def serve() -> None:
    """Start the Synaptic Drift MCP server (stdio transport).

    The server opens .synd/index.db relative to the current working
    directory. Run from your project root, or set cwd in your MCP
    client config.
    """
    try:
        from synd.server import create_server
    except ImportError:
        console.print(
            "[red]error:[/red] The MCP server requires the serve extra.\n"
            "Install with:  pip install 'synaptic-drift[serve]'"
        )
        sys.exit(EXIT_ERROR)
    create_server().run()
