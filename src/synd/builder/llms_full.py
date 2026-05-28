"""llms.txt index parsing and per-page fetch orchestration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from synd.builder.fetch import fetch_page
from synd.errors import FetchError

_log = logging.getLogger(__name__)

# Matches markdown link syntax: [label](https://...)
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


@dataclass
class LlmsPage:
    """A single page entry parsed from a llms.txt index."""

    url: str
    label: str


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
    index_content = fetch_page(index_url)
    entries = parse_llms_txt(index_content)

    results: list[tuple[str, str]] = []
    for entry in entries:
        try:
            content = fetch_page(entry.url, rate_limit_sleep=rate_limit_sleep)
            results.append((entry.url, content))
        except FetchError as exc:
            _log.warning("Skipping %s: %s", entry.url, exc)

    return results
