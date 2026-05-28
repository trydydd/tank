from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from synd.builder.chunking import (
    RawChunk,
    _DEFAULT_MAX_CHUNK_TOKENS,
    _DEFAULT_MIN_CHUNK_TOKENS,
    chunk_content,
    chunk_file,
    discover_files,
    generate_summary,
)
from synd.builder.llms_full import LlmsFullPage, fetch_llms_full_pages, fetch_pages
from synd.builder.url_filter import DEFAULT_NOISE_URL_PATTERNS, filter_page_urls
from synd.builder.manifest import (
    build_manifest,
    compute_normalized_content_hash,
    compute_pack_digest,
)
from synd.builder.normalizer import normalize
from synd.errors import BuildError, FetchError
from synd.storage.models import Page


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
    max_chunk_tokens: int = _DEFAULT_MAX_CHUNK_TOKENS,
    min_chunk_tokens: int = _DEFAULT_MIN_CHUNK_TOKENS,
    warn_chunk_tokens: int | None = None,
) -> tuple[Path, list[RawChunk]]:
    """Build a .ctx pack from a local source directory.

    Returns the path to the created .ctx file.
    """
    if not source.is_dir():
        raise BuildError(f"Source directory does not exist: {source}")

    files = discover_files(source)
    if not files:
        raise BuildError(f"No documentation files found in {source}")

    # Determine source_url: normalize the source path, strip leading "./"
    source_url = Path(source).as_posix()
    if source_url.startswith("./"):
        source_url = source_url[2:]

    # Build pages and raw chunks
    raw_chunks: list[RawChunk] = []
    pages: list[Page] = []

    for page_id, file_path in enumerate(files, start=1):
        file_source_url = Path(os.path.relpath(file_path, source.parent)).as_posix()
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
        file_chunks = chunk_file(
            file_path,
            source,
            page_id,
            max_chunk_tokens=max_chunk_tokens,
            min_chunk_tokens=min_chunk_tokens,
        )
        for chunk in file_chunks:
            chunk.source_url = file_source_url
            raw_chunks.append(chunk)

    output.mkdir(parents=True, exist_ok=True)
    pack_path = output / f"{package}@{version}.ctx"

    return _finalize_pack(
        raw_chunks=raw_chunks,
        pages=pages,
        pack_path=pack_path,
        package=package,
        version=version,
        source_url=source_url,
        lifecycle=lifecycle,
        doc_version_status=doc_version_status,
        owner=owner,
        policy_profile=policy_profile,
        source_commit=source_commit,
        max_chunk_tokens=max_chunk_tokens,
        warn_chunk_tokens=warn_chunk_tokens,
    )


