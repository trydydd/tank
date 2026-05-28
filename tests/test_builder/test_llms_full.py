from __future__ import annotations

from unittest.mock import patch

import pytest

from synd.builder.llms_full import LlmsPage, fetch_pages, parse_llms_txt
from synd.errors import FetchError

_SAMPLE_LLMS_TXT = """\
# My Library Documentation

> Context for LLMs

## Docs

- [Getting Started](https://docs.example.com/start.md)
- [API Reference](https://docs.example.com/api.md)
- [Configuration](https://docs.example.com/config.md)

## Optional

- [Changelog](https://docs.example.com/changelog.md)
"""


def test_parse_llms_txt_extracts_urls() -> None:
    pages = parse_llms_txt(_SAMPLE_LLMS_TXT)
    urls = [p.url for p in pages]
    assert "https://docs.example.com/start.md" in urls
    assert "https://docs.example.com/api.md" in urls
    assert "https://docs.example.com/config.md" in urls
    assert "https://docs.example.com/changelog.md" in urls


def test_parse_llms_txt_extracts_labels() -> None:
    pages = parse_llms_txt(_SAMPLE_LLMS_TXT)
    labels = [p.label for p in pages]
    assert "Getting Started" in labels
    assert "API Reference" in labels


def test_parse_llms_txt_preserves_order() -> None:
    pages = parse_llms_txt(_SAMPLE_LLMS_TXT)
    assert pages[0].url == "https://docs.example.com/start.md"
    assert pages[1].url == "https://docs.example.com/api.md"
    assert pages[2].url == "https://docs.example.com/config.md"


def test_parse_llms_txt_skips_non_link_lines() -> None:
    text = "# Title\n> A description\nSome prose without links.\n"
    pages = parse_llms_txt(text)
    assert pages == []


def test_parse_llms_txt_returns_llms_page_instances() -> None:
    text = "- [Title](https://example.com/page.md)\n"
    pages = parse_llms_txt(text)
    assert len(pages) == 1
    assert isinstance(pages[0], LlmsPage)
    assert pages[0].url == "https://example.com/page.md"
    assert pages[0].label == "Title"


def test_fetch_pages_calls_fetch_page_for_each_entry() -> None:
    index_text = (
        "- [A](https://docs.example.com/a.md)\n- [B](https://docs.example.com/b.md)\n"
    )

    def _fake_fetch(url: str, *, rate_limit_sleep: float = 0.0) -> str:
        if url == "https://docs.example.com/index.txt":
            return index_text
        return f"# Content from {url}"

    with patch("synd.builder.llms_full.fetch_page", side_effect=_fake_fetch):
        results = fetch_pages(
            "https://docs.example.com/index.txt", rate_limit_sleep=0.0
        )

    assert len(results) == 2
    assert results[0][0] == "https://docs.example.com/a.md"
    assert "a.md" in results[0][1]
    assert results[1][0] == "https://docs.example.com/b.md"


def test_fetch_pages_skips_failed_pages() -> None:
    index_text = (
        "- [Good](https://docs.example.com/good.md)\n"
        "- [Bad](https://docs.example.com/bad.md)\n"
    )

    def _fake_fetch(url: str, *, rate_limit_sleep: float = 0.0) -> str:
        if url == "https://docs.example.com/index.txt":
            return index_text
        if "bad" in url:
            raise FetchError("HTTP 404 fetching bad.md")
        return "# Good content"

    with patch("synd.builder.llms_full.fetch_page", side_effect=_fake_fetch):
        results = fetch_pages(
            "https://docs.example.com/index.txt", rate_limit_sleep=0.0
        )

    assert len(results) == 1
    assert results[0][0] == "https://docs.example.com/good.md"


def test_fetch_pages_raises_fetch_error_when_index_fails() -> None:
    with patch(
        "synd.builder.llms_full.fetch_page",
        side_effect=FetchError("HTTP 404 fetching index"),
    ):
        with pytest.raises(FetchError, match="HTTP 404"):
            fetch_pages("https://docs.example.com/index.txt")
