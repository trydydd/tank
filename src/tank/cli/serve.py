"""tank serve — start the MCP server (stdio transport)."""

from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


@click.command()
def serve() -> None:
    """Start the Tank MCP server (stdio transport).

    The server opens .tank/index.db relative to the current working
    directory. Run from your project root, or set cwd in your MCP
    client config.
    """
    try:
        from tank.server import create_server
    except ImportError:
        console.print(
            "[red]error:[/red] The MCP server requires the serve extra.\n"
            "Install with:  pip install 'tank-ctx[serve]'"
        )
        sys.exit(1)
    create_server().run()
