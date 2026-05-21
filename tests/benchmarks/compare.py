#!/usr/bin/env python3
"""Compare two Tank benchmark result files and report deltas.

Usage:
    # Plain text (terminal)
    python tests/benchmarks/compare.py baseline.json candidate.json

    # Markdown (GitHub comment)
    python tests/benchmarks/compare.py baseline.json candidate.json --markdown

    # Using committed release baselines
    python tests/benchmarks/compare.py \\
        tests/benchmarks/results/v0.1.0.json \\
        tests/benchmarks/results/latest.json

Exit codes:
    0  All metrics within thresholds (or only warnings)
    1  One or more thresholds exceeded
    2  Usage error or unreadable input file

Thresholds (from RELEASES.md):
    schema total tokens   > +20%  → WARN
    summary tokens/result > +15%  → WARN
    pd saving %           < 40%   → WARN
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_SCHEMA_TOKENS_WARN_PCT = 20.0
_SUMMARY_PER_RESULT_WARN_PCT = 15.0
_PD_SAVING_WARN_FLOOR = 40.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    return json.loads(p.read_text())


def _pct_delta(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return (after - before) / before * 100


def _pp_delta(before: float, after: float) -> float:
    return after - before


def _fmt_pct(v: float | None, precision: int = 1) -> str:
    if v is None:
        return "n/a"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{precision}f}%"


def _fmt_pp(v: float, precision: int = 1) -> str:
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{precision}f}pp"


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------


def compare(baseline: dict, candidate: dict) -> dict[str, Any]:
    """Return a structured comparison dict used by both formatters."""
    warnings: list[str] = []

    # Schema
    b_schema = baseline["schema"]["total_tokens"]
    c_schema = candidate["schema"]["total_tokens"]
    schema_delta = _pct_delta(b_schema, c_schema)
    schema_warn = schema_delta is not None and schema_delta > _SCHEMA_TOKENS_WARN_PCT
    if schema_warn:
        warnings.append(
            f"schema tokens +{schema_delta:.1f}% (threshold +{_SCHEMA_TOKENS_WARN_PCT}%)"
        )

    # Per-tool breakdown
    b_tools = {t["name"]: t["tokens"] for t in baseline["schema"]["tools"]}
    c_tools = {t["name"]: t["tokens"] for t in candidate["schema"]["tools"]}
    all_tools = sorted(set(b_tools) | set(c_tools))

    # Response sizes (tokens per result)
    response_rows = []
    summary_warns = []
    for key in (
        "summary_n5",
        "summary_n10",
        "summary_n20",
        "full_n5",
        "full_n10",
        "full_n20",
    ):
        b_tpr = baseline["responses"][key]["tokens_per_result"]
        c_tpr = candidate["responses"][key]["tokens_per_result"]
        delta = _pct_delta(b_tpr, c_tpr)
        is_summary = key.startswith("summary")
        warn = is_summary and delta is not None and delta > _SUMMARY_PER_RESULT_WARN_PCT
        if warn:
            summary_warns.append(key)
        response_rows.append(
            {
                "key": key,
                "before": b_tpr,
                "after": c_tpr,
                "delta_pct": delta,
                "warn": warn,
            }
        )
    if summary_warns:
        warnings.append(
            f"summary tokens/result exceeded +{_SUMMARY_PER_RESULT_WARN_PCT}% threshold: "
            + ", ".join(summary_warns)
        )

    # Progressive disclosure
    b_pd = baseline["progressive_disclosure"]
    c_pd = candidate["progressive_disclosure"]
    pd_saving_delta = _pp_delta(b_pd["saving_pct"], c_pd["saving_pct"])
    pd_warn = c_pd["saving_pct"] < _PD_SAVING_WARN_FLOOR
    if pd_warn:
        warnings.append(
            f"progressive disclosure saving {c_pd['saving_pct']:.1f}% "
            f"is below {_PD_SAVING_WARN_FLOOR}% floor"
        )

    return {
        "baseline_commit": baseline.get("git_commit", "unknown"),
        "baseline_version": baseline.get("tank_version", "unknown"),
        "candidate_commit": candidate.get("git_commit", "unknown"),
        "candidate_version": candidate.get("tank_version", "unknown"),
        "token_counter": candidate.get("token_counter", "len_div_4"),
        "schema": {
            "before": b_schema,
            "after": c_schema,
            "delta_pct": schema_delta,
            "warn": schema_warn,
            "pct_200k_before": baseline["schema"]["pct_of_200k_context"],
            "pct_200k_after": candidate["schema"]["pct_of_200k_context"],
            "tools": [
                {
                    "name": name,
                    "before": b_tools.get(name, 0),
                    "after": c_tools.get(name, 0),
                    "delta_pct": _pct_delta(b_tools.get(name, 0), c_tools.get(name, 0)),
                }
                for name in all_tools
            ],
        },
        "responses": response_rows,
        "progressive_disclosure": {
            "step1_before": b_pd["step1_summary_all_tokens"],
            "step1_after": c_pd["step1_summary_all_tokens"],
            "step1_delta": _pct_delta(
                b_pd["step1_summary_all_tokens"], c_pd["step1_summary_all_tokens"]
            ),
            "step2_before": b_pd["step2_full_top3_tokens"],
            "step2_after": c_pd["step2_full_top3_tokens"],
            "step2_delta": _pct_delta(
                b_pd["step2_full_top3_tokens"], c_pd["step2_full_top3_tokens"]
            ),
            "total_before": b_pd["total_tokens"],
            "total_after": c_pd["total_tokens"],
            "total_delta": _pct_delta(b_pd["total_tokens"], c_pd["total_tokens"]),
            "naive_before": b_pd["vs_naive_full_n20_tokens"],
            "naive_after": c_pd["vs_naive_full_n20_tokens"],
            "saving_before": b_pd["saving_pct"],
            "saving_after": c_pd["saving_pct"],
            "saving_delta_pp": pd_saving_delta,
            "warn": pd_warn,
        },
        "warnings": warnings,
        "passed": len(warnings) == 0,
    }


# ---------------------------------------------------------------------------
# Plain-text formatter
# ---------------------------------------------------------------------------

_STATUS_OK = "✓"
_STATUS_WARN = "⚠ WARN"
_STATUS_NONE = ""


def _status(warn: bool, has_delta: bool = True) -> str:
    if not has_delta:
        return _STATUS_NONE
    return _STATUS_WARN if warn else _STATUS_OK


def format_text(c: dict) -> str:
    lines: list[str] = []

    lines.append("── Tank benchmark comparison ────────────────────────────────────")
    lines.append(f"  baseline : {c['baseline_version']} @ {c['baseline_commit']}")
    lines.append(f"  candidate: {c['candidate_version']} @ {c['candidate_commit']}")
    lines.append(f"  counter  : {c['token_counter']} (approx ±15%)")

    # Schema
    lines.append("")
    lines.append("  Schema overhead")
    s = c["schema"]
    for tool in s["tools"]:
        d = _fmt_pct(tool["delta_pct"]) if tool["delta_pct"] else "—"
        lines.append(
            f"    {tool['name']:22s}  {tool['before']:>6} → {tool['after']:>6}  {d}"
        )
    total_d = _fmt_pct(s["delta_pct"]) if s["delta_pct"] else "—"
    status = _status(s["warn"])
    lines.append(
        f"    {'TOTAL':22s}  {s['before']:>6} → {s['after']:>6}  {total_d:>8}  {status}"
    )
    lines.append(
        f"    {'% of 200K ctx':22s}  {s['pct_200k_before']:.3f}% → {s['pct_200k_after']:.3f}%"
    )

    # Responses
    lines.append("")
    lines.append("  Response sizes (tokens/result)")
    lines.append(f"    {'':20s}  {'before':>7}  {'after':>7}  {'delta':>8}  status")
    for row in c["responses"]:
        label = (
            row["key"]
            .replace("_n", " N=")
            .replace("summary", "summary")
            .replace("full", "full   ")
        )
        d = _fmt_pct(row["delta_pct"]) if row["delta_pct"] else "—"
        st = _status(row["warn"])
        lines.append(
            f"    {label:20s}  {row['before']:>7}  {row['after']:>7}  {d:>8}  {st}"
        )

    # Progressive disclosure
    pd = c["progressive_disclosure"]
    lines.append("")
    lines.append("  Progressive disclosure")
    rows = [
        (
            "step 1 (summary)",
            pd["step1_before"],
            pd["step1_after"],
            pd["step1_delta"],
            False,
        ),
        (
            "step 2 (full top 3)",
            pd["step2_before"],
            pd["step2_after"],
            pd["step2_delta"],
            False,
        ),
        ("total", pd["total_before"], pd["total_after"], pd["total_delta"], False),
        (
            "naive full N=20",
            pd["naive_before"],
            pd["naive_after"],
            _pct_delta(pd["naive_before"], pd["naive_after"]),
            False,
        ),
    ]
    for label, bef, aft, delta, warn in rows:
        d = _fmt_pct(delta) if delta else "—"
        lines.append(f"    {label:22s}  {bef:>6} → {aft:>6}  {d:>8}")
    saving_d = _fmt_pp(pd["saving_delta_pp"])
    st = _status(pd["warn"])
    lines.append(
        f"    {'saving %':22s}  {pd['saving_before']:.1f}% → {pd['saving_after']:.1f}%  "
        f"{saving_d:>8}  {st}"
    )

    # Summary
    lines.append("")
    if c["passed"]:
        lines.append("  Result: PASS")
    else:
        lines.append(f"  Result: WARN ({len(c['warnings'])} threshold(s) exceeded)")
        for w in c["warnings"]:
            lines.append(f"    • {w}")
    lines.append("─────────────────────────────────────────────────────────────────")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------


def _md_status(warn: bool) -> str:
    return "⚠️" if warn else "✅"


def _md_delta_pct(v: float | None, warn: bool = False) -> str:
    if v is None or v == 0.0:
        return "—"
    s = _fmt_pct(v)
    return f"{s} {_md_status(warn)}" if warn else s


def _md_delta_pp(v: float, warn: bool = False) -> str:
    if v == 0.0:
        return "—"
    s = _fmt_pp(v)
    return f"{s} {_md_status(warn)}" if warn else s


def format_markdown(c: dict) -> str:
    lines: list[str] = []

    lines.append("<!-- tank-benchmark -->")
    result_line = (
        "✅ **PASS**"
        if c["passed"]
        else f"⚠️ **WARN** — {len(c['warnings'])} threshold(s) exceeded"
    )
    lines.append(f"## 📊 Tank benchmark delta  {result_line}")
    lines.append("")
    lines.append(
        f"**baseline** `{c['baseline_commit']}` (v{c['baseline_version']}) → "
        f"**PR** `{c['candidate_commit']}` (v{c['candidate_version']})"
    )
    lines.append(f"*Token counter: `{c['token_counter']}` (±15% approximate)*")

    if c["warnings"]:
        lines.append("")
        for w in c["warnings"]:
            lines.append(f"> ⚠️ {w}")

    # Schema
    s = c["schema"]
    lines.append("")
    lines.append("### Schema overhead")
    lines.append("")
    lines.append("| Tool | baseline | PR | Δ |")
    lines.append("|---|---:|---:|---|")
    for tool in s["tools"]:
        d = _md_delta_pct(tool["delta_pct"])
        lines.append(f"| `{tool['name']}` | {tool['before']} | {tool['after']} | {d} |")
    total_d = _md_delta_pct(s["delta_pct"], s["warn"])
    lines.append(
        f"| **Total** | **{s['before']}** | **{s['after']}** | **{total_d}** |"
    )
    lines.append(
        f"| % of 200K ctx | {s['pct_200k_before']:.3f}% | {s['pct_200k_after']:.3f}% | — |"
    )

    # Responses
    lines.append("")
    lines.append("### Response sizes (tokens per result)")
    lines.append("")
    lines.append("| | baseline | PR | Δ |")
    lines.append("|---|---:|---:|---|")
    for row in c["responses"]:
        label = row["key"].replace("_n", " N=")
        d = _md_delta_pct(row["delta_pct"], row["warn"])
        lines.append(f"| {label} | {row['before']} | {row['after']} | {d} |")

    # Progressive disclosure
    pd = c["progressive_disclosure"]
    lines.append("")
    lines.append("### Progressive disclosure")
    lines.append("")
    lines.append("| | baseline | PR | Δ |")
    lines.append("|---|---:|---:|---|")
    for label, bef, aft, delta in [
        (
            "step 1 (summary scan)",
            pd["step1_before"],
            pd["step1_after"],
            pd["step1_delta"],
        ),
        (
            "step 2 (full, top 3)",
            pd["step2_before"],
            pd["step2_after"],
            pd["step2_delta"],
        ),
        (
            "**total two-step**",
            pd["total_before"],
            pd["total_after"],
            pd["total_delta"],
        ),
        (
            "naive full N=20",
            pd["naive_before"],
            pd["naive_after"],
            _pct_delta(pd["naive_before"], pd["naive_after"]),
        ),
    ]:
        d = _md_delta_pct(delta)
        lines.append(f"| {label} | {bef} | {aft} | {d} |")
    saving_d = _md_delta_pp(pd["saving_delta_pp"], pd["warn"])
    lines.append(
        f"| **saving %** | **{pd['saving_before']:.1f}%** | "
        f"**{pd['saving_after']:.1f}%** | **{saving_d}** |"
    )

    # Threshold reference
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Threshold reference</summary>")
    lines.append("")
    lines.append("| Metric | Threshold |")
    lines.append("|---|---|")
    lines.append(f"| Schema total tokens | > +{_SCHEMA_TOKENS_WARN_PCT:.0f}% → warn |")
    lines.append(
        f"| Summary tokens/result | > +{_SUMMARY_PER_RESULT_WARN_PCT:.0f}% → warn |"
    )
    lines.append(
        f"| Progressive disclosure saving | < {_PD_SAVING_WARN_FLOOR:.0f}% → warn |"
    )
    lines.append("")
    lines.append("</details>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if len(args) != 2:
        print(
            "usage: compare.py <baseline.json> <candidate.json> [--markdown]",
            file=sys.stderr,
        )
        sys.exit(2)

    markdown = "--markdown" in flags
    baseline = _load(args[0])
    candidate = _load(args[1])
    result = compare(baseline, candidate)

    if markdown:
        print(format_markdown(result))
    else:
        print(format_text(result))

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
