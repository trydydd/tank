from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Callable, cast

from tank.builder.chunking import RawChunk


def _sha256hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_manifest(
    package: str,
    version: str,
    chunks_count: int,
    pages_count: int,
    normalized_content_hash: str,
    lifecycle: str,
    doc_version_status: str,
    owner: str | None,
    policy_profile: str | None,
    source_url: str,
    source_commit: str | None,
) -> dict[str, str | int | float | None]:
    """Build the manifest dictionary from build parameters."""
    manifest: dict[str, str | int | float | None] = {
        "schema_version": 2,
        "pack_format": "tank-text-v1",
        "package": package,
        "version": version,
        "pack_digest": "",
        "normalized_content_hash": normalized_content_hash,
        "chunks": chunks_count,
        "pages": pages_count,
        "lifecycle_state": lifecycle,
        "doc_version_status": doc_version_status,
        "source_url": source_url,
        "created_at": time.time(),
        "created_by": "tank/0.1.0",
    }
    if owner is not None:
        manifest["owner"] = owner
    if policy_profile is not None:
        manifest["policy_profile"] = policy_profile
    if source_commit is not None:
        manifest["source_commit"] = source_commit
    return manifest


def compute_pack_digest(archive_path: Path) -> str:
    """Compute pack_digest over the archive bytes.

    Reads the archive, extracts manifest.json, zeroes out the pack_digest
    field, rebuilds the zip with the zeroed manifest, then hashes the
    resulting bytes.
    """
    with zipfile.ZipFile(archive_path, "r") as zf:
        manifest_json = zf.read("manifest.json")

    manifest = json.loads(manifest_json)
    manifest["pack_digest"] = ""
    zeroed_manifest = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(archive_path, "r") as zf:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for item in zf.infolist():
                content = zf.read(item.filename)
                if item.filename == "manifest.json":
                    content = zeroed_manifest
                out.writestr(item, content)

    return _sha256hex(buf.getvalue())


def load_manifest(ctx_path: Path) -> dict[str, str | int | float | None]:
    """Load and parse manifest.json from a .ctx archive."""
    with zipfile.ZipFile(ctx_path, "r") as zf:
        return cast(
            dict[str, str | int | float | None], json.loads(zf.read("manifest.json"))
        )


def compute_normalized_content_hash(
    chunks: list[RawChunk],
    normalize_fn: Callable[[str], str],
) -> str:
    """Compute normalized_content_hash from RawChunk objects.

    Concatenates normalized content strings in ascending ID order with newline
    separator, then hashes.
    """
    sorted_chunks = sorted(chunks, key=lambda c: c.id)
    parts: list[str] = []
    for chunk in sorted_chunks:
        normalized = normalize_fn(chunk.content)
        parts.append(normalized)
    concatenated = "\n".join(parts)
    return _sha256hex(concatenated)
