from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

from synd.builder.normalizer import normalize

_MD = MarkdownIt()
_DEFAULT_MAX_CHUNK_TOKENS: int = 800
_DEFAULT_MIN_CHUNK_TOKENS: int = 20
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
    # Sort by the full relative path from source for determinism
    result = sorted(result, key=lambda p: Path(os.path.relpath(p, source)).as_posix())
    return result


def chunk_content(
    content: str,
    heading_prefix: str,
    source_url: str,
    page_id: int,
    max_chunk_tokens: int = _DEFAULT_MAX_CHUNK_TOKENS,
    min_chunk_tokens: int = _DEFAULT_MIN_CHUNK_TOKENS,
) -> list[RawChunk]:
    """Chunk markdown content using a markdown-it-py token walker.

    Splits at all heading levels (#-######). Treats code fences as atomic.
    Splits oversized sections at paragraph boundaries when content exceeds
    max_chunk_tokens (measured as len(text) // 4).
    """
    tokens = _MD.parse(content)
    source_lines = content.split("\n")

    # ancestor_stack[0] = heading_prefix (never popped — prefix sentinel)
    # ancestor_stack[1..] = heading texts from outermost to innermost
    ancestor_stack: list[str] = [heading_prefix]
    level_stack: list[int] = [0]  # parallel to ancestor_stack; 0 = prefix sentinel

    chunk_start_line: int = 0
    current_para_end_line: int = 0
    chunks: list[RawChunk] = []

    def _emit(end_line: int) -> None:
        nonlocal chunk_start_line
        raw = "\n".join(source_lines[chunk_start_line:end_line]).strip()
        if raw:
            chunks.append(
                RawChunk(
                    heading_path=" / ".join(ancestor_stack),
                    content=normalize(raw),
                    source_url=source_url,
                    page_id=page_id,
                )
            )
        chunk_start_line = end_line

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "heading_open":
            heading_level = int(token.tag[1])  # "h1"->1, "h2"->2, …
            inline_token = tokens[i + 1]
            heading_text = inline_token.content
            assert (
                token.map is not None
            )  # heading_open tokens always carry a source map
            heading_line = token.map[0]  # 0-indexed line number

            # Only emit if accumulated content meets the minimum token threshold.
            # Below threshold: leave chunk_start_line in place so stub content
            # flows into the next section rather than becoming a near-empty chunk.
            candidate = "\n".join(source_lines[chunk_start_line:heading_line]).strip()
            if len(candidate) // 4 >= min_chunk_tokens:
                _emit(heading_line)
                chunk_start_line = heading_line

            # Always update ancestor stack so heading_path is correct for the
            # next emit regardless of whether we emitted above.
            while len(level_stack) > 1 and level_stack[-1] >= heading_level:
                ancestor_stack.pop()
                level_stack.pop()
            ancestor_stack.append(heading_text)
            level_stack.append(heading_level)

            i += 3  # skip heading_open, inline, heading_close
            continue

        # Track end of paragraphs for overflow detection
        if token.type == "paragraph_open" and token.map:
            current_para_end_line = token.map[1]

        # At paragraph close: split if accumulated content exceeds the token budget
        if token.type == "paragraph_close":
            accumulated = "\n".join(
                source_lines[chunk_start_line:current_para_end_line]
            )
            if len(accumulated) // 4 > max_chunk_tokens:
                _emit(current_para_end_line)

        i += 1

    # Emit the final trailing chunk
    _emit(len(source_lines))

    return chunks


def chunk_file(
    file_path: Path,
    source: Path,
    page_id: int,
    max_chunk_tokens: int = _DEFAULT_MAX_CHUNK_TOKENS,
    min_chunk_tokens: int = _DEFAULT_MIN_CHUNK_TOKENS,
) -> list[RawChunk]:
    """Chunk a single documentation file.

    heading_path is constructed as: <relative_file_prefix> / <heading ancestors>
    where relative_file_prefix is the path relative to source, minus extension.
    """
    relative = Path(os.path.relpath(file_path, source)).as_posix()
    prefix = str(Path(relative).with_suffix(""))  # e.g. "auth/oauth"
    raw_content = file_path.read_text(encoding="utf-8")
    return chunk_content(
        raw_content,
        heading_prefix=prefix,
        source_url=relative,
        page_id=page_id,
        max_chunk_tokens=max_chunk_tokens,
        min_chunk_tokens=min_chunk_tokens,
    )


def generate_summary(content: str, heading_path: str = "") -> str:
    """Generate a one-line summary from chunk content.

    If heading_path is provided, prefix the summary with the leaf heading node
    (S2 heading-aware heuristic). Falls back to first-sentence extraction.
    Prose-heavy: first prose sentence, truncated at 200 chars.
    Code-heavy (>50% inside fences): first function/class signature.
    """
    lines = content.split("\n")
    in_fence = False
    code_line_count = 0
    prose_lines: list[str] = []
    first_fence_content: list[str] = []
    inside_first_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                inside_first_fence = True
                first_fence_content = []
            else:
                in_fence = False
                inside_first_fence = False
            continue
        if in_fence:
            code_line_count += 1
            if inside_first_fence:
                first_fence_content.append(line)
        else:
            # Exclude markdown heading lines and list item lines from prose summary
            if not stripped.startswith("#") and not re.match(
                r"^[-*+]\s+|^\d+\.\s+", stripped
            ):
                prose_lines.append(line)

    total = max(len(lines), 1)
    is_code_heavy = (code_line_count / total) > 0.5

    if is_code_heavy and first_fence_content:
        for fl in first_fence_content:
            s = fl.strip()
            if s.startswith(("def ", "class ", "function ", "export ")):
                return s
        prose_summary = (
            _first_sentence(prose_lines) if prose_lines else _heading_fallback(content)
        )
    else:
        prose_summary = (
            _first_sentence(prose_lines) if prose_lines else _heading_fallback(content)
        )

    # S2: prefix with leaf heading node when available
    if not heading_path:
        return prose_summary

    path_parts = heading_path.split(" / ")
    # path_parts[0] is always the file prefix — only use parts[1:] as heading context
    heading_parts = path_parts[1:]
    if not heading_parts:
        return prose_summary  # preamble chunk: heading_path is just the file prefix

    leaf = heading_parts[-1]
    if len(leaf) > 60:
        return leaf
    if prose_summary.startswith(leaf):
        return prose_summary  # avoid "Foo: Foo is..." redundancy
    return f"{leaf}: {prose_summary}"


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
