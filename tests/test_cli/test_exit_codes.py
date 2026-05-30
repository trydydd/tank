"""Tests for the differentiated CLI exit-code contract.

Unit-level: the exception → code mapping. End-to-end: real `synd` invocations
that drive each documented code through the CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.cli.exit_codes import (
    EXIT_BUILD,
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    EXIT_POLICY,
    EXIT_VERIFICATION,
    exit_code_for,
    verify_failure_code,
)
from synd.cli.main import cli
from synd.errors import (
    BuildError,
    FetchError,
    ImportError_,
    LockfileError,
    ManifestError,
    PackNotFoundError,
    PolicyError,
    SchemaValidationError,
    SearchError,
    SyndError,
    VerificationError,
)

_FIXTURE_DOCS = Path(__file__).parent.parent / "fixtures" / "sample_docs"


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (PackNotFoundError("x"), EXIT_NOT_FOUND),
        (PolicyError("x"), EXIT_POLICY),
        (VerificationError("x"), EXIT_VERIFICATION),
        (SchemaValidationError("x"), EXIT_VERIFICATION),
        (ManifestError("x"), EXIT_VERIFICATION),
        (BuildError("x"), EXIT_BUILD),
        (FetchError("x"), EXIT_BUILD),
        (LockfileError("x"), EXIT_BUILD),
        (SearchError("x"), EXIT_ERROR),
        (ImportError_("x"), EXIT_ERROR),
        (SyndError("x"), EXIT_ERROR),
        (ValueError("not a synd error"), EXIT_ERROR),
    ],
)
def test_exit_code_for(exc: Exception, code: int) -> None:
    assert exit_code_for(exc) == code


@pytest.mark.parametrize(
    ("step", "code"),
    [
        (3, EXIT_POLICY),
        (1, EXIT_VERIFICATION),
        (2, EXIT_VERIFICATION),
        (6, EXIT_VERIFICATION),
        (7, EXIT_VERIFICATION),
        (None, EXIT_VERIFICATION),
    ],
)
def test_verify_failure_code(step: int | None, code: int) -> None:
    assert verify_failure_code(step) == code


# --- End-to-end: real CLI invocations produce the documented codes ---


def _build(out: Path, *, lifecycle: str = "draft") -> Path:
    result = CliRunner().invoke(
        cli,
        [
            "build",
            "my-lib@1.0.0",
            "--source",
            str(_FIXTURE_DOCS),
            "--output",
            str(out),
            "--lifecycle",
            lifecycle,
        ],
    )
    assert result.exit_code == 0, result.output
    return out / "my-lib@1.0.0.ctx"


def test_e2e_success_code_0(tmp_path: Path) -> None:
    _build(tmp_path / "build")


def test_e2e_usage_code_2(tmp_path: Path) -> None:
    """Malformed package spec → usage error."""
    result = CliRunner().invoke(
        cli, ["build", "no-at-sign", "--source", str(_FIXTURE_DOCS)]
    )
    assert result.exit_code == 2


def test_e2e_policy_code_3(tmp_path: Path) -> None:
    """A 'revoked' pack is rejected by the default policy at verify step 3."""
    ctx = _build(tmp_path / "build", lifecycle="revoked")
    result = CliRunner().invoke(cli, ["verify", str(ctx)])
    assert result.exit_code == 3, result.output


def test_e2e_verification_code_4(tmp_path: Path) -> None:
    """A corrupt archive fails verification."""
    import zipfile

    broken = tmp_path / "broken.ctx"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("manifest.json", "not json")
        zf.writestr("chunks.jsonl", "")
        zf.writestr("pages.json", "[]")
    result = CliRunner().invoke(cli, ["verify", str(broken)])
    assert result.exit_code == 4, result.output


def test_e2e_not_found_code_5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing a pack that was never imported → not found."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["remove", "ghost@9.9.9"])
    assert result.exit_code == 5, result.output


def test_e2e_build_code_6(tmp_path: Path) -> None:
    """An unsupported URL source is a build failure."""
    result = CliRunner().invoke(
        cli,
        ["build", "my-lib@1.0.0", "--source", "https://example.com/README.md"],
    )
    assert result.exit_code == 6, result.output
