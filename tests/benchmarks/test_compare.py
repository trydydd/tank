"""Unit tests for tests/benchmarks/compare.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.benchmarks.compare import (
    _fmt_pct,
    _fmt_pp,
    _load,
    _pct_delta,
    _pp_delta,
    compare,
    format_markdown,
    format_text,
    main,
)


# ---------------------------------------------------------------------------
# Fixture factory
# ---------------------------------------------------------------------------


def _make_result(
    *,
    schema_total: int = 260,
    summary_n5_tpr: float = 113.0,
    summary_n10_tpr: float = 112.0,
    summary_n20_tpr: float = 112.0,
    full_n5_tpr: float = 362.0,
    full_n10_tpr: float = 354.0,
    full_n20_tpr: float = 356.0,
    pd_saving_pct: float = 52.2,
    git_commit: str = "abc123",
    tank_version: str = "0.1.0",
    tool_tokens: dict[str, int] | None = None,
    step1_tokens: int = 2012,
    step2_tokens: int = 1047,
    total_pd_tokens: int = 3059,
    naive_tokens: int = 6405,
) -> dict[str, Any]:
    if tool_tokens is None:
        tool_tokens = {"resolve-deps": 75, "query-docs": 185}
    return {
        "git_commit": git_commit,
        "tank_version": tank_version,
        "token_counter": "len_div_4",
        "schema": {
            "total_tokens": schema_total,
            "pct_of_200k_context": round(schema_total / 200_000 * 100, 3),
            "tools": [{"name": k, "tokens": v} for k, v in tool_tokens.items()],
        },
        "responses": {
            "summary_n5": {
                "tokens": int(summary_n5_tpr * 5),
                "actual_results": 5,
                "tokens_per_result": summary_n5_tpr,
            },
            "summary_n10": {
                "tokens": int(summary_n10_tpr * 10),
                "actual_results": 10,
                "tokens_per_result": summary_n10_tpr,
            },
            "summary_n20": {
                "tokens": int(summary_n20_tpr * 20),
                "actual_results": 20,
                "tokens_per_result": summary_n20_tpr,
            },
            "full_n5": {
                "tokens": int(full_n5_tpr * 5),
                "actual_results": 5,
                "tokens_per_result": full_n5_tpr,
            },
            "full_n10": {
                "tokens": int(full_n10_tpr * 10),
                "actual_results": 10,
                "tokens_per_result": full_n10_tpr,
            },
            "full_n20": {
                "tokens": int(full_n20_tpr * 20),
                "actual_results": 20,
                "tokens_per_result": full_n20_tpr,
            },
        },
        "progressive_disclosure": {
            "step1_summary_all_tokens": step1_tokens,
            "step2_full_top3_tokens": step2_tokens,
            "total_tokens": total_pd_tokens,
            "vs_naive_full_n20_tokens": naive_tokens,
            "saving_pct": pd_saving_pct,
        },
    }


# ---------------------------------------------------------------------------
# _pct_delta
# ---------------------------------------------------------------------------


def test_pct_delta_positive() -> None:
    assert _pct_delta(100.0, 120.0) == pytest.approx(20.0)


def test_pct_delta_negative() -> None:
    assert _pct_delta(100.0, 80.0) == pytest.approx(-20.0)


def test_pct_delta_no_change() -> None:
    assert _pct_delta(100.0, 100.0) == pytest.approx(0.0)


def test_pct_delta_zero_before_returns_none() -> None:
    assert _pct_delta(0.0, 100.0) is None


def test_pct_delta_zero_both_returns_none() -> None:
    assert _pct_delta(0.0, 0.0) is None


# ---------------------------------------------------------------------------
# _pp_delta
# ---------------------------------------------------------------------------


def test_pp_delta_positive() -> None:
    assert _pp_delta(40.0, 52.2) == pytest.approx(12.2)


def test_pp_delta_negative() -> None:
    assert _pp_delta(52.2, 40.0) == pytest.approx(-12.2)


# ---------------------------------------------------------------------------
# _fmt_pct / _fmt_pp
# ---------------------------------------------------------------------------


def test_fmt_pct_none_returns_na() -> None:
    assert _fmt_pct(None) == "n/a"


def test_fmt_pct_positive_shows_sign() -> None:
    assert _fmt_pct(20.1) == "+20.1%"


def test_fmt_pct_negative_no_plus() -> None:
    assert "-5.0%" in _fmt_pct(-5.0)
    assert "+" not in _fmt_pct(-5.0)


def test_fmt_pp_positive_shows_pp() -> None:
    assert _fmt_pp(5.5) == "+5.5pp"


def test_fmt_pp_negative_shows_pp() -> None:
    assert _fmt_pp(-3.2) == "-3.2pp"


# ---------------------------------------------------------------------------
# compare() — identical inputs
# ---------------------------------------------------------------------------


def test_compare_identical_passes() -> None:
    r = _make_result()
    result = compare(r, r)
    assert result["passed"] is True
    assert result["warnings"] == []


# ---------------------------------------------------------------------------
# compare() — schema threshold boundaries
# ---------------------------------------------------------------------------


def test_compare_schema_exactly_at_threshold_no_warn() -> None:
    # +20.0% exactly — strict '>' means this does NOT warn
    b = _make_result(schema_total=100)
    c = _make_result(schema_total=120)
    result = compare(b, c)
    assert result["schema"]["warn"] is False
    assert result["passed"] is True


def test_compare_schema_above_threshold_warns() -> None:
    # +21% > 20% threshold
    b = _make_result(schema_total=100)
    c = _make_result(schema_total=121)
    result = compare(b, c)
    assert result["schema"]["warn"] is True
    assert result["passed"] is False
    assert any("schema tokens" in w for w in result["warnings"])


def test_compare_schema_delta_values_correct() -> None:
    b = _make_result(schema_total=200)
    c = _make_result(schema_total=250)
    result = compare(b, c)
    assert result["schema"]["before"] == 200
    assert result["schema"]["after"] == 250
    assert result["schema"]["delta_pct"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# compare() — summary threshold boundaries
# ---------------------------------------------------------------------------


def test_compare_summary_exactly_at_threshold_no_warn() -> None:
    # +15.0% exactly — strict '>' means no warning
    b = _make_result(summary_n10_tpr=100.0)
    c = _make_result(summary_n10_tpr=115.0)
    result = compare(b, c)
    summary_rows = [r for r in result["responses"] if r["key"].startswith("summary")]
    for row in summary_rows:
        if row["key"] == "summary_n10":
            assert row["warn"] is False
    assert result["passed"] is True


def test_compare_summary_above_threshold_warns() -> None:
    # +16% on summary_n10
    b = _make_result(summary_n10_tpr=100.0)
    c = _make_result(summary_n10_tpr=116.0)
    result = compare(b, c)
    summary_n10_row = next(r for r in result["responses"] if r["key"] == "summary_n10")
    assert summary_n10_row["warn"] is True
    assert result["passed"] is False
    assert any("summary" in w for w in result["warnings"])


def test_compare_full_mode_increase_does_not_warn() -> None:
    # Full response tokens increasing does NOT trigger the summary threshold
    b = _make_result(full_n10_tpr=100.0)
    c = _make_result(full_n10_tpr=200.0)  # +100%
    result = compare(b, c)
    full_n10_row = next(r for r in result["responses"] if r["key"] == "full_n10")
    assert full_n10_row["warn"] is False
    # Only schema or PD saving could warn here — those are unchanged
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# compare() — progressive disclosure threshold boundaries
# ---------------------------------------------------------------------------


def test_compare_pd_saving_exactly_at_floor_no_warn() -> None:
    # 40.0% exactly — strict '<' means no warning
    b = _make_result(pd_saving_pct=52.2)
    c = _make_result(pd_saving_pct=40.0)
    result = compare(b, c)
    assert result["progressive_disclosure"]["warn"] is False
    assert result["passed"] is True


def test_compare_pd_saving_below_floor_warns() -> None:
    b = _make_result(pd_saving_pct=52.2)
    c = _make_result(pd_saving_pct=39.9)
    result = compare(b, c)
    assert result["progressive_disclosure"]["warn"] is True
    assert result["passed"] is False
    assert any("progressive disclosure" in w for w in result["warnings"])


def test_compare_pd_saving_delta_pp_correct() -> None:
    b = _make_result(pd_saving_pct=52.2)
    c = _make_result(pd_saving_pct=45.0)
    result = compare(b, c)
    assert result["progressive_disclosure"]["saving_delta_pp"] == pytest.approx(
        45.0 - 52.2
    )


# ---------------------------------------------------------------------------
# compare() — multiple warnings
# ---------------------------------------------------------------------------


def test_compare_multiple_thresholds_exceeded() -> None:
    b = _make_result(schema_total=100, summary_n5_tpr=100.0, pd_saving_pct=52.2)
    c = _make_result(schema_total=130, summary_n5_tpr=120.0, pd_saving_pct=35.0)
    result = compare(b, c)
    assert result["passed"] is False
    assert len(result["warnings"]) == 3


# ---------------------------------------------------------------------------
# compare() — tool add / remove
# ---------------------------------------------------------------------------


def test_compare_tool_added_in_candidate() -> None:
    b = _make_result(tool_tokens={"query-docs": 185, "resolve-deps": 75})
    c = _make_result(
        tool_tokens={"query-docs": 185, "resolve-deps": 75, "new-tool": 50}
    )
    result = compare(b, c)
    tools = {t["name"]: t for t in result["schema"]["tools"]}
    assert "new-tool" in tools
    assert tools["new-tool"]["before"] == 0
    assert tools["new-tool"]["after"] == 50
    # before=0 → _pct_delta returns None (no division by zero)
    assert tools["new-tool"]["delta_pct"] is None


def test_compare_tool_removed_in_candidate() -> None:
    b = _make_result(tool_tokens={"query-docs": 185, "resolve-deps": 75})
    c = _make_result(tool_tokens={"query-docs": 185})
    result = compare(b, c)
    tools = {t["name"]: t for t in result["schema"]["tools"]}
    assert "resolve-deps" in tools
    assert tools["resolve-deps"]["before"] == 75
    assert tools["resolve-deps"]["after"] == 0
    assert tools["resolve-deps"]["delta_pct"] == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# compare() — metadata passthrough
# ---------------------------------------------------------------------------


def test_compare_metadata_passthrough() -> None:
    b = _make_result(git_commit="base000", tank_version="0.0.9")
    c = _make_result(git_commit="cand999", tank_version="0.1.0")
    result = compare(b, c)
    assert result["baseline_commit"] == "base000"
    assert result["baseline_version"] == "0.0.9"
    assert result["candidate_commit"] == "cand999"
    assert result["candidate_version"] == "0.1.0"
    assert result["token_counter"] == "len_div_4"


def test_compare_missing_git_fields_default_to_unknown() -> None:
    b = _make_result()
    c = _make_result()
    del b["git_commit"]
    del b["tank_version"]
    result = compare(b, c)
    assert result["baseline_commit"] == "unknown"
    assert result["baseline_version"] == "unknown"


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------


def test_format_markdown_starts_with_marker() -> None:
    r = _make_result()
    output = format_markdown(compare(r, r))
    assert output.startswith("<!-- tank-benchmark -->")


def test_format_markdown_pass_contains_pass() -> None:
    r = _make_result()
    output = format_markdown(compare(r, r))
    assert "PASS" in output


def test_format_markdown_warn_contains_warn() -> None:
    b = _make_result(schema_total=100)
    c = _make_result(schema_total=130)
    output = format_markdown(compare(b, c))
    assert "<!-- tank-benchmark -->" == output.splitlines()[0]
    assert "WARN" in output


def test_format_markdown_contains_threshold_reference() -> None:
    r = _make_result()
    output = format_markdown(compare(r, r))
    assert "Thresholds" in output
    assert "+20%" in output
    assert "+15%" in output
    assert "40%" in output


# ---------------------------------------------------------------------------
# format_text
# ---------------------------------------------------------------------------


def test_format_text_pass_result() -> None:
    r = _make_result()
    output = format_text(compare(r, r))
    assert "PASS" in output


def test_format_text_warn_result() -> None:
    b = _make_result(schema_total=100)
    c = _make_result(schema_total=130)
    output = format_text(compare(b, c))
    assert "WARN" in output


def test_format_text_contains_version_info() -> None:
    b = _make_result(git_commit="bbb", tank_version="0.0.9")
    c = _make_result(git_commit="ccc", tank_version="0.1.0")
    output = format_text(compare(b, c))
    assert "bbb" in output
    assert "ccc" in output


# ---------------------------------------------------------------------------
# _load
# ---------------------------------------------------------------------------


def test_load_missing_file_exits_2(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _load(str(tmp_path / "nonexistent.json"))
    assert exc.value.code == 2


def test_load_valid_file_returns_dict(tmp_path: Path) -> None:
    data = {"foo": "bar"}
    p = tmp_path / "data.json"
    p.write_text(json.dumps(data))
    result = _load(str(p))
    assert result == data


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------


def test_main_exit_0_on_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    b = _make_result()
    c = _make_result()
    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "candidate.json"
    b_path.write_text(json.dumps(b))
    c_path.write_text(json.dumps(c))
    monkeypatch.setattr(sys, "argv", ["compare.py", str(b_path), str(c_path)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0


def test_main_exit_1_on_warn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    b = _make_result(schema_total=100)
    c = _make_result(schema_total=130)  # +30% > 20% threshold
    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "candidate.json"
    b_path.write_text(json.dumps(b))
    c_path.write_text(json.dumps(c))
    monkeypatch.setattr(sys, "argv", ["compare.py", str(b_path), str(c_path)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_exit_2_on_wrong_arg_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["compare.py"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_main_exit_2_on_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare.py",
            str(tmp_path / "missing.json"),
            str(tmp_path / "also_missing.json"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_main_markdown_flag_does_not_change_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    b = _make_result()
    c = _make_result()
    b_path = tmp_path / "baseline.json"
    c_path = tmp_path / "candidate.json"
    b_path.write_text(json.dumps(b))
    c_path.write_text(json.dumps(c))
    monkeypatch.setattr(
        sys, "argv", ["compare.py", str(b_path), str(c_path), "--markdown"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
