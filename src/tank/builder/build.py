from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Mapping
from pathlib import Path

from tank.builder.chunking import RawChunk, chunk_file, discover_files, generate_summary
from tank.builder.manifest import (
    build_manifest,
    compute_normalized_content_hash,
    compute_pack_digest,
)
from tank.builder.normalizer import normalize
from tank.errors import BuildError
from tank.storage.models import Page


def build_pack(
    package: str,
    version: str,
    source: Path,
    output: Path,
    lifecycle: str = "draft",
    doc_version_status: str = "stable",
    owner: str | None = None,
    policy_profile: str | None = None,
    source_commit: str | None = None,
) -> Path:
    """Build a .ctx pack from a local source directory.

    Returns the path to the created .ctx file.
    """
    if not source.is_dir():
        raise BuildError(f"Source directory does not exist: {source}")

    files = discover_files(source)
    if not files:
        raise BuildError(f"No documentation files found in {source}")

    # Determine source_url: normalize the source path, strip leading "./"
    source_url = os.path.normpath(source)
    if source_url.startswith("./"):
        source_url = source_url[2:]

    # Build pages and raw chunks
    raw_chunks: list[RawChunk] = []
    pages: list[Page] = []

    for page_id, file_path in enumerate(files, start=1):
        relative = os.path.relpath(file_path, source.parent)
        file_source_url = relative
        if file_source_url.startswith("./"):
            file_source_url = file_source_url[2:]

        # Read and normalize the full file content for page hash
        raw_content = file_path.read_text(encoding="utf-8")
        normalized_content = normalize(raw_content)
        content_hash = (
            "sha256:" + hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        )

        # Extract title from first heading
        title = _extract_title(raw_content) or Path(file_path).stem

        pages.append(
            Page(
                id=page_id,
                package=package,
                version=version,
                url=file_source_url,
                title=title,
                content_hash=content_hash,
            )
        )

        # Chunk the file
        file_chunks = chunk_file(file_path, source, page_id)
        for chunk in file_chunks:
            chunk.source_url = file_source_url
            raw_chunks.append(chunk)

    # Assign sequential IDs to raw_chunks (already in lexicographic file order)
    for i, rc in enumerate(raw_chunks, start=1):
        rc.id = i

    # Compute hashes
    normalized_content_hash = compute_normalized_content_hash(raw_chunks, normalize)

    # Token counts on raw chunks
    for rc in raw_chunks:
        rc.token_count = len(rc.content) // 4

    # Generate summaries for chunks without one yet
    for rc in raw_chunks:
        if not hasattr(rc, "summary") or not rc.summary:
            rc.summary = generate_summary(rc.content)

    # Build manifest
    manifest = build_manifest(
        package=package,
        version=version,
        chunks_count=len(raw_chunks),
        pages_count=len(pages),
        normalized_content_hash=normalized_content_hash,
        lifecycle=lifecycle,
        doc_version_status=doc_version_status,
        owner=owner,
        policy_profile=policy_profile,
        source_url=source_url,
        source_commit=source_commit,
    )

    # Create output directory if needed
    output.mkdir(parents=True, exist_ok=True)

    # Build archive with zeroed pack_digest
    pack_filename = f"{package}@{version}.ctx"
    pack_path = output / pack_filename

    # Write the zip with empty pack_digest, then compute and rewrite
    _write_archive(
        path=pack_path,
        manifest=manifest,
        raw_chunks=raw_chunks,
        pages=pages,
    )

    # Compute real pack_digest and rewrite manifest
    real_digest = compute_pack_digest(pack_path)
    manifest["pack_digest"] = real_digest
    _write_archive(
        path=pack_path,
        manifest=manifest,
        raw_chunks=raw_chunks,
        pages=pages,
    )

    return pack_path


def _write_archive(
    path: Path,
    manifest: Mapping[str, object],
    raw_chunks: list[RawChunk],
    pages: list[Page],
) -> None:
    """Write a .ctx archive at the given path."""
    chunks_lines = ""
    for rc in raw_chunks:
        record = {
            "id": rc.id,
            "page_id": rc.page_id,
            "heading_path": rc.heading_path,
            "summary": getattr(rc, "summary", None),
            "content": rc.content,
            "token_count": getattr(rc, "token_count", None),
            "source_url": rc.source_url,
            "content_hash": _content_hash(rc.content),
        }
        # Only include source_commit if set
        if hasattr(rc, "source_commit") and rc.source_commit is not None:
            record["source_commit"] = rc.source_commit
        chunks_lines += json.dumps(record, sort_keys=True) + "\n"

    pages_json = json.dumps(
        [
            {
                "id": p.id,
                "package": p.package,
                "version": p.version,
                "url": p.url,
                "title": p.title,
                "content_hash": p.content_hash,
            }
            for p in pages
        ],
        indent=2,
        sort_keys=True,
    )

    # _ZIP_EPOCH pins every entry's timestamp so both archive writes during
    # build produce identical ZipInfo metadata, making pack_digest reproducible
    # by the verifier. This value must never change.
    _ZIP_EPOCH = (2021, 8, 8, 0, 0, 0)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in [
            ("manifest.json", json.dumps(manifest, indent=2, sort_keys=True)),
            ("chunks.jsonl", chunks_lines),
            ("pages.json", pages_json),
        ]:
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content)
        sig_info = zipfile.ZipInfo("signatures/", date_time=_ZIP_EPOCH)
        sig_info.compress_type = zipfile.ZIP_STORED
        zf.writestr(sig_info, "")


def _extract_title(content: str) -> str | None:
    """Extract title from the first # heading in content."""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _content_hash(content: str) -> str:
    """SHA-256 hash of normalized content."""
    normalized = normalize(content)
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
