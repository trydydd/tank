"""Synaptic Drift CLI — root command group.

Each subcommand handles its own errors and maps them to the exit-code taxonomy
in ``synd.cli.exit_codes``. Click maps usage errors (bad arguments, missing
input paths) to exit code 2 natively.
"""

from __future__ import annotations

import click

from synd.cli.add import add
from synd.cli.build import build
from synd.cli.inspect import inspect_cmd
from synd.cli.query import query
from synd.cli.remove import remove
from synd.cli.serve import serve
from synd.cli.sync import sync
from synd.cli.verify import verify_cmd

cli = click.Group()

cli.add_command(build)
cli.add_command(verify_cmd)
cli.add_command(add)
cli.add_command(sync)
cli.add_command(remove)
cli.add_command(query)
cli.add_command(inspect_cmd)
cli.add_command(serve)
