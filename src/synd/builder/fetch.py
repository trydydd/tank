"""HTML-to-markdown conversion for fetched documentation pages."""

from __future__ import annotations

import re

try:
    import markdownify
    from bs4 import BeautifulSoup
except ImportError as exc:
    raise ImportError(
        "URL fetch requires the serve extra: pip install 'synaptic-drift[serve]'"
    ) from exc

_BOILERPLATE_TAGS = ["nav", "header", "footer", "aside", "script", "style", "noscript"]

_PILCROW_RE = re.compile(r"\[¶\]\([^)]*\)|¶")


def html_to_markdown(html: str) -> str:
    """Convert a fetched HTML page to clean markdown text for chunking.

    Removes navigation, header, footer, and sidebar elements. Targets the
    main content element (<main>, <article>, or role="main") when present.
    Preserves fenced code blocks and pipe-style tables.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(_BOILERPLATE_TAGS):
        tag.decompose()

    main = soup.find("main") or soup.find(role="main") or soup.find("article")
    target = str(main) if main else str(soup.body or soup)

    md = markdownify.markdownify(target, heading_style="ATX")
    md = _PILCROW_RE.sub("", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()
