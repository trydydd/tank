from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from synd.builder.fetch import fetch_page
from synd.errors import FetchError


def _mock_urlopen(body: str) -> MagicMock:
    """Build a context-manager mock that returns body bytes from .read()."""
    response = MagicMock()
    response.read.return_value = body.encode("utf-8")
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=response)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def test_fetch_page_md_url_routes_to_mdx_pipeline() -> None:
    body = "# Hello\n\n<Note>Some note.</Note>\n"
    with patch("synd.builder.fetch.urlopen", return_value=_mock_urlopen(body)):
        result = fetch_page("https://example.com/page.md")
    assert "Some note." in result
    assert "<Note>" not in result


def test_fetch_page_html_url_routes_to_html_pipeline() -> None:
    body = "<html><body><main><h1>Hello</h1><p>World</p></main></body></html>"
    with patch("synd.builder.fetch.urlopen", return_value=_mock_urlopen(body)):
        result = fetch_page("https://example.com/page.html")
    assert "Hello" in result
    assert "World" in result
    assert "<html>" not in result


def test_fetch_page_url_without_extension_routes_to_html_pipeline() -> None:
    body = "<html><body><main><p>Content here.</p></main></body></html>"
    with patch("synd.builder.fetch.urlopen", return_value=_mock_urlopen(body)):
        result = fetch_page("https://docs.example.com/guide")
    assert "Content here." in result
    assert "<html>" not in result


def test_fetch_page_raises_fetch_error_on_4xx() -> None:
    import http.client

    headers = http.client.HTTPMessage()
    with patch(
        "synd.builder.fetch.urlopen",
        side_effect=HTTPError(
            "https://example.com/page.md", 404, "Not Found", headers, None
        ),
    ):
        with pytest.raises(FetchError, match="HTTP 404"):
            fetch_page("https://example.com/page.md")


def test_fetch_page_raises_fetch_error_on_network_failure() -> None:
    with patch(
        "synd.builder.fetch.urlopen",
        side_effect=URLError("connection refused"),
    ):
        with pytest.raises(FetchError, match="Network error"):
            fetch_page("https://example.com/page.html")


def test_fetch_page_rate_limit_sleep_is_called() -> None:
    body = "# Title\n"
    with (
        patch("synd.builder.fetch.urlopen", return_value=_mock_urlopen(body)),
        patch("synd.builder.fetch.time") as mock_time,
    ):
        fetch_page("https://example.com/page.md", rate_limit_sleep=0.5)
    mock_time.sleep.assert_called_once_with(0.5)


def test_fetch_page_no_sleep_when_zero() -> None:
    body = "# Title\n"
    with (
        patch("synd.builder.fetch.urlopen", return_value=_mock_urlopen(body)),
        patch("synd.builder.fetch.time") as mock_time,
    ):
        fetch_page("https://example.com/page.md", rate_limit_sleep=0.0)
    mock_time.sleep.assert_not_called()
