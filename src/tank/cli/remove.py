"""tank remove command — remove a pack from the local index and lockfile."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from tank.cli._lockfile import LOCK_FILE, write_lockfile
from tank.errors import PackNotFoundError, TankError
from tank.storage.db import Database

console = Console()

TANK_DIR = Path(".tank")
INDEX_DB = TANK_DIR / "index.db"


@click.command()
@click.argument("pkg_spec")
def remove(pkg_spec: str) -> None:
    """Remove a pack from the local index and tank.lock.

    PKG_SPEC must be in the form ``package@version``, e.g.::

        tank remove fastmcp@3.3.0
    """
    if "@" not in pkg_spec:
        console.print(
            f"[red]error: invalid pack spec {pkg_spec!r} — "
            "expected 'package@version'[/red]"
        )
        sys.exit(1)

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

    except (TankError, OSError) as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)
