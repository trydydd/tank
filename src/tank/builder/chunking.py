from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from chunkana import chunk_text as _chunk_text  # type: ignore[import-untyped]

from tank.builder.normalizer import normalize

_WHITELISTED = {".md", ".html", ".htm"}


@dataclass
class RawChunk:
    heading_path: str
    content: str
    source_url: str
    page_id: int
    id: int = 0
    summary: str | None = None
    token_count: int | None = None
    source_commit: str | None = None


def discover_files(source: Path) -> list[Path]:
    """Recursively discover documentation files, sorted lexicographically.

    Only files with whitelisted extensions (.md, .html, .htm) are included.
    """
    result: list[Path] = []
    for root, _dirs, files in os.walk(source):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _WHITELISTED:
                result.append(Path(root) / fname)
    # Sort by the full relative path from source parent for determinism
    source_parent = source.parent if str(source).startswith("./") else source
    result = sorted(
        result, key=lambda p: Path(os.path.relpath(p, source_parent)).as_posix()
    )
    return result


def chunk_file(file_path: Path, source: Path, page_id: int) -> list[RawChunk]:
    """Chunk a single documentation file using chunkana.

    heading_path is constructed as: <relative_file_prefix> / <first section_tag>
    where relative_file_prefix is the path relative to source, minus extension.
    section_tags is the chunkana metadata field that holds headers present in
    the chunk; header_path is always empty and not used.
    """
    relative = Path(os.path.relpath(file_path, source)).as_posix()
    prefix = Path(relative).with_suffix("")  # e.g. "auth/oauth"

    raw_content = file_path.read_text(encoding="utf-8")
    ana_chunks = _chunk_text(raw_content)

    chunks: list[RawChunk] = []
    for ana in ana_chunks:
        # chunkana never populates header_path; section headings are in section_tags.
        section_tags: list[str] = ana.metadata.get("section_tags") or []
        parts: list[str] = [str(prefix)]
        if section_tags:
            parts.append(section_tags[0])
        heading_path = " / ".join(parts)

        content = normalize(ana.content)
        chunks.append(
            RawChunk(
                heading_path=heading_path,
                content=content,
                source_url=relative,
                page_id=page_id,
            )
        )
    return chunks


def generate_summary(content: str) -> str:
    """Generate a one-line summary from chunk content.

    Prose-heavy: first sentence, truncated at 200 chars if needed.
    Code-heavy (>50% inside fences): first function/class signature.
    """
    lines = content.split("\n")
    in_fence = False
    code_line_count = 0
    prose_lines: list[str] = []
    first_fence_content: list[str] = []  # content INSIDE the first code block
    inside_first_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                # Opening fence — next lines are code block content
                in_fence = True
                inside_first_fence = True
                first_fence_content = []
            else:
                # Closing fence
                in_fence = False
                inside_first_fence = False
            continue
        if in_fence:
            code_line_count += 1
            if inside_first_fence:
                first_fence_content.append(line)
        else:
            prose_lines.append(line)

    total = max(len(lines), 1)
    is_code_heavy = (code_line_count / total) > 0.5

    if is_code_heavy and first_fence_content:
        # Look for def/class/function/export inside the first code block
        for fl in first_fence_content:
            s = fl.strip()
            if s.startswith(("def ", "class ", "function ", "export ")):
                return s
        # Fall back to first prose sentence
        return (
            _first_sentence(prose_lines) if prose_lines else _heading_fallback(content)
        )

    return _first_sentence(prose_lines) if prose_lines else _heading_fallback(content)


def _first_sentence(parts: list[str]) -> str:
    text = " ".join(parts)
    match = re.match(r"([^.!?]*[.!?])\s*", text)
    if match:
        sentence = match.group(1).rstrip()
    else:
        sentence = text

    if len(sentence) > 200:
        truncated = sentence[:200]
        # Back up to last word boundary
        last_space = truncated.rfind(" ")
        if last_space > 100:  # don't truncate too short
            truncated = truncated[:last_space]
        return truncated + "..."
    return sentence


def _heading_fallback(content: str) -> str:
    """Last resort: use the first heading line."""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    # Absolute last resort: first 200 chars
    return (content[:200] + "...") if len(content) > 200 else content
