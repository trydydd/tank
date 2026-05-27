#!/usr/bin/env python3
"""Inspect a generated Markdown file for MDX/HTML pollution.

Exits 0 if the file is clean, 1 if issues are found.

Usage:
    python3 inspect_markdown.py fastmcp.md
    python3 inspect_markdown.py fastmcp.md --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Each check is (label, pattern). Patterns are matched against lines *outside*
# code fences, so false positives from code samples are not a concern.
CHECKS: list[tuple[str, re.Pattern[str]]] = [
    ("Dirty code fence (extra info-string attrs)",   re.compile(r"^```[a-z][^\s`]*[ \t]")),
    ("MDX JSX component tag",                        re.compile(r"^<[A-Z][a-zA-Z]+")),
    ("Stray HTML block tag",                         re.compile(r"^<(div|span|p|section|aside|nav|header|footer|script|style|iframe|html|head|body)\b", re.I)),
    ("Bare JSX / curly expression",                  re.compile(r"^\{[^`]")),
    ("MDX import / export statement",                re.compile(r"^(import|export)\s+(default\s+)?[{A-Z*]")),
    ("Leftover MDX theme attribute",                 re.compile(r"theme=\{")),
    ("Unescaped HTML entity",                        re.compile(r"&[a-z]{2,8};|&#[0-9]+;")),
    ("Inline HTML self-closing tag (<br/>, <hr/>)",  re.compile(r"<(br|hr)\s*/?>")),
]


def _mask_code_fences(text: str) -> str:
    """Replace the *contents* of fenced code blocks with a placeholder so
    checks don't fire on code that legitimately contains HTML or JSX."""
    return re.sub(r"```[\s\S]*?```", "```FENCED```", text)


def inspect(path: Path) -> list[tuple[int, str, str]]:
    """Return a list of (line_number, label, line) for every issue found."""
    text = path.read_text(encoding="utf-8")
    masked = _mask_code_fences(text)
    issues: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(masked.splitlines(), 1):
        for label, pat in CHECKS:
            if pat.search(line):
                issues.append((lineno, label, line))
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="Markdown file to inspect")
    ap.add_argument("-v", "--verbose", action="store_true", help="Show every issue line")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    issues = inspect(path)

    if not issues:
        print(f"✓  {path}  —  no issues found")
        return 0

    # Summary by type
    by_type: dict[str, int] = {}
    for _, label, _ in issues:
        by_type[label] = by_type.get(label, 0) + 1

    print(f"✗  {path}  —  {len(issues)} issue(s) found\n")
    for label, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {count:4d}  {label}")

    if args.verbose and issues:
        print()
        for lineno, label, line in issues:
            print(f"  [{lineno:5d}]  {label}")
            print(f"           {line[:120]}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
