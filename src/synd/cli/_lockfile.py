"""Shared lockfile read/write logic for synd.lock (TOML, schema version 2).

This module is the single source of truth for lockfile I/O.  Both ``tank add``
and ``tank sync`` call ``write_lockfile``; ``tank sync`` also calls
``read_lockfile``.
"""

from __future__ import annotations

import tomllib
from datetime import datetime, timezone
from pathlib import Path

from synd.errors import LockfileError
from synd.storage.db import Database

LOCK_FILE = Path("synd.lock")
_SUPPORTED_SCHEMA_VERSION = 2


def write_lockfile(db: Database, lock_path: Path = LOCK_FILE) -> None:
    """Regenerate *lock_path* from the current state of *db*.

    Source URL priority:
    - Use ``source_url`` from the pack manifest (``Pack.source_url``) when it
      looks like a canonical HTTPS URL — this is the value ``tank sync`` will
      later use to fetch the pack on a fresh checkout.
    - Fall back to ``pack_source`` (the local filesystem path that was passed to
      ``tank add``) so that locally-imported packs still have a resolvable path
      recorded in the lockfile.
    """
    packs = db.get_packages()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "[meta]",
        "schema_version = 2",
        f'generated_at = "{now}"',
        "",
    ]
    for p in packs:
        lines.append(f'[packs."{p.name}@{p.version}"]')
        lines.append(f'pack_digest = "{p.pack_digest or ""}"')
        lines.append(f'lifecycle_state = "{p.lifecycle_state}"')
        lines.append(f'indexed_at = "{p.indexed_at}"')
        # Prefer the canonical manifest source_url (HTTPS) over the local
        # import path so that `tank sync` can reproduce the pack from a URL.
        source = (
            p.source_url
            if p.source_url and p.source_url.startswith("https://")
            else p.pack_source or ""
        )
        if source:
            lines.append(f'source_url = "{source}"')
        lines.append("")
    lock_path.write_text("\n".join(lines), encoding="utf-8")


def read_lockfile(lock_path: Path = LOCK_FILE) -> dict[str, dict[str, str]]:
    """Parse *lock_path* and return a mapping of pack spec → entry dict.

    The returned dict has the shape::

        {
            "fastmcp@3.3.0": {
                "pack_digest": "sha256:...",
                "lifecycle_state": "draft",
                "indexed_at": "2026-05-25T04:01:28Z",
                "source_url": "https://...",   # may be absent
            },
            ...
        }

    Raises:
        LockfileError: If the file does not exist, cannot be parsed, or has an
            unsupported ``schema_version``.
    """
    if not lock_path.exists():
        raise LockfileError(
            f"{lock_path} not found — run 'tank add <pack.ctx>' to create it"
        )

    try:
        data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise LockfileError(f"failed to parse {lock_path}: {exc}") from exc

    meta = data.get("meta", {})
    version = meta.get("schema_version")
    if version != _SUPPORTED_SCHEMA_VERSION:
        raise LockfileError(
            f"{lock_path} has schema_version={version!r}; "
            f"expected {_SUPPORTED_SCHEMA_VERSION}"
        )

    return {spec: dict(entry) for spec, entry in data.get("packs", {}).items()}
