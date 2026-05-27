from pathlib import Path
import tempfile
import textwrap
import pytest
from synd.policy.engine import Policy
from synd.errors import PolicyError


def _write_toml(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


def test_load_from_explicit_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.toml"
        _write_toml(
            p,
            """
            [policy]
            require_signatures = true
            require_attribution = true
            allowed_lifecycle_states = ["approved"]
            rejected_doc_version_statuses = ["archived"]
        """,
        )
        policy = Policy.load(policy_path=p)
        assert policy.require_signatures is True
        assert policy.require_attribution is True
        assert policy.allowed_lifecycle_states == ["approved"]
        assert policy.rejected_doc_version_statuses == ["archived"]


def test_load_from_project_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / ".synd" / "policy.toml"
        _write_toml(
            p,
            """
            [policy]
            require_signatures = false
            allowed_lifecycle_states = ["draft", "approved"]
            rejected_doc_version_statuses = []
        """,
        )
        policy = Policy.load(project_dir=Path(tmp))
        assert policy.allowed_lifecycle_states == ["draft", "approved"]


def test_load_from_user_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        p = home / ".synd" / "policy.toml"
        _write_toml(
            p,
            """
            [policy]
            allowed_lifecycle_states = ["approved", "deprecated"]
            rejected_doc_version_statuses = []
        """,
        )
        # home_dir simulates ~/.synd/ — user dir is checked after project dir
        policy = Policy.load(project_dir=Path("/nonexistent"), home_dir=home)
        assert policy.allowed_lifecycle_states == ["approved", "deprecated"]


def test_load_falls_back_to_defaults() -> None:
    policy = Policy.load(project_dir=Path("/nonexistent"))
    assert policy.allowed_lifecycle_states == ["draft", "approved", "deprecated"]
    assert policy.require_signatures is False
    assert policy.rejected_doc_version_statuses == []


def test_load_no_args_falls_back_to_defaults() -> None:
    policy = Policy.load()
    assert policy.allowed_lifecycle_states == ["draft", "approved", "deprecated"]


def test_default_policy_allows_approved() -> None:
    policy = Policy.default()
    result = policy.evaluate("approved", "stable")
    assert result.allowed is True


def test_default_policy_allows_deprecated() -> None:
    policy = Policy.default()
    result = policy.evaluate("deprecated", "stable")
    assert result.allowed is True


def test_default_policy_rejects_revoked() -> None:
    policy = Policy.default()
    result = policy.evaluate("revoked", "stable")
    assert result.allowed is False


def test_evaluate_rejects_disallowed_state() -> None:
    policy = Policy(
        require_signatures=False,
        require_attribution=False,
        allowed_lifecycle_states=["approved"],
        rejected_doc_version_statuses=[],
    )
    result = policy.evaluate("draft", "stable")
    assert result.allowed is False


def test_evaluate_rejects_archived_doc_status() -> None:
    policy = Policy(
        require_signatures=False,
        require_attribution=False,
        allowed_lifecycle_states=["draft", "approved", "deprecated", "revoked"],
        rejected_doc_version_statuses=["archived"],
    )
    result = policy.evaluate("approved", "archived")
    assert result.allowed is False


def test_evaluate_passes_valid_pack() -> None:
    policy = Policy(
        require_signatures=False,
        require_attribution=False,
        allowed_lifecycle_states=["approved"],
        rejected_doc_version_statuses=[],
    )
    result = policy.evaluate("approved", "stable")
    assert result.allowed is True


def test_invalid_toml_raises_policy_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "invalid.toml"
        p.write_text("[[broken\n")
        with pytest.raises(PolicyError):
            Policy.load(policy_path=p)


def test_nonexistent_policy_path_raises() -> None:
    with pytest.raises(PolicyError):
        Policy.load(policy_path=Path("/nonexistent/policy.toml"))


def test_load_uses_home_dir_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        p = home / ".synd" / "policy.toml"
        _write_toml(
            p,
            """
            [policy]
            allowed_lifecycle_states = ["approved"]
        """,
        )
        policy = Policy.load(project_dir=Path("/nonexistent"), home_dir=home)
        assert policy.allowed_lifecycle_states == ["approved"]


def test_partial_policy_uses_permissive_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.toml"
        _write_toml(
            p,
            """
            [policy]
            require_signatures = true
        """,
        )
        policy = Policy.load(policy_path=p)
        assert policy.require_signatures is True
        assert policy.allowed_lifecycle_states == ["draft", "approved", "deprecated"]
