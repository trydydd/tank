"""synd remove command — remove a pack from the local index and lockfile."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from synd.cli._lockfile import LOCK_FILE, write_lockfile
from synd.cli.exit_codes import EXIT_USAGE, exit_code_for
from synd.errors import PackNotFoundError, SyndError
from synd.storage.db import Database

console = Console()

SYND_DIR = Path(".synd")
INDEX_DB = SYND_DIR / "index.db"


@click.command()
@click.argument("pkg_spec")
def remove(pkg_spec: str) -> None:
    """Remove a pack from the local index and synd.lock.

    PKG_SPEC must be in the form ``package@version``, e.g.::

        synd remove fastmcp@3.3.0
    """
    if "@" not in pkg_spec:
        console.print(
            f"[red]error: invalid pack spec {pkg_spec!r} — "
            "expected 'package@version'[/red]"
        )
        sys.exit(EXIT_USAGE)

    name, version = pkg_spec.rsplit("@", 1)

    try:
        if not INDEX_DB.exists():
            raise PackNotFoundError(
                f"{name}@{version} is not in the index (no index.db found)"
            )

        db = Database(INDEX_DB)
        db.create_schema()

        if not db.pack_exists(name, version):
            db.close()
            raise PackNotFoundError(f"{name}@{version} is not in the index")

        db.delete_pack(name, version)
        write_lockfile(db, LOCK_FILE)
        db.close()

        console.print(f"[green]removed {name}@{version}[/green]")

    except (SyndError, OSError) as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(exit_code_for(exc))
