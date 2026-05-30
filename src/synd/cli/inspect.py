"""synd inspect command."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from synd.cli.exit_codes import EXIT_VERIFICATION, exit_code_for
from synd.errors import SyndError
from synd.storage.db import Database

console = Console()

DEFAULT_DB = Path(".synd/index.db")


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def inspect_cmd(path: Path) -> None:
    """Inspect a .ctx pack or the local index database."""
    try:
        if path.suffix == ".ctx":
            _inspect_ctx(path)
        elif path.name == "index.db" or path.suffix == ".db":
            _inspect_db(path)
        else:
            # Try to detect: if it looks like a .synd/index.db path
            if ".synd" in str(path) and path.suffix == ".db":
                _inspect_db(path)
            else:
                # Default to ctx inspection for zip-like files
                _inspect_ctx(path)
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(exit_code_for(exc))


def _inspect_ctx(path: Path) -> None:
    """Inspect a .ctx file — print manifest fields."""
    import zipfile

    try:
        with zipfile.ZipFile(path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))

        console.print(f"[bold]Pack: {path.name}[/bold]")
        console.print("")

        table = Table(title="Manifest")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        for key, value in sorted(manifest.items()):
            display_val = str(value)
            if len(display_val) > 80:
                display_val = display_val[:77] + "..."
            table.add_row(key, display_val)

        console.print(table)

        # Show archive contents
        with zipfile.ZipFile(path, "r") as zf:
            files = zf.namelist()

        file_table = Table(title="Archive contents")
        file_table.add_column("File")
        for f in sorted(files):
            file_table.add_row(f)
        console.print(file_table)

    except (zipfile.BadZipFile, json.JSONDecodeError) as exc:
        console.print(f"[red]error: invalid .ctx archive: {exc}[/red]")
        sys.exit(EXIT_VERIFICATION)


def _inspect_db(path: Path) -> None:
    """Inspect the local index database — list imported packs."""
    try:
        db = Database(path)
        db.create_schema()
        packs = db.get_packages()

        if not packs:
            console.print("[yellow]No packs imported.[/yellow]")
            return

        console.print(f"[bold]Index: {path}[/bold]")
        console.print("")

        table = Table(title=f"Imported packs ({len(packs)})")
        table.add_column("Package", style="cyan")
        table.add_column("Version", style="magenta")
        table.add_column("Lifecycle", style="green")
        table.add_column("Status", style="blue")
        table.add_column("Indexed at", style="dim")

        for p in packs:
            table.add_row(
                p.name,
                p.version,
                p.lifecycle_state,
                p.doc_version_status,
                p.indexed_at,
            )

        console.print(table)
        db.close()
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(exit_code_for(exc))
