"""HTML-to-markdown conversion and URL fetching for documentation pages."""

from __future__ import annotations

import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import markdownify
from bs4 import BeautifulSoup

from synd.builder.mdx import process_mdx
from synd.errors import FetchError

_USER_AGENT = "synd/0.1 (https://github.com/trydydd/synaptic-drift)"

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


def fetch_page(url: str, *, rate_limit_sleep: float = 0.0) -> str:
    """Fetch a documentation page and return normalised markdown.

    Routing:
    - URL ends in .md  →  fetch text, run process_mdx(), return markdown
    - otherwise        →  fetch HTML, run html_to_markdown(), return markdown

    Uses urllib.request (stdlib) with a descriptive User-Agent header.
    Raises FetchError on HTTP error status or network failure.

    rate_limit_sleep: seconds to sleep after a successful fetch. Pass a
    nonzero value when looping over many pages to avoid hammering the server.
    """
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=30) as response:  # nosec: B310 (URL from llms.txt/caller)
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} fetching {url}") from exc
    except URLError as exc:
        raise FetchError(f"Network error fetching {url}: {exc.reason}") from exc

    if rate_limit_sleep > 0:
        time.sleep(rate_limit_sleep)

    if url.endswith(".md"):
        return process_mdx(raw)
    return html_to_markdown(raw)
