#!/usr/bin/env python3
"""Validate chunk size distributions against real production llms-full.txt sources.

Fetches live docs from one or more llms-full.txt URLs, builds .ctx packs using
the public build_pack_from_url() API, then reports per-source chunk size stats.

Usage:
    .venv/bin/python scripts/validate_chunk_sizes.py
    .venv/bin/python scripts/validate_chunk_sizes.py --max-chunk-tokens 500
    .venv/bin/python scripts/validate_chunk_sizes.py \\
        --url https://modelcontextprotocol.io/llms-full.txt \\
        --url https://gofastmcp.com/llms-full.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from synd.builder.build import build_pack_from_url  # noqa: E402
from synd.builder.chunking import _DEFAULT_MAX_CHUNK_TOKENS, _DEFAULT_MIN_CHUNK_TOKENS  # noqa: E402

_DEFAULT_URLS = [
    "https://modelcontextprotocol.io/llms-full.txt",
    "https://gofastmcp.com/llms-full.txt",
]

_DEFAULT_ABORT_ABOVE = 10_000


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * pct / 100)
    return sorted_v[min(idx, len(sorted_v) - 1)]


def _label(url: str) -> str:
    host = urlparse(url).netloc
    return host or url


def _validate_url(
    url: str,
    out_dir: Path,
    max_chunk_tokens: int,
    min_chunk_tokens: int,
    warn_chunk_tokens: int,
    abort_above: int,
) -> dict:
    label = _label(url)
    pkg = label.replace(".", "-").replace("/", "-")
    print(f"\nFetching {url} ...", flush=True)
    ctx_path, oversized = build_pack_from_url(
        package=pkg,
        version="validate",
        source_url=url,
        output=out_dir,
        max_chunk_tokens=max_chunk_tokens,
        min_chunk_tokens=min_chunk_tokens,
        warn_chunk_tokens=warn_chunk_tokens,
    )
    token_counts: list[int] = []
    with zipfile.ZipFile(ctx_path) as zf:
        for line in zf.read("chunks.jsonl").decode().splitlines():
            if line.strip():
                rec = json.loads(line)
                token_counts.append(rec.get("token_count") or 0)

    total = len(token_counts)
    max_t = max(token_counts) if token_counts else 0
    p95 = _percentile(token_counts, 95)
    p99 = _percentile(token_counts, 99)
    over_warn = sum(1 for t in token_counts if t > warn_chunk_tokens)
    over_2k = sum(1 for t in token_counts if t > 2000)

    aborted = max_t > abort_above

    return {
        "source": label,
        "total": total,
        "max": max_t,
        "p95": p95,
        "p99": p99,
        "over_warn": over_warn,
        "over_2k": over_2k,
        "aborted": aborted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="llms-full.txt URL to validate. Repeatable. Defaults to MCP + FastMCP.",
    )
    parser.add_argument(
        "--max-chunk-tokens",
        type=int,
        default=_DEFAULT_MAX_CHUNK_TOKENS,
        help=f"Max tokens per chunk (default: {_DEFAULT_MAX_CHUNK_TOKENS})",
    )
    parser.add_argument(
        "--min-chunk-tokens",
        type=int,
        default=_DEFAULT_MIN_CHUNK_TOKENS,
        help=f"Min tokens to emit a chunk (default: {_DEFAULT_MIN_CHUNK_TOKENS})",
    )
    parser.add_argument(
        "--warn-chunk-tokens",
        type=int,
        default=None,
        help="Warn threshold (default: 2× --max-chunk-tokens)",
    )
    parser.add_argument(
        "--abort-above",
        type=int,
        default=_DEFAULT_ABORT_ABOVE,
        help=f"Exit non-zero if any chunk exceeds this (default: {_DEFAULT_ABORT_ABOVE})",
    )
    args = parser.parse_args()

    urls = args.urls or _DEFAULT_URLS
    warn = args.warn_chunk_tokens if args.warn_chunk_tokens is not None else 2 * args.max_chunk_tokens

    results = []
    with tempfile.TemporaryDirectory(prefix="synd-validate-") as tmp:
        out_dir = Path(tmp)
        for url in urls:
            try:
                r = _validate_url(
                    url=url,
                    out_dir=out_dir,
                    max_chunk_tokens=args.max_chunk_tokens,
                    min_chunk_tokens=args.min_chunk_tokens,
                    warn_chunk_tokens=warn,
                    abort_above=args.abort_above,
                )
                results.append(r)
            except Exception as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)
                results.append({"source": _label(url), "error": str(exc)})

    # Print summary table
    col_w = 36
    print(f"\n{'Source':<{col_w}} {'Chunks':>7} {'Max':>6} {'P95':>5} {'P99':>5} {f'>warn({warn}t)':>12} {'>2000t':>7}")
    print("-" * (col_w + 7 + 6 + 5 + 5 + 13 + 8))
    any_aborted = False
    for r in results:
        if "error" in r:
            print(f"{r['source']:<{col_w}} ERROR: {r['error']}")
            continue
        flag = " [ABORT]" if r["aborted"] else ""
        print(
            f"{r['source']:<{col_w}} {r['total']:>7,} {r['max']:>6,} {r['p95']:>5,} {r['p99']:>5,}"
            f" {r['over_warn']:>12,} {r['over_2k']:>7,}{flag}"
        )
        if r["aborted"]:
            any_aborted = True

    print(f"\nSettings: max_chunk_tokens={args.max_chunk_tokens}, min_chunk_tokens={args.min_chunk_tokens}, warn_chunk_tokens={warn}")

    if any_aborted:
        print(f"\nABORT: one or more sources produced chunks > {args.abort_above:,} tokens.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
