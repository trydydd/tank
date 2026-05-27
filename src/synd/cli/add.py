"""tank add command — verify and import a .ctx documentation pack."""

from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console

from synd.cli._lockfile import LOCK_FILE, write_lockfile
from synd.errors import SyndError
from synd.policy.engine import Policy
from synd.storage.db import Database
from synd.storage.models import Chunk, Pack, Page
from synd.validator.verify import verify

console = Console()

SYND_DIR = Path(".synd")
INDEX_DB = SYND_DIR / "index.db"


def _import_pack(ctx_path: Path, policy: Policy, db: Database) -> Path:
    """Import a verified .ctx pack into the database.

    Returns the pack path.
    """
    from synd.builder.manifest import load_manifest

    manifest = load_manifest(ctx_path)
    doc_version_status = str(manifest.get("doc_version_status", "unknown"))
    if doc_version_status == "unknown":
        console.print(
            "[yellow]warning: manifest does not specify doc_version_status; "
            "defaulting to 'unknown'[/yellow]"
        )
    pack = Pack(
        name=str(manifest["package"]),
        version=str(manifest["version"]),
        lifecycle_state=str(manifest["lifecycle_state"]),
        doc_version_status=doc_version_status,
        indexed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        policy_profile=str(manifest.get("policy_profile", "")),
        pack_digest=str(manifest["pack_digest"]),
        normalized_content_hash=str(manifest["normalized_content_hash"]),
        source_url=str(manifest.get("source_url", "")),
        source_commit=str(manifest.get("source_commit", "")),
        owner=str(manifest.get("owner", "")),
        pack_source=str(ctx_path),
    )

    with zipfile.ZipFile(ctx_path, "r") as zf:
        pages_data = json.loads(zf.read("pages.json"))
        chunks_data = zf.read("chunks.jsonl").decode("utf-8")

    pages: list[Page] = [
        Page(
            id=p["id"],
            package=p["package"],
            version=p["version"],
            url=p["url"],
            title=p.get("title"),
            content_hash=p.get("content_hash"),
        )
        for p in pages_data
    ]

    chunks: list[Chunk] = []
    for line in chunks_data.strip().split("\n"):
        if not line:
            continue
        c = json.loads(line)
        chunks.append(
            Chunk(
                id=c["id"],
                package=pack.name,
                version=pack.version,
                content=c["content"],
                page_id=c.get("page_id"),
                heading_path=c.get("heading_path"),
                summary=c.get("summary"),
                token_count=c.get("token_count"),
                source_url=c.get("source_url"),
                source_commit=c.get("source_commit"),
                content_hash=c.get("content_hash"),
            )
        )

    db.import_pack(pack, pages, chunks)
    return ctx_path


@click.command()
@click.argument("ctx_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--policy", type=click.Path(path_type=Path), default=None, help="Policy file path"
)
@click.option(
    "--force", is_flag=True, default=False, help="Force reimport of existing pack"
)
def add(ctx_path: Path, policy: Path | None, force: bool) -> None:
    """Verify and import a .ctx documentation pack into the local index."""
    policy_obj = Policy.load(policy_path=policy)

    # Step 1: Verify the pack
    result = verify(ctx_path=ctx_path, policy=policy_obj)
    if not result.passed:
        step_label = f"step {result.step}" if result.step is not None else "unknown"
        console.print(
            f"[red]Verification failed at {step_label}: {result.reason}[/red]"
        )
        sys.exit(1)

    # Step 2: Import
    try:
        SYND_DIR.mkdir(parents=True, exist_ok=True)
        db = Database(INDEX_DB)
        db.create_schema()

        with zipfile.ZipFile(ctx_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        pack_name = manifest["package"]
        pack_version = manifest["version"]

        if not force and db.pack_exists(pack_name, pack_version):
            console.print(
                f"[red]error: pack {pack_name}@{pack_version} is already imported. "
                "Use --force to reimport.[/red]"
            )
            db.close()
            sys.exit(1)

        # When --force, delete the existing pack so import_pack succeeds
        if force and db.pack_exists(pack_name, pack_version):
            db.delete_pack(pack_name, pack_version)

        _import_pack(ctx_path, policy_obj, db)
        write_lockfile(db, LOCK_FILE)
        db.close()

        console.print(
            f"[green]Successfully imported {pack_name}@{pack_version}[/green]"
        )
    except (SyndError, zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)


@click.command(hidden=True)
@click.argument("ctx_path", type=click.Path(exists=True, path_type=Path))
@click.option("--policy", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True, default=False)
@click.pass_context
def pull(ctx: click.Context, ctx_path: Path, policy: Path | None, force: bool) -> None:
    """(Deprecated) Use 'tank add' instead."""
    console.print(
        "[yellow]warning: 'tank pull' is deprecated — use 'tank add' instead[/yellow]"
    )
    ctx.invoke(add, ctx_path=ctx_path, policy=policy, force=force)
