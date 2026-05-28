from __future__ import annotations

from synd.builder.url_filter import (
    DEFAULT_NOISE_URL_PATTERNS,
    filter_page_urls,
    is_noise_url,
)


class TestIsNoiseUrl:
    def test_exact_segment_match(self) -> None:
        assert is_noise_url(
            "https://docs.example.com/changelog", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_segment_in_path(self) -> None:
        assert is_noise_url(
            "https://docs.example.com/docs/changelog", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_segment_with_subpath(self) -> None:
        assert is_noise_url(
            "https://docs.example.com/releases/v2", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_no_false_positive_on_partial_match(self) -> None:
        # "configuration-updates" must NOT match "updates"
        assert not is_noise_url(
            "https://docs.example.com/configuration-updates", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_no_false_positive_on_unrelated_path(self) -> None:
        assert not is_noise_url(
            "https://docs.example.com/docs/api/auth", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_case_insensitive(self) -> None:
        assert is_noise_url(
            "https://docs.example.com/Changelog", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_updates_segment(self) -> None:
        assert is_noise_url(
            "https://docs.example.com/updates", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_whats_new_segment(self) -> None:
        assert is_noise_url(
            "https://docs.example.com/whats-new", DEFAULT_NOISE_URL_PATTERNS
        )

    def test_empty_patterns_always_false(self) -> None:
        assert not is_noise_url("https://docs.example.com/changelog", ())

    def test_custom_pattern(self) -> None:
        assert is_noise_url("https://docs.example.com/blog", ("blog",))

    def test_root_path_not_noise(self) -> None:
        assert not is_noise_url("https://docs.example.com/", DEFAULT_NOISE_URL_PATTERNS)


class TestFilterPageUrls:
    def test_filters_noise_urls(self) -> None:
        pairs = [
            ("https://docs.example.com/api/auth", "auth content"),
            ("https://docs.example.com/changelog", "v1.0 released"),
            ("https://docs.example.com/guide", "guide content"),
            ("https://docs.example.com/releases/v2", "v2 release notes"),
        ]
        kept, excluded = filter_page_urls(pairs, DEFAULT_NOISE_URL_PATTERNS)
        kept_urls = [u for u, _ in kept]
        assert "https://docs.example.com/api/auth" in kept_urls
        assert "https://docs.example.com/guide" in kept_urls
        assert "https://docs.example.com/changelog" in excluded
        assert "https://docs.example.com/releases/v2" in excluded

    def test_empty_patterns_keeps_all(self) -> None:
        pairs = [
            ("https://docs.example.com/changelog", "content"),
            ("https://docs.example.com/updates", "content"),
        ]
        kept, excluded = filter_page_urls(pairs, ())
        assert len(kept) == 2
        assert excluded == []

    def test_all_kept_when_no_matches(self) -> None:
        pairs = [
            ("https://docs.example.com/api", "api content"),
            ("https://docs.example.com/guide", "guide content"),
        ]
        kept, excluded = filter_page_urls(pairs, DEFAULT_NOISE_URL_PATTERNS)
        assert len(kept) == 2
        assert excluded == []

    def test_empty_input(self) -> None:
        kept, excluded = filter_page_urls([], DEFAULT_NOISE_URL_PATTERNS)
        assert kept == []
        assert excluded == []

    def test_content_preserved_in_kept(self) -> None:
        pairs = [("https://docs.example.com/api", "my content")]
        kept, _ = filter_page_urls(pairs, DEFAULT_NOISE_URL_PATTERNS)
        assert kept[0][1] == "my content"

    def test_all_noise_returns_empty_kept(self) -> None:
        pairs = [
            ("https://docs.example.com/changelog", "c1"),
            ("https://docs.example.com/releases", "c2"),
        ]
        kept, excluded = filter_page_urls(pairs, DEFAULT_NOISE_URL_PATTERNS)
        assert kept == []
        assert len(excluded) == 2
