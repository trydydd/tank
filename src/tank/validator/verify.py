"""8-step archive safety validator.

Runs the verification sequence on a .ctx pack before allowing it into the index.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tank.builder.normalizer import normalize
from tank.errors import SchemaValidationError
from tank.policy.engine import Policy, PolicyResult
from tank.schemas import validate_manifest


@dataclass
class VerifyResult:
    passed: bool
    step: int | None  # step number that failed, None if all passed
    reason: str
    manifest: (
        dict[str, Any] | None
    )  # parsed manifest on success, None on failure before step 2


_MAX_ENTRIES = 10_000
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
_MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500 MB


def verify(
    ctx_path: Path,
    policy: Policy,
) -> VerifyResult:
    """Run the 8-step archive safety validation sequence.

    Returns VerifyResult with pass/fail status. Steps execute in order and
    stop at the first failure.
    """
    # --- Step 1: Open archive, read manifest.json only ---
    try:
        zf = zipfile.ZipFile(ctx_path, "r")
    except (zipfile.BadZipFile, OSError):
        return VerifyResult(
            passed=False,
            step=1,
            reason=f"Cannot open archive — not a valid ZIP file: {ctx_path.name}",
            manifest=None,
        )

    with zf:
        manifest: dict[str, Any] | None = None

        # --- Step 1: Read and parse manifest ---
        try:
            manifest_raw = zf.read("manifest.json")
        except KeyError:
            return VerifyResult(
                passed=False,
                step=1,
                reason="manifest.json not found in archive",
                manifest=None,
            )

        try:
            manifest = json.loads(manifest_raw)
        except json.JSONDecodeError as exc:
            return VerifyResult(
                passed=False,
                step=1,
                reason=f"manifest.json contains invalid JSON: {exc}",
                manifest=None,
            )

        # --- Step 2: Validate manifest JSON schema ---
        try:
            validate_manifest(manifest)
        except SchemaValidationError as exc:
            return VerifyResult(
                passed=False,
                step=2,
                reason=f"Invalid manifest: {exc}",
                manifest=None,
            )

        # --- Step 3: Check lifecycle_state against policy ---
        lc = manifest.get("lifecycle_state", "")
        dvs = manifest.get("doc_version_status", "")
        policy_result: PolicyResult = policy.evaluate(lc, dvs)
        if not policy_result.allowed:
            return VerifyResult(
                passed=False,
                step=3,
                reason=policy_result.reason,
                manifest=manifest,
            )

        # --- Step 4: Scan archive file listing for unsafe entries ---
        infos = zf.infolist()
        for info in infos:
            name = info.filename

            # Absolute path check — covers Unix (/), UNC (//server), and Windows drive letters (C:/)
            normalized_name = name.replace("\\", "/")
            if normalized_name.startswith("/") or re.match(
                r"^[A-Za-z]:/", normalized_name
            ):
                return VerifyResult(
                    passed=False,
                    step=4,
                    reason=f"Unsafe archive entry: {name} (absolute path)",
                    manifest=manifest,
                )

            # Path traversal check
            parts = name.replace("\\", "/").split("/")
            if ".." in parts:
                return VerifyResult(
                    passed=False,
                    step=4,
                    reason=f"Unsafe archive entry: {name} (path traversal)",
                    manifest=manifest,
                )

            # Symlink check via external_attr
            if info.external_attr is not None:
                file_type = (info.external_attr >> 16) & 0o170000
                if file_type == 0o120000:  # S_IFLNK
                    return VerifyResult(
                        passed=False,
                        step=4,
                        reason=f"Unsafe archive entry: {name} (symbolic link)",
                        manifest=manifest,
                    )

        # --- Step 5: Enforce size and count limits ---
        total_size = 0
        for info in infos:
            if info.file_size > _MAX_FILE_SIZE:
                return VerifyResult(
                    passed=False,
                    step=5,
                    reason=(
                        f"Archive exceeds size limit: {info.filename} "
                        f"is {info.file_size} bytes (max {_MAX_FILE_SIZE})"
                    ),
                    manifest=manifest,
                )
            total_size += info.file_size

        if len(infos) > _MAX_ENTRIES:
            return VerifyResult(
                passed=False,
                step=5,
                reason=(
                    f"Archive exceeds entry count limit: "
                    f"{len(infos)} entries (max {_MAX_ENTRIES})"
                ),
                manifest=manifest,
            )

        if total_size > _MAX_TOTAL_SIZE:
            return VerifyResult(
                passed=False,
                step=5,
                reason=(
                    f"Archive exceeds total size limit: "
                    f"{total_size} bytes total (max {_MAX_TOTAL_SIZE})"
                ),
                manifest=manifest,
            )

        # --- Step 6: Recompute pack_digest ---
        archive_buf = _read_archive_bytes(ctx_path, manifest)
        computed_digest = _compute_pack_digest_from_bytes(archive_buf)
        if computed_digest != manifest["pack_digest"]:
            return VerifyResult(
                passed=False,
                step=6,
                reason="pack_digest mismatch: archive may be tampered",
                manifest=manifest,
            )

        # --- Step 7: Recompute normalized_content_hash ---
        try:
            computed_nch = _compute_normalized_content_hash_from_archive(zf)
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return VerifyResult(
                passed=False,
                step=7,
                reason=f"Failed to parse chunks.jsonl: {exc}",
                manifest=manifest,
            )
        if computed_nch != manifest["normalized_content_hash"]:
            return VerifyResult(
                passed=False,
                step=7,
                reason="normalized_content_hash mismatch",
                manifest=manifest,
            )

        # --- Step 8: Verify signature (MVP stub) ---
        if policy.require_signatures:
            try:
                zf.read("signatures/manifest.sig")
            except KeyError:
                return VerifyResult(
                    passed=False,
                    step=8,
                    reason="Signature required by policy but missing",
                    manifest=manifest,
                )

        return VerifyResult(
            passed=True,
            step=None,
            reason="",
            manifest=manifest,
        )


def _read_archive_bytes(ctx_path: Path, manifest: dict[str, Any]) -> bytes:
    """Read all archive bytes, zeroing pack_digest in the manifest."""
    with zipfile.ZipFile(ctx_path, "r") as zf:
        info_list = zf.infolist()

    zeroed_manifest = dict(manifest)
    zeroed_manifest["pack_digest"] = ""
    zeroed_manifest_json = json.dumps(zeroed_manifest, indent=2, sort_keys=True).encode(
        "utf-8"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(ctx_path, "r") as zf:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for item in info_list:
                content = zf.read(item.filename)
                if item.filename == "manifest.json":
                    content = zeroed_manifest_json
                out.writestr(item, content)

    return buf.getvalue()


def _compute_pack_digest_from_bytes(data: bytes) -> str:
    """SHA-256 hex digest of archive bytes with pack_digest zeroed."""
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()


def _compute_normalized_content_hash_from_archive(zf: zipfile.ZipFile) -> str:
    """Extract chunks.jsonl, normalize, concatenate in ascending id order, hash."""
    import hashlib

    raw = zf.read("chunks.jsonl")
    lines = raw.decode("utf-8").strip().split("\n")

    chunks: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if line:
            chunks.append(json.loads(line))

    # Sort by id ascending
    chunks.sort(key=lambda c: c.get("id", 0))

    parts: list[str] = []
    for chunk in chunks:
        content = chunk.get("content", "")
        normalized = normalize(content)
        parts.append(normalized)

    concatenated = "\n".join(parts)
    return "sha256:" + hashlib.sha256(concatenated.encode("utf-8")).hexdigest()
