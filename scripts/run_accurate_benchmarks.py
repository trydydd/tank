"""Run the FTS5 query latency benchmark with high-precision settings.

Loads 59 packs once, runs each query with --reps samples (default 2500 =
50× the test default of 50), computes true percentiles from all samples,
and writes tests/benchmarks/results/latency.json.

Only the final results table is printed; DB-loading progress is suppressed.

Usage:
    python scripts/run_accurate_benchmarks.py [--reps N]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PACKS_DIR = REPO_ROOT / "tests" / "benchmarks" / "fixtures" / "packs"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"

_QUERIES = [
    ("single_common_term", "install", 10),
    ("multi_term", "authentication token", 10),
    ("technical_specific", "webhook endpoint", 10),
    ("rare_term", "sigstore", 10),
    ("high_limit", "configuration", 20),
]


def _load_db(packs: list[Path]) -> object:
    from synd.builder.manifest import load_manifest
    from synd.storage.db import Database
    from synd.storage.models import Chunk, Pack, Page

    tmp = tempfile.mkdtemp()
    db = Database(Path(tmp) / "bench.db")
    db.create_schema()

    for ctx_path in packs:
        manifest = load_manifest(ctx_path)
        pack = Pack(
            name=str(manifest["package"]),
            version=str(manifest["version"]),
            lifecycle_state=str(manifest["lifecycle_state"]),
            doc_version_status=str(manifest.get("doc_version_status", "unknown")),
            indexed_at="2025-01-01T00:00:00Z",
            policy_profile=str(manifest.get("policy_profile", "")),
            pack_digest=str(manifest["pack_digest"]),
            normalized_content_hash=str(manifest["normalized_content_hash"]),
            source_url=str(manifest.get("source_url", "")),
            source_commit=str(manifest.get("source_commit", "")),
            owner=str(manifest.get("owner", "")),
            pack_source=str(ctx_path),
        )
        with zipfile.ZipFile(ctx_path, "r") as zf:
            pages_data = json.loads(zf.read("pages.json"))
            chunks_data = zf.read("chunks.jsonl").decode("utf-8")

        pages = [
            Page(
                id=p["id"],
                package=p["package"],
                version=p["version"],
                url=p["url"],
                title=p.get("title"),
                content_hash=p.get("content_hash"),
            )
            for p in pages_data
        ]
        chunks = []
        for line in chunks_data.strip().split("\n"):
            if not line:
                continue
            c = json.loads(line)
            chunks.append(
                Chunk(
                    id=c["id"],
                    package=pack.name,
                    version=pack.version,
                    content=c["content"],
                    page_id=c.get("page_id"),
                    heading_path=c.get("heading_path"),
                    summary=c.get("summary"),
                    token_count=c.get("token_count"),
                    source_url=c.get("source_url"),
                    source_commit=c.get("source_commit"),
                    content_hash=c.get("content_hash"),
                )
            )
        db.import_pack(pack, pages, chunks)

    return db


def _measure(db: object, query: str, limit: int, reps: int) -> dict[str, float]:
    from synd.search.fts import search

    times_ms: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        search(db, query, limit=limit)
        times_ms.append((time.perf_counter() - t0) * 1000)
    times_ms.sort()
    p95_idx = max(0, math.ceil(len(times_ms) * 0.95) - 1)
    return {
        "p50_ms": round(times_ms[len(times_ms) // 2], 3),
        "p95_ms": round(times_ms[p95_idx], 3),
        "min_ms": round(times_ms[0], 3),
        "max_ms": round(times_ms[-1], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reps",
        type=int,
        default=2500,
        help="Timing samples per query (default: 2500)",
    )
    args = parser.parse_args()

    packs = sorted(PACKS_DIR.glob("*.ctx")) if PACKS_DIR.exists() else []
    if not packs:
        print(f"error: no .ctx packs in {PACKS_DIR}", file=sys.stderr)
        print("Run: python scripts/build_benchmark_packs.py", file=sys.stderr)
        sys.exit(1)

    db = _load_db(packs)

    results: dict[str, object] = {
        "pack_count": len(packs),
        "reps_per_query": args.reps,
        "queries": {},
    }
    query_stats: dict[str, dict[str, float]] = {}
    for label, query, limit in _QUERIES:
        stats = _measure(db, query, limit, args.reps)
        results["queries"][label] = {"query": query, "limit": limit, **stats}  # type: ignore[index]
        query_stats[label] = stats

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "latency.json"
    out.write_text(json.dumps(results, indent=2) + "\n")

    print(f"\n{len(packs)} packs  |  {args.reps} reps/query")
    print(f"{'Query':<30} {'p50 ms':>8} {'p95 ms':>8} {'min ms':>8} {'max ms':>8}")
    print("-" * 66)
    for label, _query, _limit in _QUERIES:
        s = query_stats[label]
        print(
            f"{label:<30} {s['p50_ms']:>8.3f} {s['p95_ms']:>8.3f}"
            f" {s['min_ms']:>8.3f} {s['max_ms']:>8.3f}"
        )
    print(f"\nWrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
