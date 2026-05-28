"""Entry point for python -m synd (MCP server, stdio transport)."""

import sys

try:
    from synd.server import create_server
except ImportError:
    from rich.console import Console

    Console().print(
        "[red]error:[/red] The MCP server requires the serve extra.\n"
        "Install with:  pip install 'synaptic-drift[serve]'"
    )
    sys.exit(1)

create_server().run()
