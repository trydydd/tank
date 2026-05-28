from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# URL path segments that signal non-documentation noise pages.
# Matched case-insensitively against individual path segments so that
# "/docs/changelog" matches but "/docs/configuration-updates" does not.
DEFAULT_NOISE_URL_PATTERNS: tuple[str, ...] = (
    "changelog",
    "changelogs",
    "releases",
    "release-notes",
    "updates",
    "news",
    "history",
    "whats-new",
    "what-is-new",
)


def is_noise_url(url: str, patterns: tuple[str, ...]) -> bool:
    """Return True if any path segment of url matches a noise pattern.

    Matching is against individual path segments (split on '/'), case-insensitive,
    so the pattern "updates" matches ".../updates" and ".../updates/v2" but not
    ".../configuration-updates.md".
    """
    if not patterns:
        return False
    path = urlparse(url).path.lower().strip("/")
    segments = set(path.split("/"))
    lowered = {p.lower().strip("/") for p in patterns}
    return bool(segments & lowered)


def filter_page_urls(
    page_pairs: list[tuple[str, str]],
    patterns: tuple[str, ...] = DEFAULT_NOISE_URL_PATTERNS,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Split page_pairs into (kept, excluded_urls) based on noise patterns.

    Returns the kept pairs and a list of excluded URLs for logging.
    Pass patterns=() to disable all filtering.
    """
    if not patterns:
        return list(page_pairs), []

    kept: list[tuple[str, str]] = []
    excluded: list[str] = []

    for url, content in page_pairs:
        if is_noise_url(url, patterns):
            logger.debug("url_filter: excluded %s (matches noise pattern)", url)
            excluded.append(url)
        else:
            kept.append((url, content))

    return kept, excluded
