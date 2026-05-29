"""tank query command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from synd.errors import SyndError
from synd.search.fts import get_chunks_by_id, search
from synd.storage.db import Database

console = Console()

DEFAULT_DB = Path(".synd/index.db")


def _open_db() -> Database:
    """Open the default Tank database."""
    db_path = DEFAULT_DB
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return Database(db_path)


@click.command()
@click.argument("query")
@click.option(
    "--package", "packages", multiple=True, help="Filter by package name (repeatable)"
)
@click.option(
    "--detail", "detail", type=click.Choice(["summary", "full"]), default="summary"
)
@click.option(
    "--limit", "limit", default=10, type=int, help="Maximum number of results"
)
@click.option(
    "--chunk-ids",
    "chunk_ids",
    default=None,
    help="Comma-separated chunk IDs to retrieve",
)
def query(
    query: str,
    packages: tuple[str, ...],
    detail: str,
    limit: int,
    chunk_ids: str | None,
) -> None:
    """Search imported documentation packs using full-text search."""
    pkg_list = list(packages) if packages else None

    try:
        db = _open_db()
        db.create_schema()

        if chunk_ids is not None:
            ids = [int(cid.strip()) for cid in chunk_ids.split(",") if cid.strip()]
            results = get_chunks_by_id(db, ids, detail=detail)
        else:
            results = search(db, query, packages=pkg_list, detail=detail, limit=limit).results
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(title=f"Search results ({len(results)} found)")
    table.add_column("Package", style="cyan")
    table.add_column("Version", style="magenta")
    table.add_column("Heading", style="green")
    table.add_column("Score", justify="right")
    table.add_column("Content", overflow="fold")

    for r in results:
        # Build the content cell
        if detail == "full" and r.content:
            content_text = r.content[:200]
        else:
            content_text = r.summary or ""

        warning = ""
        if r.lifecycle_warning:
            warning = f" [{r.lifecycle_warning}]"

        cell_text = f"{content_text}{warning}"

        table.add_row(
            r.package,
            r.version,
            r.heading_path or "",
            f"{r.score:.3f}",
            cell_text,
        )

    console.print(table)
