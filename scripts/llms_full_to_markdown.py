#!/usr/bin/env python3
"""Convert llms-full.txt content that includes MDX/HTML into plain Markdown."""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "nav",
    "main",
    "pre",
    "blockquote",
    "ul",
    "ol",
    "table",
    "tr",
    "tbody",
    "thead",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
}


class MarkdownExtractor(HTMLParser):
    """Extract readable text from HTML while keeping markdown-friendly structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._in_li = False

    def _newline(self) -> None:
        if not self._chunks or self._chunks[-1].endswith("\n"):
            return
        self._chunks.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._chunks.append("\n")
            return
        if tag == "li":
            self._newline()
            self._chunks.append("- ")
            self._in_li = True
            return
        if tag in BLOCK_TAGS:
            self._newline()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "li":
            self._in_li = False
            self._chunks.append("\n")
            return
        if tag in BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        # Collapse internal whitespace in plain HTML text.
        text = re.sub(r"\s+", " ", data)
        self._chunks.append(text)

    def text(self) -> str:
        merged = "".join(self._chunks)
        merged = re.sub(r"[ \t]+", " ", merged)
        merged = re.sub(r"\n{3,}", "\n\n", merged)
        return merged.strip() + "\n"


def strip_mdx(text: str) -> str:
    """Remove common MDX wrappers while preserving markdown content."""
    cleaned = text
    # Remove JSX/MDX import/export lines.
    cleaned = re.sub(r"^\s*(?:import|export)\s+.+?$", "", cleaned, flags=re.MULTILINE)
    # Remove self-closing JSX component lines.
    cleaned = re.sub(r"^\s*<([A-Z][\w.]*)\b[^>]*?/?>\s*$", "", cleaned, flags=re.MULTILINE)
    # Remove JSX expression wrappers but keep text literals where possible.
    cleaned = re.sub(r"\{`([^`]*)`\}", r"\1", cleaned)
    cleaned = re.sub(r"\{\s*" + '"([^"]*)"' + r"\s*\}", r"\1", cleaned)
    cleaned = re.sub(r"\{\s*'([^']*)'\s*\}", r"\1", cleaned)
    # Remove remaining simple expressions.
    cleaned = re.sub(r"\{[^{}\n]*\}", "", cleaned)
    return cleaned


def _extract_code_fences(text: str) -> tuple[str, list[str]]:
    fences: list[str] = []

    def _repl(match: re.Match[str]) -> str:
        fences.append(match.group(0))
        return f"@@CODE_FENCE_{len(fences) - 1}@@"

    masked = re.sub(r"```[\s\S]*?```", _repl, text)
    return masked, fences


def convert_to_markdown(raw_text: str) -> str:
    cleaned = strip_mdx(raw_text)
    cleaned, fences = _extract_code_fences(cleaned)

    parser = MarkdownExtractor()
    parser.feed(cleaned)
    parser.close()

    rendered = parser.text()
    for i, fence in enumerate(fences):
        rendered = rendered.replace(f"@@CODE_FENCE_{i}@@", f"\n{fence}\n")
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered


def read_input(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        request = Request(source, headers={"User-Agent": "Mozilla/5.0 tank-llms-full-converter"})
        with urlopen(request, timeout=30) as response:  # nosec: B310 (user-supplied URL by design)
            return response.read().decode("utf-8", errors="replace")
    return Path(source).read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="Path or URL to llms-full.txt")
    ap.add_argument("-o", "--output", help="Write Markdown output to this path")
    args = ap.parse_args()

    markdown = convert_to_markdown(read_input(args.source))

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
