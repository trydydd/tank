"""FTS5 query latency benchmark against a real documentation index.

Uses 59 packs (100,116 chunks) built from real llms-full.txt sources via
https://directory.llmstxt.cloud/. This gives a realistic vocabulary distribution
and document frequency profile, unlike a synthetic corpus.

Pre-built packs live in tests/benchmarks/fixtures/packs/ and are loaded into
a fresh in-memory-equivalent temp DB at fixture setup time. If the packs
directory is empty or missing, the test is skipped with setup instructions.

Run:
    pytest tests/benchmarks/test_query_latency.py -v -s

The P95 assertion (< 100 ms) is a safety-net regression guard. Actual observed
latency on commodity hardware is in the low single digits of milliseconds for
specific technical terms; common high-frequency terms approach ~10 ms.
"""

from __future__ import annotations

import json
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from synd.search.fts import search
from synd.storage.db import Database
from synd.storage.models import Chunk, Pack, Page

RESULTS_DIR = Path(__file__).parent / "results"
PACKS_DIR = Path(__file__).parent / "fixtures" / "packs"
REPS = 50

# Representative query types spanning different term frequencies and domains
_QUERIES = [
    ("single_common_term", "install", 10),
    ("multi_term", "authentication token", 10),
    ("technical_specific", "webhook endpoint", 10),
    ("rare_term", "sigstore", 10),
    ("high_limit", "configuration", 20),
]


def _load_pack_into_db(ctx_path: Path, db: Database) -> int:
    """Import a .ctx pack into db. Returns number of chunks imported."""
    from synd.builder.manifest import load_manifest

    manifest = load_manifest(ctx_path)
    pack = Pack(
        name=str(manifest["package"]),
        version=str(manifest["version"]),
        lifecycle_state=str(manifest["lifecycle_state"]),
        doc_version_status=str(manifest.get("doc_version_status", "unknown")),
        indexed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    return len(chunks)


@pytest.fixture(scope="module")
def real_index_db() -> Database:
    packs = sorted(PACKS_DIR.glob("*.ctx")) if PACKS_DIR.exists() else []
    if not packs:
        pytest.skip(
            f"No .ctx packs found in {PACKS_DIR}. "
            "Run scripts/build_benchmark_packs.py to fetch real documentation data."
        )

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "bench.db")
        db.create_schema()
        total = 0
        for pack_path in packs:
            total += _load_pack_into_db(pack_path, db)
        print(f"\nLoaded {total:,} chunks from {len(packs)} packs into benchmark index")
        yield db


def _measure(db: Database, query: str, limit: int) -> dict[str, float]:
    times_ms: list[float] = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        search(db, query, limit=limit)
        times_ms.append((time.perf_counter() - t0) * 1000)
    times_ms.sort()
    p95_idx = max(0, int(len(times_ms) * 0.95) - 1)
    return {
        "p50_ms": round(times_ms[len(times_ms) // 2], 3),
        "p95_ms": round(times_ms[p95_idx], 3),
        "min_ms": round(times_ms[0], 3),
        "max_ms": round(times_ms[-1], 3),
    }


def test_query_latency(real_index_db: Database) -> None:
    results: dict[str, object] = {
        "pack_count": len(sorted(PACKS_DIR.glob("*.ctx"))),
        "reps_per_query": REPS,
        "queries": {},
    }

    print(f"\n{'Query':<30} {'P50 ms':>8} {'P95 ms':>8} {'min ms':>8} {'max ms':>8}")
    print("-" * 70)

    for label, query, limit in _QUERIES:
        stats = _measure(real_index_db, query, limit)
        results["queries"][label] = {"query": query, "limit": limit, **stats}  # type: ignore[index]
        print(
            f"{label:<30} {stats['p50_ms']:>8.3f} {stats['p95_ms']:>8.3f}"
            f" {stats['min_ms']:>8.3f} {stats['max_ms']:>8.3f}"
        )
        assert stats["p95_ms"] < 100, (
            f"P95 latency for '{query}' is {stats['p95_ms']:.1f} ms — "
            "FTS5 performance regression (threshold: 100 ms)"
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "latency.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nResults written to {RESULTS_DIR / 'latency.json'}")
