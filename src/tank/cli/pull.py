"""tank pull command."""

from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console

from tank.errors import TankError
from tank.policy.engine import Policy
from tank.storage.db import Database
from tank.storage.models import Chunk, Pack, Page
from tank.validator.verify import verify

console = Console()

TANK_DIR = Path(".tank")
INDEX_DB = TANK_DIR / "index.db"
LOCK_FILE = TANK_DIR / "index.lock"


def _import_pack(ctx_path: Path, policy: Policy, db: Database) -> Path:
    """Import a verified .ctx pack into the database.

    Returns the pack path.
    """
    from tank.builder.manifest import load_manifest

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
        indexed_at=str(manifest.get("created_at", "")),
        policy_profile=str(manifest.get("policy_profile", "")),
        pack_digest=str(manifest["pack_digest"]),
        normalized_content_hash=str(manifest["normalized_content_hash"]),
        source_url=str(manifest.get("source_url", "")),
        source_commit=str(manifest.get("source_commit", "")),
        owner=str(manifest.get("owner", "")),
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


def _write_lockfile(db: Database) -> None:
    """Write/update .tank/index.lock with current index state."""
    TANK_DIR.mkdir(parents=True, exist_ok=True)
    packs = db.get_packages()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "[meta]",
        "schema_version = 1",
        f'generated_at = "{now}"',
        "",
    ]
    for p in packs:
        lines.append(f'[packs."{p.name}@{p.version}"]')
        lines.append(f'pack_digest = "{p.pack_digest or ""}"')
        lines.append(f'lifecycle_state = "{p.lifecycle_state}"')
        lines.append(f'indexed_at = "{p.indexed_at}"')
        lines.append("")
    LOCK_FILE.write_text("\n".join(lines), encoding="utf-8")


@click.command()
@click.argument("ctx_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--policy", type=click.Path(path_type=Path), default=None, help="Policy file path"
)
@click.option(
    "--force", is_flag=True, default=False, help="Force reimport of existing pack"
)
def pull(ctx_path: Path, policy: Path | None, force: bool) -> None:
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
        TANK_DIR.mkdir(parents=True, exist_ok=True)
        db = Database(INDEX_DB)
        db.create_schema()

        pack_name = None
        pack_version = None
        try:
            with zipfile.ZipFile(ctx_path, "r") as zf:
                manifest = json.loads(zf.read("manifest.json"))
                pack_name = manifest["package"]
                pack_version = manifest["version"]
        except Exception:
            pass

        if (
            not force
            and pack_name
            and pack_version
            and db.pack_exists(pack_name, pack_version)
        ):
            console.print(
                f"[red]error: pack {pack_name}@{pack_version} is already imported. "
                "Use --force to reimport.[/red]"
            )
            db.close()
            sys.exit(1)

        # When --force, delete the existing pack so import_pack succeeds
        if (
            force
            and pack_name
            and pack_version
            and db.pack_exists(pack_name, pack_version)
        ):
            db.delete_pack(pack_name, pack_version)

        _import_pack(ctx_path, policy_obj, db)
        _write_lockfile(db)
        db.close()

        if pack_name:
            console.print(
                f"[green]Successfully imported {pack_name}@{pack_version}[/green]"
            )
        else:
            console.print("[green]Successfully imported pack[/green]")
    except TankError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)
