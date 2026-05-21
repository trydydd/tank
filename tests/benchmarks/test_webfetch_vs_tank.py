"""WebFetch vs Tank token comparison benchmark.

Simulates two documentation retrieval strategies for the same query:

  1. WebFetch   — the full source page lands in context as-is
  2. Tank full  — query-docs with detail='full', no prior summary step (agentless)
  3. Tank 2-step — summary scan first, then full content for ALL matched chunks

⚠️  The two-step approach here is AGENTLESS: all matched chunk IDs are
    fetched unconditionally after the summary scan. A real agent would read
    the summaries and fetch only the relevant chunks, reducing token cost
    further. That selective path is not yet benchmarked.

Source fixture: tests/benchmarks/fixtures/fastmcp-running-server.md
  Original URL: https://gofastmcp.com/deployment/running-server
  Fetched:      2026-05-21

Natural language query: "how do I configure a stdio implementation in fastmcp"
FTS5 query:             "stdio transport run"
  (FTS5 requires terms present in the document; the natural language
  version matched 0 results because "configure" and "implementation"
  do not appear in the source page.)

Run:
    pytest tests/benchmarks/test_webfetch_vs_tank.py --benchmark -v -s

Results are written to tests/benchmarks/results/webfetch_vs_tank_latest.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import tank
from tank.builder.build import build_pack
from tank.storage.db import Database
from tank.storage.models import Pack
from tank.server import query_docs as _query_docs

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"

FIXTURE_FILE = FIXTURE_DIR / "fastmcp-running-server.md"
SOURCE_URL = "https://gofastmcp.com/deployment/running-server"

NATURAL_LANGUAGE_QUERY = "how do I configure a stdio implementation in fastmcp"
FTS5_QUERY = "stdio transport run"


def _count_tokens(text: str) -> int:
    return len(text) // 4


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bench_db(tmp_path_factory: pytest.TempPathFactory) -> Database:
    """Build a Tank pack from the fixture file and pull it into a temp DB."""
    tmp = tmp_path_factory.mktemp("webfetch_bench")
    source_dir = tmp / "source"
    source_dir.mkdir()
    shutil.copy(FIXTURE_FILE, source_dir / FIXTURE_FILE.name)

    ctx_path = build_pack(
        package="fastmcp",
        version="3.0.0",
        source=source_dir,
        output=tmp,
        lifecycle="approved",
        doc_version_status="stable",
    )

    db_path = tmp / ".tank" / "index.db"
    db = Database(db_path)
    db.create_schema()

    import zipfile
    import json as _json
    from tank.storage.models import Chunk, Page

    with zipfile.ZipFile(ctx_path) as zf:
        manifest = _json.loads(zf.read("manifest.json"))
        pages_data = _json.loads(zf.read("pages.json"))
        chunks_data = [
            _json.loads(line)
            for line in zf.read("chunks.jsonl").decode().splitlines()
            if line.strip()
        ]

    pack = Pack(
        name=manifest["package"],
        version=manifest["version"],
        lifecycle_state=manifest["lifecycle_state"],
        doc_version_status=manifest["doc_version_status"],
        indexed_at=datetime.now(timezone.utc).isoformat(),
        pack_digest=manifest["pack_digest"],
        normalized_content_hash=manifest["normalized_content_hash"],
        source_url=manifest.get("source_url", ""),
        source_commit=manifest.get("source_commit"),
        owner=manifest.get("owner"),
        policy_profile=manifest.get("policy_profile"),
    )

    pages = [
        Page(
            id=p["id"],
            package=manifest["package"],
            version=manifest["version"],
            url=p["url"],
            title=p.get("title"),
            content_hash=p.get("content_hash"),
        )
        for p in pages_data
    ]

    chunks = [
        Chunk(
            id=c["id"],
            package=manifest["package"],
            version=manifest["version"],
            page_id=c.get("page_id"),
            heading_path=c.get("heading_path"),
            summary=c.get("summary"),
            content=c["content"],
            token_count=c.get("token_count"),
            source_url=c.get("source_url"),
            source_commit=c.get("source_commit"),
            content_hash=c.get("content_hash"),
        )
        for c in chunks_data
    ]

    db.import_pack(pack, pages, chunks)
    return db


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_webfetch_vs_tank(bench_db: Database) -> None:
    # ------------------------------------------------------------------
    # 1. WebFetch baseline — full page, no filtering
    # ------------------------------------------------------------------
    raw_page = FIXTURE_FILE.read_text(encoding="utf-8")
    webfetch_chars = len(raw_page)
    webfetch_tokens = _count_tokens(raw_page)

    # ------------------------------------------------------------------
    # 2. Tank single-step full (agentless — no prior summary scan)
    # ------------------------------------------------------------------
    full_result = _query_docs(
        bench_db,
        query=FTS5_QUERY,
        packages=["fastmcp"],
        detail="full",
        limit=10,
    )
    full_hits = full_result.get("results", [])
    full_tokens = sum(_count_tokens(r.get("content") or "") for r in full_hits)
    full_chunks_returned = len(full_hits)

    # ------------------------------------------------------------------
    # 3. Tank two-step (agentless — ALL matched chunks fetched, no agent
    #    selection after reading summaries)
    # ------------------------------------------------------------------
    summary_result = _query_docs(
        bench_db,
        query=FTS5_QUERY,
        packages=["fastmcp"],
        detail="summary",
        limit=20,
    )
    summary_hits = summary_result.get("results", [])
    summary_tokens = sum(_count_tokens(r.get("summary") or "") for r in summary_hits)

    matched_ids = [r["chunk_id"] for r in summary_hits]
    fetch_result = _query_docs(bench_db, query="", chunk_ids=matched_ids, detail="full")
    fetch_hits = fetch_result.get("results", [])
    fetch_tokens = sum(_count_tokens(r.get("content") or "") for r in fetch_hits)

    two_step_total = summary_tokens + fetch_tokens

    # ------------------------------------------------------------------
    # Per-chunk breakdown for two-step
    # ------------------------------------------------------------------
    chunk_breakdown = []
    for r in fetch_hits:
        content = r.get("content") or ""
        summary = r.get("summary") or ""
        chunk_breakdown.append(
            {
                "chunk_id": r["chunk_id"],
                "heading_path": r.get("heading_path"),
                "summary": summary,
                "content_chars": len(content),
                "content_tokens": _count_tokens(content),
            }
        )

    # ------------------------------------------------------------------
    # Results payload
    # ------------------------------------------------------------------
    results_payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "tank_version": tank.__version__,
        "token_counter": "len_div_4",
        "source_url": SOURCE_URL,
        "natural_language_query": NATURAL_LANGUAGE_QUERY,
        "fts5_query": FTS5_QUERY,
        "note": (
            "Two-step approach is AGENTLESS: all matched chunk IDs are fetched "
            "unconditionally. A real agent selecting only relevant chunks after "
            "reading summaries would reduce token cost further."
        ),
        "webfetch": {
            "chars": webfetch_chars,
            "tokens": webfetch_tokens,
        },
        "tank_single_step_full": {
            "chunks_returned": full_chunks_returned,
            "tokens": full_tokens,
            "pct_of_webfetch": round(100 * full_tokens / webfetch_tokens)
            if webfetch_tokens
            else 0,
            "tokens_saved": webfetch_tokens - full_tokens,
            "pct_saved": round(100 * (webfetch_tokens - full_tokens) / webfetch_tokens)
            if webfetch_tokens
            else 0,
        },
        "tank_two_step_agentless": {
            "step1_summary_tokens": summary_tokens,
            "step2_full_tokens": fetch_tokens,
            "total_tokens": two_step_total,
            "pct_of_webfetch": round(100 * two_step_total / webfetch_tokens)
            if webfetch_tokens
            else 0,
            "tokens_saved": webfetch_tokens - two_step_total,
            "pct_saved": round(
                100 * (webfetch_tokens - two_step_total) / webfetch_tokens
            )
            if webfetch_tokens
            else 0,
            "chunk_breakdown": chunk_breakdown,
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "webfetch_vs_tank_latest.json"
    out_path.write_text(json.dumps(results_payload, indent=2))

    # ------------------------------------------------------------------
    # Console output
    # ------------------------------------------------------------------
    print("\n── WebFetch vs Tank Token Comparison ──────────────────────────")
    print(f"  git commit   : {results_payload['git_commit']}")
    print(f"  tank version : {results_payload['tank_version']}")
    print(f"  source       : {SOURCE_URL}")
    print(f"  query (NL)   : {NATURAL_LANGUAGE_QUERY}")
    print(f"  query (FTS5) : {FTS5_QUERY}")
    print()
    print(f"  {'Approach':<35} {'tokens':>7}  {'vs WebFetch':>11}  {'saved':>7}")
    print(f"  {'-' * 35} {'-' * 7}  {'-' * 11}  {'-' * 7}")
    print(
        f"  {'WebFetch (full page)':<35} {webfetch_tokens:>7}  {'100%':>11}  {'—':>7}"
    )
    pct = results_payload["tank_single_step_full"]["pct_of_webfetch"]
    saved = results_payload["tank_single_step_full"]["pct_saved"]
    print(
        f"  {'Tank single-step full (agentless)':<35} {full_tokens:>7}"
        f"  {pct:>10}%  {saved:>6}%"
    )
    pct2 = results_payload["tank_two_step_agentless"]["pct_of_webfetch"]
    saved2 = results_payload["tank_two_step_agentless"]["pct_saved"]
    print(
        f"  {'Tank two-step (agentless)':<35} {two_step_total:>7}"
        f"  {pct2:>10}%  {saved2:>6}%"
    )
    print(f"    ↳ step 1 summary scan                {summary_tokens:>7}")
    print(
        f"    ↳ step 2 full fetch ({len(fetch_hits)} chunks)        {fetch_tokens:>7}"
    )
    print()
    print("  Per-chunk breakdown (step 2):")
    print(f"    {'chunk':>5}  {'tokens':>7}  summary")
    for c in chunk_breakdown:
        summary_short = (c["summary"] or "")[:60]
        print(f"    {c['chunk_id']:>5}  {c['content_tokens']:>7}  {summary_short}")
    print()
    print("  ⚠️  Two-step is AGENTLESS: all matched chunks fetched unconditionally.")
    print("     A real agent selecting only relevant chunks after reading summaries")
    print("     would reduce token cost further. That path is not yet benchmarked.")
    print(f"\n  Results written to {out_path}")
    print("────────────────────────────────────────────────────────────────\n")
