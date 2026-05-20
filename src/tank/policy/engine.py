from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

from tank.errors import PolicyError


@dataclass
class PolicyResult:
    allowed: bool
    reason: str


@dataclass
class Policy:
    require_signatures: bool
    require_attribution: bool
    allowed_lifecycle_states: list[str]
    rejected_doc_version_statuses: list[str]

    # Built-in defaults — all states except revoked allowed
    _DEFAULT_LIFECYCLE: tuple[str, ...] = (
        "draft",
        "approved",
        "deprecated",
    )
    _DEFAULT_REJECTED_STATUSES: tuple[str, ...] = ()

    @classmethod
    def default(cls) -> "Policy":
        return cls(
            require_signatures=False,
            require_attribution=True,
            allowed_lifecycle_states=list(cls._DEFAULT_LIFECYCLE),
            rejected_doc_version_statuses=list(cls._DEFAULT_REJECTED_STATUSES),
        )

    @classmethod
    def load(
        cls,
        policy_path: Path | None = None,
        project_dir: Path | None = None,
        home_dir: Path | None = None,
    ) -> "Policy":
        # 1. Explicit path
        if policy_path is not None:
            if not policy_path.exists():
                raise PolicyError(f"Policy file not found: {policy_path}")
            try:
                with open(policy_path, "rb") as f:
                    data = tomllib.load(f)
                return _parse_policy(data)
            except tomllib.TOMLDecodeError as exc:
                raise PolicyError(f"Invalid TOML in {policy_path}: {exc}") from exc

        # 2. Project .tank/policy.toml
        if project_dir is not None:
            proj_path = project_dir / ".tank" / "policy.toml"
            if proj_path.exists():
                try:
                    with open(proj_path, "rb") as f:
                        data = tomllib.load(f)
                    return _parse_policy(data)
                except tomllib.TOMLDecodeError as exc:
                    raise PolicyError(f"Invalid TOML in {proj_path}: {exc}") from exc

        # 3. User ~/.tank/policy.toml
        resolved_home = home_dir if home_dir is not None else Path.home()
        if resolved_home is not None:
            home_path = resolved_home / ".tank" / "policy.toml"
            if home_path.exists():
                try:
                    with open(home_path, "rb") as f:
                        data = tomllib.load(f)
                    return _parse_policy(data)
                except tomllib.TOMLDecodeError as exc:
                    raise PolicyError(f"Invalid TOML in {home_path}: {exc}") from exc

        # 4. Built-in defaults
        return cls.default()

    def evaluate(
        self,
        lifecycle_state: str,
        doc_version_status: str,
    ) -> PolicyResult:
        if lifecycle_state not in self.allowed_lifecycle_states:
            return PolicyResult(
                allowed=False,
                reason=f"lifecycle_state '{lifecycle_state}' is not allowed by policy",
            )
        if doc_version_status in self.rejected_doc_version_statuses:
            return PolicyResult(
                allowed=False,
                reason=f"doc_version_status '{doc_version_status}' is rejected by policy",
            )
        return PolicyResult(allowed=True, reason="")


def _parse_policy(data: dict[str, Any]) -> Policy:
    policy = data.get("policy", {})
    return Policy(
        require_signatures=bool(policy.get("require_signatures", False)),
        require_attribution=bool(policy.get("require_attribution", True)),
        allowed_lifecycle_states=list(
            policy.get("allowed_lifecycle_states", list(Policy._DEFAULT_LIFECYCLE))
        ),
        rejected_doc_version_statuses=list(
            policy.get(
                "rejected_doc_version_statuses", list(Policy._DEFAULT_REJECTED_STATUSES)
            )
        ),
    )
