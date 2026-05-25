"""tank sync command — reproduce the local index from tank.lock."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import click
from rich.console import Console

from tank.cli._lockfile import LOCK_FILE, read_lockfile, write_lockfile
from tank.cli.add import _import_pack
from tank.errors import FetchError, LockfileError, TankError
from tank.policy.engine import Policy
from tank.storage.db import Database
from tank.validator.verify import verify

console = Console()

TANK_DIR = Path(".tank")
INDEX_DB = TANK_DIR / "index.db"


def _resolve_source(source_url: str, frozen: bool) -> Path:
    """Resolve a source_url to a local Path, fetching if needed.

    Currently only local paths are supported.  HTTPS URLs require the fetcher
    module (planned for a future release) and raise ``FetchError`` unless
    ``frozen=True``, in which case the error message differs.

    Args:
        source_url: The ``source_url`` value from the lockfile entry.
        frozen: If True, fail immediately for HTTPS URLs without attempting
            to fetch (analogous to ``cargo build --frozen``).

    Returns:
        A Path to the local .ctx file.

    Raises:
        FetchError: If source_url is an HTTPS URL (fetcher not yet available).
        FileNotFoundError: If source_url is a local path that does not exist.
    """
    if source_url.startswith("https://"):
        if frozen:
            raise FetchError(
                f"--frozen: would need to fetch {source_url!r} "
                "but network access is disabled"
            )
        raise FetchError(
            f"URL fetching is not yet supported — download the pack manually "
            f"and run 'tank add <path.ctx>' instead.\n"
            f"  source_url: {source_url}"
        )

    path = Path(source_url)
    if not path.exists():
        raise FileNotFoundError(
            f"source_url {source_url!r} is a local path that does not exist. "
            "Download the pack and re-run 'tank add <path.ctx>'."
        )
    return path


@click.command()
@click.option(
    "--policy", type=click.Path(path_type=Path), default=None, help="Policy file path"
)
@click.option(
    "--frozen",
    is_flag=True,
    default=False,
    help="Fail immediately if any pack requires network access.",
)
def sync(policy: Path | None, frozen: bool) -> None:
    """Import all packs listed in tank.lock that are not yet in the local index.

    Reads tank.lock from the current directory, verifies each pack's digest
    against the lockfile, then imports any packs that are not already present.
    Skips packs that are already imported at the recorded digest.

    This command is idempotent: running it multiple times is safe.
    """
    policy_obj = Policy.load(policy_path=policy)

    # Read and validate the lockfile
    try:
        entries = read_lockfile(LOCK_FILE)
    except LockfileError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)

    if not entries:
        console.print("[dim]tank.lock contains no packs — nothing to sync[/dim]")
        return

    TANK_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(INDEX_DB)
    db.create_schema()

    imported = 0
    skipped = 0
    failed = 0

    for spec, entry in entries.items():
        # Parse "package@version" spec
        if "@" not in spec:
            console.print(
                f"[yellow]warning: skipping malformed pack spec {spec!r}[/yellow]"
            )
            failed += 1
            continue

        name, version = spec.rsplit("@", 1)

        # Check if already imported at the expected digest
        expected_digest = entry.get("pack_digest", "")
        if db.pack_exists(name, version):
            console.print(f"  [dim]skip  {spec} (already imported)[/dim]")
            skipped += 1
            continue

        # Resolve the source to a local path
        source_url = entry.get("source_url", "")
        if not source_url:
            console.print(
                f"  [red]fail  {spec}: no source_url in lockfile — "
                "re-add with 'tank add <path.ctx>'[/red]"
            )
            failed += 1
            continue

        try:
            ctx_path = _resolve_source(source_url, frozen)
        except (FetchError, FileNotFoundError) as exc:
            console.print(f"  [red]fail  {spec}: {exc}[/red]")
            failed += 1
            continue

        # Pre-check: verify digest matches lockfile BEFORE running the verifier.
        # A mismatch here is a supply-chain signal — reject loudly.
        if expected_digest:
            from tank.builder.manifest import compute_pack_digest

            actual_digest = compute_pack_digest(ctx_path)
            if actual_digest != expected_digest:
                console.print(
                    f"  [red]fail  {spec}: digest mismatch[/red]\n"
                    f"    expected: {expected_digest}\n"
                    f"    actual:   {actual_digest}\n"
                    "    The pack file does not match the lockfile. "
                    "Re-download and run 'tank add' again."
                )
                failed += 1
                continue

        # Run the full 8-step verifier + policy
        verify_result = verify(ctx_path=ctx_path, policy=policy_obj)
        if not verify_result.passed:
            step_label = (
                f"step {verify_result.step}"
                if verify_result.step is not None
                else "unknown"
            )
            console.print(
                f"  [red]fail  {spec}: verification failed at {step_label}: "
                f"{verify_result.reason}[/red]"
            )
            failed += 1
            continue

        # Import
        try:
            _import_pack(ctx_path, policy_obj, db)
            console.print(f"  [green]add   {spec}[/green]")
            imported += 1
        except (TankError, zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
            console.print(f"  [red]fail  {spec}: {exc}[/red]")
            failed += 1

    # Rewrite the lockfile to reflect current indexed_at timestamps
    try:
        write_lockfile(db, LOCK_FILE)
    except OSError as exc:
        console.print(f"[yellow]warning: could not update tank.lock: {exc}[/yellow]")

    db.close()

    # Summary
    parts = []
    if imported:
        parts.append(f"[green]{imported} imported[/green]")
    if skipped:
        parts.append(f"[dim]{skipped} skipped[/dim]")
    if failed:
        parts.append(f"[red]{failed} failed[/red]")

    summary = ", ".join(parts) if parts else "nothing to do"
    console.print(f"\nsync complete: {summary}")

    if failed:
        sys.exit(1)
