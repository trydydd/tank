"""llms.txt / llms-full.txt index parsing and per-page fetch orchestration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from synd.builder.fetch import fetch_page, fetch_text
from synd.builder.mdx import process_mdx
from synd.errors import FetchError

_log = logging.getLogger(__name__)

# Matches markdown link syntax: [label](https://...)
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

# Matches a Source: boundary line in llms-full.txt
_SOURCE_RE = re.compile(r"^Source:\s+(\S+)\s*$")


@dataclass
class LlmsPage:
    """A single page entry parsed from a llms.txt index."""

    url: str
    label: str


@dataclass
class LlmsFullPage:
    """A single page section parsed from a llms-full.txt blob."""

    url: str
    content: str  # MDX-cleaned markdown, ready for the chunker


def parse_llms_txt(text: str) -> list[LlmsPage]:
    """Extract page entries from a llms.txt index document.

    llms.txt is a markdown document whose page links appear as:
      - [Page Title](https://example.com/page.md)

    Returns entries in source order (preserves llms.txt priority ordering).
    Non-link lines are ignored.
    """
    return [
        LlmsPage(url=match.group(2), label=match.group(1))
        for match in _LINK_RE.finditer(text)
    ]


def split_llms_full_txt(text: str) -> list[LlmsFullPage]:
    """Split an llms-full.txt concatenation into per-page documents.

    llms-full.txt uses 'Source: <url>' lines as page boundaries. Each
    section's content is run through process_mdx() to strip JSX/MDX tags
    and heading pollution before being returned.

    Sections with no content after MDX processing are skipped. Duplicate
    Source URLs are deduplicated (last occurrence wins). A warning is emitted
    when both occurrences have non-empty, differing content.
    Returns pages in first-occurrence order.
    """
    seen: dict[str, LlmsFullPage] = {}
    current_url: str | None = None
    current_lines: list[str] = []

    def _flush(url: str, lines: list[str]) -> None:
        content = process_mdx("\n".join(lines))
        if not content.strip():
            return
        page = LlmsFullPage(url=url, content=content)
        if url in seen and seen[url].content != content:
            _log.warning(
                "Duplicate Source URL with differing content, keeping last occurrence: %s",
                url,
            )
        seen[url] = page

    for line in text.splitlines():
        m = _SOURCE_RE.match(line)
        if m:
            if current_url is not None:
                _flush(current_url, current_lines)
            current_url = m.group(1)
            current_lines = []
        else:
            current_lines.append(line)

    if current_url is not None:
        _flush(current_url, current_lines)

    return list(seen.values())


def fetch_llms_full_pages(index_url: str) -> list[LlmsFullPage]:
    """Fetch a llms-full.txt URL and split it into per-page documents.

    Raises FetchError if the URL cannot be fetched.
    """
    raw = fetch_text(index_url)
    return split_llms_full_txt(raw)


def fetch_pages(
    index_url: str,
    *,
    rate_limit_sleep: float = 0.5,
) -> list[tuple[str, str]]:
    """Fetch a llms.txt index then fetch each linked page individually.

    Returns a list of (page_url, normalised_markdown) pairs in llms.txt order.
    Pages that fail to fetch are skipped with a WARNING log entry — a single
    unreachable page does not abort the whole build.
    Raises FetchError if the llms.txt index itself cannot be fetched.
    """
    index_content = fetch_text(index_url)
    entries = parse_llms_txt(index_content)

    results: list[tuple[str, str]] = []
    for entry in entries:
        try:
            content = fetch_page(entry.url, rate_limit_sleep=rate_limit_sleep)
            results.append((entry.url, content))
        except FetchError as exc:
            _log.warning("Skipping %s: %s", entry.url, exc)

    return results