def build_pack_from_url(
    package: str,
    version: str,
    source_url: str,
    output: Path,
    lifecycle: str = "draft",
    doc_version_status: str = "stable",
    owner: str | None = None,
    policy_profile: str | None = None,
    source_commit: str | None = None,
    rate_limit_sleep: float = 0.5,
    excluded_url_patterns: tuple[str, ...] = DEFAULT_NOISE_URL_PATTERNS,
    max_chunk_tokens: int = _DEFAULT_MAX_CHUNK_TOKENS,
    min_chunk_tokens: int = _DEFAULT_MIN_CHUNK_TOKENS,
    warn_chunk_tokens: int | None = None,
) -> tuple[Path, list[RawChunk]]:
    """Build a .ctx pack from a URL source (llms-full.txt or llms.txt).

    source_url must be an HTTP/HTTPS URL ending in 'llms-full.txt' or 'llms.txt'.
    Returns the path to the created .ctx file.
    Raises BuildError if the URL type is unrecognised, the fetch fails, or
    no pages are returned.
    """
    if source_url.endswith("llms-full.txt"):
        try:
            llms_pages: list[LlmsFullPage] = fetch_llms_full_pages(source_url)
        except FetchError as exc:
            raise BuildError(f"Failed to fetch {source_url}: {exc}") from exc
        page_pairs = [(p.url, p.content) for p in llms_pages]
    elif source_url.endswith("llms.txt"):
        try:
            page_pairs = fetch_pages(source_url, rate_limit_sleep=rate_limit_sleep)
        except FetchError as exc:
            raise BuildError(f"Failed to fetch {source_url}: {exc}") from exc
    else:
        raise BuildError(
            f"Unsupported URL source: {source_url!r}. "
            "Expected a URL ending in 'llms-full.txt' or 'llms.txt'."
        )

    if not page_pairs:
        raise BuildError(f"No pages found at {source_url}")

    page_pairs, excluded_urls = filter_page_urls(page_pairs, excluded_url_patterns)
    _logger = logging.getLogger(__name__)
    for url in excluded_urls:
        _logger.info("build: excluded noise URL %s", url)

    if not page_pairs:
        raise BuildError(f"No pages remain after URL filtering at {source_url}")

    raw_chunks: list[RawChunk] = []
    pages: list[Page] = []

    for page_id, (page_url, content) in enumerate(page_pairs, start=1):
        label = _url_path_label(page_url)
        normalized_content = normalize(content)
        content_hash = (
            "sha256:" + hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        )
        title = _extract_title(content) or label

        pages.append(
            Page(
                id=page_id,
                package=package,
                version=version,
                url=page_url,
                title=title,
                content_hash=content_hash,
            )
        )

        page_chunks = chunk_content(
            content,
            heading_prefix=label,
            source_url=page_url,
            page_id=page_id,
            max_chunk_tokens=max_chunk_tokens,
            min_chunk_tokens=min_chunk_tokens,
        )
        raw_chunks.extend(page_chunks)

    if not raw_chunks:
        raise BuildError(f"No chunks produced from pages at {source_url}")

    output.mkdir(parents=True, exist_ok=True)
    pack_path = output / f"{package}@{version}.ctx"

    return _finalize_pack(
        raw_chunks=raw_chunks,
        pages=pages,
        pack_path=pack_path,
        package=package,
        version=version,
        source_url=source_url,
        lifecycle=lifecycle,
        doc_version_status=doc_version_status,
        owner=owner,
        policy_profile=policy_profile,
        source_commit=source_commit,
        max_chunk_tokens=max_chunk_tokens,
        warn_chunk_tokens=warn_chunk_tokens,
    )


def _finalize_pack(
    raw_chunks: list[RawChunk],
    pages: list[Page],
    pack_path: Path,
    package: str,
    version: str,
    source_url: str,
    lifecycle: str = "draft",
    doc_version_status: str = "stable",
    owner: str | None = None,
    policy_profile: str | None = None,
    source_commit: str | None = None,
    max_chunk_tokens: int = _DEFAULT_MAX_CHUNK_TOKENS,
    warn_chunk_tokens: int | None = None,
) -> tuple[Path, list[RawChunk]]:
    """Assign IDs, compute hashes, generate summaries, write .ctx archive.

    Shared by build_pack() (directory sources) and build_pack_from_url()
    (URL sources). Returns (pack_path, oversized_chunks) where oversized_chunks
    are chunks whose token_count exceeds warn_chunk_tokens (defaults to 2× max).
    """
    for i, rc in enumerate(raw_chunks, start=1):
        rc.id = i

    normalized_content_hash = compute_normalized_content_hash(raw_chunks, normalize)

    for rc in raw_chunks:
        rc.token_count = len(rc.content) // 4

    for rc in raw_chunks:
        if not rc.summary:
            rc.summary = generate_summary(rc.content, heading_path=rc.heading_path)

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

    # Write with zeroed digest, compute real digest, rewrite.
    _write_archive(
        path=pack_path, manifest=manifest, raw_chunks=raw_chunks, pages=pages
    )
    real_digest = compute_pack_digest(pack_path)
    manifest["pack_digest"] = real_digest
    _write_archive(
        path=pack_path, manifest=manifest, raw_chunks=raw_chunks, pages=pages
    )

    # Detect chunks that exceed the warning threshold after all splits.
    # warn_chunk_tokens defaults to 2× max_chunk_tokens when not specified.
    effective_warn = (
        warn_chunk_tokens if warn_chunk_tokens is not None else 2 * max_chunk_tokens
    )
    oversized = [rc for rc in raw_chunks if (rc.token_count or 0) > effective_warn]
    oversized.sort(key=lambda rc: rc.token_count or 0, reverse=True)

    return pack_path, oversized


def _url_path_label(url: str) -> str:
    """Extract a path-relative label from a page URL for use in heading_path.

    'https://docs.example.com/api/auth.md' → 'api/auth'
    'https://docs.example.com/guide'       → 'guide'
    Falls back to the full URL string when the path component is empty.
    """
    path = urlparse(url).path.lstrip("/")
    if not path:
        return url
    p = PurePosixPath(path)
    label = str(p.with_suffix("")) if p.suffix else path
    return label or url


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
