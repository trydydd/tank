"""Build the real documentation packs used by the FTS5 latency benchmark.

Fetches llms-full.txt from 59 real documentation sites (sourced from
https://directory.llmstxt.cloud/) and builds .ctx packs into
tests/benchmarks/fixtures/packs/. Already-built packs are skipped.

Target: ≥100,000 chunks across all packs.

Run:
    python scripts/build_benchmark_packs.py

Requirements: synd CLI available in PATH or .venv/bin/synd.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

OUTDIR = Path("tests/benchmarks/fixtures/packs")
TARGET_CHUNKS = 100_000
VERSION = "2025-05-29"

# Sites ordered largest-first (by Source: page count in their llms-full.txt).
# All confirmed to use the Mintlify Source: boundary format.
SOURCES: list[tuple[str, str]] = [
    ("crewai", "https://docs.crewai.com/llms-full.txt"),
    ("coinbase", "https://docs.cdp.coinbase.com/llms-full.txt"),
    ("infisical", "https://infisical.com/docs/llms-full.txt"),
    ("flowx", "https://docs.flowx.ai/llms-full.txt"),
    ("galileo", "https://docs.galileo.ai/llms-full.txt"),
    ("axiom", "https://axiom.co/docs/llms-full.txt"),
    ("upstash", "https://upstash.com/docs/llms-full.txt"),
    ("methodfi", "https://docs.methodfi.com/llms-full.txt"),
    ("pinecone", "https://docs.pinecone.io/llms-full.txt"),
    ("mangopay", "https://docs.mangopay.com/llms-full.txt"),
    ("unstructured", "https://docs.unstructured.io/llms-full.txt"),
    ("getlago", "https://getlago.com/docs/llms-full.txt"),
    ("fireworks", "https://docs.fireworks.ai/llms-full.txt"),
    ("conductor", "https://docs.conductor.is/llms-full.txt"),
    ("hyperline", "https://docs.hyperline.co/llms-full.txt"),
    ("aptible", "https://www.aptible.com/docs/llms-full.txt"),
    ("zapier", "https://docs.zapier.com/llms-full.txt"),
    ("writer", "https://dev.writer.com/llms-full.txt"),
    ("trigger", "https://trigger.dev/docs/llms-full.txt"),
    ("projectdiscovery", "https://docs.projectdiscovery.io/llms-full.txt"),
    ("resend", "https://resend.com/docs/llms-full.txt"),
    ("turso", "https://docs.turso.tech/llms-full.txt"),
    ("smartcar", "https://smartcar.com/docs/llms-full.txt"),
    ("dub", "https://dub.co/docs/llms-full.txt"),
    ("activepieces", "https://www.activepieces.com/docs/llms-full.txt"),
    ("squared", "https://docs.squared.ai/llms-full.txt"),
    ("loops", "https://loops.so/docs/llms-full.txt"),
    ("datafold", "https://docs.datafold.com/llms-full.txt"),
    ("stedi", "https://www.stedi.com/docs/llms-full.txt"),
    ("plain", "https://www.plain.com/docs/llms-full.txt"),
    ("mcp", "https://modelcontextprotocol.io/llms-full.txt"),
    ("perplexity", "https://docs.perplexity.ai/llms-full.txt"),
    ("finch", "https://developer.tryfinch.com/llms-full.txt"),
    ("embedchain", "https://docs.embedchain.ai/llms-full.txt"),
    ("openpipe", "https://docs.openpipe.ai/llms-full.txt"),
    ("ionq", "https://docs.ionq.com/llms-full.txt"),
    ("primev", "https://docs.primev.xyz/llms-full.txt"),
    ("pinata", "https://docs.pinata.cloud/llms-full.txt"),
    ("cobo", "https://www.cobo.com/developers/llms-full.txt"),
    ("meshconnect", "https://docs.meshconnect.com/llms-full.txt"),
    ("unifygtm", "https://docs.unifygtm.com/llms-full.txt"),
    ("ongoody", "https://developer.ongoody.com/llms-full.txt"),
    ("axle", "https://docs.axle.insure/llms-full.txt"),
    ("quill", "https://quill.co/docs/llms-full.txt"),
    ("fractalpay", "https://docs.fractalpay.com/llms-full.txt"),
    ("fabric", "https://developer.fabric.inc/llms-full.txt"),
    ("brightdata", "https://docs.brightdata.com/llms-full.txt"),
    ("speakeasy", "https://www.speakeasy.com/llms-full.txt"),
    ("cal", "https://cal.com/docs/llms-full.txt"),
    ("avacloud", "https://developers.avacloud.io/llms-full.txt"),
    ("augmentcode", "https://docs.augmentcode.com/llms-full.txt"),
    ("tavus", "https://docs.tavus.io/llms-full.txt"),
    ("chatling", "https://docs.chatling.ai/llms-full.txt"),
    ("dappier", "https://docs.dappier.com/llms-full.txt"),
    ("codecrafters", "https://docs.codecrafters.io/llms-full.txt"),
    ("chargeblast", "https://docs.chargeblast.com/llms-full.txt"),
    ("playai", "https://docs.play.ai/llms-full.txt"),
    ("envoyer", "https://docs.envoyer.io/llms-full.txt"),
    ("comfy", "https://docs.comfy.org/llms-full.txt"),
]


def _chunk_count(ctx_path: Path) -> int:
    try:
        with zipfile.ZipFile(ctx_path, "r") as zf:
            return zf.read("chunks.jsonl").count(b"\n")
    except Exception:
        return 0


def _find_synd() -> str:
    candidates = [".venv/bin/synd", "synd"]
    for c in candidates:
        try:
            subprocess.run([c, "--help"], capture_output=True)
            return c
        except FileNotFoundError:
            pass
    print("error: synd CLI not found. Run: pip install -e '.[all]'", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    synd = _find_synd()
    total = 0

    for name, url in SOURCES:
        pack_path = OUTDIR / f"{name}@{VERSION}.ctx"
        if pack_path.exists():
            count = _chunk_count(pack_path)
            total += count
            print(f"skip  {name:<20} {count:>6} chunks  cumulative: {total:,}")
        else:
            print(f"build {name:<20} {url}")
            result = subprocess.run(
                [
                    synd,
                    "build",
                    f"{name}@{VERSION}",
                    "--source",
                    url,
                    "--output",
                    str(OUTDIR),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and pack_path.exists():
                count = _chunk_count(pack_path)
                total += count
                print(f"  -> {count:,} chunks  cumulative: {total:,}")
            else:
                err = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
                print(f"  -> FAILED: {err}")

        if total >= TARGET_CHUNKS:
            print(f"\nTarget reached: {total:,} chunks from {name}")
            break

    built = len(list(OUTDIR.glob("*.ctx")))
    print(f"\nDone: {total:,} total chunks across {built} packs in {OUTDIR}")
    if total < TARGET_CHUNKS:
        print(f"WARNING: only {total:,} chunks built, target was {TARGET_CHUNKS:,}")
        print("Add more sources to SOURCES list above.")


if __name__ == "__main__":
    main()
