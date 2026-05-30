from __future__ import annotations

import hashlib
import json
import struct
import time
import zipfile
from pathlib import Path
from typing import Callable, cast

from synd.builder.chunking import RawChunk
from synd.schemas.types import ManifestDict


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
) -> ManifestDict:
    """Build the manifest dictionary from build parameters.

    The returned dict matches the manifest.v2 schema structurally; enum values
    are validated at the boundary (see synd.schemas.validate_manifest), which
    the builder calls before writing the final archive.
    """
    manifest: ManifestDict = {
        "schema_version": 2,
        "pack_format": "synd-text-v1",
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
        "created_by": "synd/0.1.1",
    }
    if owner is not None:
        manifest["owner"] = owner
    if policy_profile is not None:
        manifest["policy_profile"] = policy_profile
    if source_commit is not None:
        manifest["source_commit"] = source_commit
    return manifest


def compute_pack_digest(archive_path: Path) -> str:
    """Compute pack_digest by hashing each entry's content in filename-sorted order.

    Wire format per entry: 4-byte big-endian name length, name bytes,
    4-byte big-endian content length, content bytes. manifest.json is hashed
    with its pack_digest field zeroed to avoid the circular-dependency problem.
    """
    h = hashlib.sha256()
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            name_bytes = info.filename.encode("utf-8")
            content = zf.read(info.filename)
            if info.filename == "manifest.json":
                manifest = json.loads(content)
                manifest["pack_digest"] = ""
                content = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            h.update(struct.pack(">I", len(name_bytes)))
            h.update(name_bytes)
            h.update(struct.pack(">I", len(content)))
            h.update(content)
    return "sha256:" + h.hexdigest()


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
