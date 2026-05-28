from __future__ import annotations

from unittest.mock import patch

import pytest

from synd.builder.llms_full import (
    LlmsFullPage,
    LlmsPage,
    fetch_llms_full_pages,
    fetch_pages,
    parse_llms_txt,
    split_llms_full_txt,
)
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

_SAMPLE_LLMS_FULL_TXT = """\
Source: https://docs.example.com/intro.md
# Introduction

Welcome to the library.

Source: https://docs.example.com/api.md
# API Reference

Use `client.get()` to fetch data.

Source: https://docs.example.com/guide.md
# User Guide

Step-by-step usage instructions.
"""


# --- parse_llms_txt ---


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


# --- split_llms_full_txt ---


def test_split_llms_full_txt_produces_one_page_per_source_boundary() -> None:
    pages = split_llms_full_txt(_SAMPLE_LLMS_FULL_TXT)
    assert len(pages) == 3


def test_split_llms_full_txt_extracts_correct_urls() -> None:
    pages = split_llms_full_txt(_SAMPLE_LLMS_FULL_TXT)
    urls = [p.url for p in pages]
    assert urls[0] == "https://docs.example.com/intro.md"
    assert urls[1] == "https://docs.example.com/api.md"
    assert urls[2] == "https://docs.example.com/guide.md"


def test_split_llms_full_txt_content_contains_heading() -> None:
    pages = split_llms_full_txt(_SAMPLE_LLMS_FULL_TXT)
    assert "# Introduction" in pages[0].content
    assert "# API Reference" in pages[1].content


def test_split_llms_full_txt_content_does_not_include_source_lines() -> None:
    pages = split_llms_full_txt(_SAMPLE_LLMS_FULL_TXT)
    for page in pages:
        assert "Source:" not in page.content


def test_split_llms_full_txt_skips_empty_sections() -> None:
    text = "Source: https://example.com/empty.md\n\nSource: https://example.com/real.md\n# Title\n\nContent.\n"
    pages = split_llms_full_txt(text)
    assert len(pages) == 1
    assert pages[0].url == "https://example.com/real.md"


def test_split_llms_full_txt_strips_mdx_from_content() -> None:
    text = (
        "Source: https://example.com/page.md\n"
        "import Foo from 'bar'\n"
        "# Title\n"
        "<Note>Keep this text.</Note>\n"
    )
    pages = split_llms_full_txt(text)
    assert len(pages) == 1
    assert "import Foo" not in pages[0].content
    assert "Keep this text." in pages[0].content


def test_split_llms_full_txt_returns_llms_full_page_instances() -> None:
    pages = split_llms_full_txt(_SAMPLE_LLMS_FULL_TXT)
    assert all(isinstance(p, LlmsFullPage) for p in pages)


def test_split_llms_full_txt_no_source_boundaries_returns_empty() -> None:
    text = "# Title\n\nSome content without Source: lines.\n"
    pages = split_llms_full_txt(text)
    assert pages == []


def test_split_llms_full_txt_deduplicates_url_with_empty_first_occurrence() -> None:
    text = (
        "Source: https://example.com/page.md\n"
        "\n"
        "Source: https://example.com/page.md\n"
        "# Real Content\n\nActual body.\n"
    )
    pages = split_llms_full_txt(text)
    assert len(pages) == 1
    assert pages[0].url == "https://example.com/page.md"
    assert "Real Content" in pages[0].content


def test_split_llms_full_txt_deduplicates_identical_duplicate_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = (
        "Source: https://example.com/page.md\n"
        "# Title\n\nSame content.\n"
        "Source: https://example.com/page.md\n"
        "# Title\n\nSame content.\n"
    )
    import logging

    with caplog.at_level(logging.WARNING, logger="synd.builder.llms_full"):
        pages = split_llms_full_txt(text)
    assert len(pages) == 1
    assert not caplog.records


def test_split_llms_full_txt_warns_on_duplicate_url_with_differing_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = (
        "Source: https://example.com/page.md\n"
        "# First Version\n\nOriginal content.\n"
        "Source: https://example.com/page.md\n"
        "# Second Version\n\nDifferent content.\n"
    )
    import logging

    with caplog.at_level(logging.WARNING, logger="synd.builder.llms_full"):
        pages = split_llms_full_txt(text)
    assert len(pages) == 1
    assert "Second Version" in pages[0].content
    assert any("example.com/page.md" in r.message for r in caplog.records)


# --- fetch_llms_full_pages ---


def test_fetch_llms_full_pages_calls_fetch_text_and_splits() -> None:
    with patch("synd.builder.llms_full.fetch_text", return_value=_SAMPLE_LLMS_FULL_TXT):
        pages = fetch_llms_full_pages("https://docs.example.com/llms-full.txt")
    assert len(pages) == 3
    assert pages[0].url == "https://docs.example.com/intro.md"


def test_fetch_llms_full_pages_raises_fetch_error_on_failure() -> None:
    with patch(
        "synd.builder.llms_full.fetch_text",
        side_effect=FetchError("HTTP 404 fetching llms-full.txt"),
    ):
        with pytest.raises(FetchError, match="HTTP 404"):
            fetch_llms_full_pages("https://docs.example.com/llms-full.txt")


# --- fetch_pages ---


def test_fetch_pages_calls_fetch_page_for_each_entry() -> None:
    index_text = (
        "- [A](https://docs.example.com/a.md)\n- [B](https://docs.example.com/b.md)\n"
    )

    with (
        patch("synd.builder.llms_full.fetch_text", return_value=index_text),
        patch(
            "synd.builder.llms_full.fetch_page",
            side_effect=lambda url, **kw: f"# Content from {url}",
        ),
    ):
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

    def _fake_page(url: str, *, rate_limit_sleep: float = 0.0) -> str:
        if "bad" in url:
            raise FetchError("HTTP 404 fetching bad.md")
        return "# Good content"

    with (
        patch("synd.builder.llms_full.fetch_text", return_value=index_text),
        patch("synd.builder.llms_full.fetch_page", side_effect=_fake_page),
    ):
        results = fetch_pages(
            "https://docs.example.com/index.txt", rate_limit_sleep=0.0
        )

    assert len(results) == 1
    assert results[0][0] == "https://docs.example.com/good.md"


def test_fetch_pages_raises_fetch_error_when_index_fails() -> None:
    with patch(
        "synd.builder.llms_full.fetch_text",
        side_effect=FetchError("HTTP 404 fetching index"),
    ):
        with pytest.raises(FetchError, match="HTTP 404"):
            fetch_pages("https://docs.example.com/index.txt")
