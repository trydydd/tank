"""Tests for the 8-step archive safety validator."""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest

from synd.builder.build import build_pack
from synd.policy.engine import Policy
from synd.validator.verify import VerifyResult, verify

_REQUIRED_FIELDS = [
    "schema_version",
    "pack_format",
    "package",
    "version",
    "pack_digest",
    "normalized_content_hash",
    "chunks",
    "pages",
    "lifecycle_state",
    "doc_version_status",
    "created_at",
    "created_by",
]


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


def _build_valid_ctx(tmp_path: Path) -> Path:
    """Build a valid .ctx pack and return the path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    import os

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        output = tmp_path / "packs"
        output.mkdir()
        ctx_path, _ = build_pack(
            package="test-lib",
            version="1.0.0",
            source=_fixture_path(),
            output=output,
        )
        return ctx_path
    finally:
        os.chdir(old_cwd)


def _create_empty_zip(path: Path) -> None:
    """Create a zip file with no entries (not a valid .ctx)."""
    with zipfile.ZipFile(path, "w") as _:
        pass


def _rewrite_archive_keep_digest(
    src: Path,
    manifest_override: dict[str, object] | None = None,
    extra_entries: dict[str, bytes] | None = None,
    remove_entries: set[str] | None = None,
) -> Path:
    """Rewrite a .ctx archive with correct pack_digest.

    First builds the modified archive, then computes the correct digest.
    """
    import hashlib as _hashlib
    import io as _io

    result = src.parent / (src.stem + "_rebuilt" + src.suffix)

    with zipfile.ZipFile(src, "r") as zf:
        manifest_json_raw = zf.read("manifest.json")
        manifest = json.loads(manifest_json_raw)

    if manifest_override:
        manifest.update(manifest_override)

    # Step 1: Build the modified archive (without pack_digest in manifest)
    # to compute the correct digest
    with zipfile.ZipFile(src, "r") as orig:
        with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in orig.infolist():
                data = orig.read(item.filename)
                if item.filename == "manifest.json":
                    zeroed = dict(manifest)
                    zeroed["pack_digest"] = ""
                    data = json.dumps(zeroed, indent=2, sort_keys=True).encode()
                if remove_entries and item.filename in remove_entries:
                    continue
                zf.writestr(item, data)
            if extra_entries:
                for name, data in extra_entries.items():
                    zf.writestr(name, data)

    # Step 2: Compute pack_digest from the modified archive
    buf = _io.BytesIO()
    with zipfile.ZipFile(result, "r") as zf:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for item in zf.infolist():
                data = zf.read(item.filename)
                if item.filename == "manifest.json":
                    zeroed = dict(manifest)
                    zeroed["pack_digest"] = ""
                    data = json.dumps(zeroed, indent=2, sort_keys=True).encode()
                out.writestr(item, data)
    digest = "sha256:" + _hashlib.sha256(buf.getvalue()).hexdigest()

    # Step 3: Update manifest with the real digest
    manifest["pack_digest"] = digest
    manifest_json_out = json.dumps(manifest, indent=2, sort_keys=True).encode()

    # Step 4: Rewrite archive with the updated manifest
    buf2 = _io.BytesIO()
    with zipfile.ZipFile(result, "r") as zf:
        with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as out:
            for item in zf.infolist():
                data = zf.read(item.filename)
                if item.filename == "manifest.json":
                    out.writestr(item, manifest_json_out)
                else:
                    out.writestr(item, data)
    result.write_bytes(buf2.getvalue())

    return result


_ZIP_EPOCH = (2021, 8, 8, 0, 0, 0)


def _rewrite_archive_with_modified_chunks(
    src: Path,
    content_replacements: dict[int, str],
) -> Path:
    """Rewrite archive with modified chunk content, correct digest."""
    import hashlib as _hashlib
    import io as _io

    result = src.parent / (src.stem + "_rebuilt" + src.suffix)

    with zipfile.ZipFile(src, "r") as zf:
        manifest_json = zf.read("manifest.json")
        manifest = json.loads(manifest_json)
        chunks_raw = zf.read("chunks.jsonl")

    lines = chunks_raw.decode("utf-8").strip().split("\n")
    new_chunks = ""
    for line in lines:
        line = line.strip()
        if line:
            rec = json.loads(line)
            if rec["id"] in content_replacements:
                rec["content"] = content_replacements[rec["id"]]
            new_chunks += json.dumps(rec, sort_keys=True) + "\n"
        else:
            new_chunks += "\n"

    # Compute correct pack_digest — pin all ZipInfo timestamps to _ZIP_EPOCH
    buf = _io.BytesIO()
    with zipfile.ZipFile(src, "r") as zf:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            zeroed = dict(manifest)
            zeroed["pack_digest"] = ""
            manifest_info = zipfile.ZipInfo("manifest.json", date_time=_ZIP_EPOCH)
            manifest_info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(
                manifest_info,
                json.dumps(zeroed, indent=2, sort_keys=True).encode(),
            )
            chunks_info = zipfile.ZipInfo("chunks.jsonl", date_time=_ZIP_EPOCH)
            chunks_info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(chunks_info, new_chunks.encode())
            for orig_item in zf.infolist():
                if orig_item.filename in ("manifest.json", "chunks.jsonl"):
                    continue
                out.writestr(orig_item, zf.read(orig_item.filename))
    digest = "sha256:" + _hashlib.sha256(buf.getvalue()).hexdigest()
    manifest["pack_digest"] = digest

    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_info = zipfile.ZipInfo("manifest.json", date_time=_ZIP_EPOCH)
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(
            manifest_info,
            json.dumps(manifest, indent=2, sort_keys=True).encode(),
        )
        chunks_info = zipfile.ZipInfo("chunks.jsonl", date_time=_ZIP_EPOCH)
        chunks_info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(chunks_info, new_chunks.encode())
        with zipfile.ZipFile(src, "r") as orig:
            for orig_item in orig.infolist():
                if orig_item.filename in ("manifest.json", "chunks.jsonl"):
                    continue
                zf.writestr(orig_item, orig.read(orig_item.filename))

    return result


def _create_zip_with_entries(path: Path, entries: dict[str, bytes]) -> None:
    """Create a zip with exactly the given {arcname: content} mapping."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def _make_manifest(**overrides: object) -> dict:
    """Create a minimal valid manifest with optional overrides."""
    m = {
        "schema_version": 2,
        "pack_format": "synd-text-v1",
        "package": "test-lib",
        "version": "1.0.0",
        "pack_digest": "sha256:" + "a" * 64,
        "normalized_content_hash": "sha256:" + "b" * 64,
        "chunks": 1,
        "pages": 1,
        "lifecycle_state": "approved",
        "doc_version_status": "stable",
        "created_at": time.time(),
        "created_by": "synd/0.1.1",
    }
    m.update(overrides)
    return m


# ---------------------------------------------------------------------------
# Happy-path test
# ---------------------------------------------------------------------------


def test_verify_valid_pack_passes(tmp_path: Path) -> None:
    """A valid .ctx built by build_pack() passes all 8 steps."""
    ctx_path = _build_valid_ctx(tmp_path)
    policy = Policy.default()
    result = verify(ctx_path, policy)
    assert result.passed is True
    assert result.step is None
    assert result.manifest is not None


# ---------------------------------------------------------------------------
# Step 1 — open archive, read manifest.json only
# ---------------------------------------------------------------------------


def test_step1_missing_manifest(tmp_path: Path) -> None:
    """Archive without manifest.json fails at step 1."""
    ctx = tmp_path / "bad.ctx"
    _create_zip_with_entries(ctx, {"chunks.jsonl": b'{"id":1}\n'})
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 1


def test_step1_corrupt_zip(tmp_path: Path) -> None:
    """A file that isn't a valid zip fails at step 1."""
    ctx = tmp_path / "not_a_zip.ctx"
    ctx.write_text("not a zip")
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 1


# ---------------------------------------------------------------------------
# Step 2 — validate manifest JSON schema (required fields)
# ---------------------------------------------------------------------------


def test_step2_missing_required_field(tmp_path: Path) -> None:
    """Manifest missing 'package' field is rejected at step 2."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    del manifest["package"]
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "chunks.jsonl": b'{"id":1,"content":"hello"}\n',
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 2
    assert "package" in result.reason


def test_step2_missing_pack_digest_field(tmp_path: Path) -> None:
    """Manifest missing 'pack_digest' field is rejected at step 2."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    del manifest["pack_digest"]
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "chunks.jsonl": b'{"id":1,"content":"hello"}\n',
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 2
    assert "pack_digest" in result.reason


# ---------------------------------------------------------------------------
# Step 3 — check lifecycle_state against policy
# ---------------------------------------------------------------------------


def test_step3_lifecycle_rejected_by_policy(tmp_path: Path) -> None:
    """Revoked lifecycle_state rejected by default policy."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest(lifecycle_state="revoked")
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "chunks.jsonl": b'{"id":1,"content":"hello"}\n',
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 3


# ---------------------------------------------------------------------------
# Step 4 — scan archive file listing for unsafe entries
# ---------------------------------------------------------------------------


def test_step4_absolute_path_rejected(tmp_path: Path) -> None:
    """Archive containing '/etc/passwd' entry fails at step 4."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "/etc/passwd": b"root:x:0:0",
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 4
    assert "Unsafe archive entry" in result.reason


def test_step4_path_traversal_rejected(tmp_path: Path) -> None:
    """Archive containing '../secret.txt' fails at step 4."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "foo/../secret.txt": b"sneaky",
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 4
    assert "Unsafe archive entry" in result.reason


def test_step4_symlink_rejected(tmp_path: Path) -> None:
    """Archive containing a symlink entry fails at step 4."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    # Create a symlink in a temp zip using external_attr
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Write a normal entry for manifest
        zf.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        zf.writestr("chunks.jsonl", b"")
        zf.writestr("pages.json", b"[]")
        zf.writestr("signatures/", b"")

        # Add a symlink entry by setting the external_attr flag for symlink (0o120000)
        info = zipfile.ZipInfo("link_to_secret")
        info.external_attr = 0o120000 << 16  # symlink Unix file type
        zf.writestr(info, "secret_target")

    buf.seek(0)
    ctx.write_bytes(buf.read())

    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 4


# ---------------------------------------------------------------------------
# Step 5 — enforce size and count limits
# ---------------------------------------------------------------------------


def test_step5_too_many_entries(tmp_path: Path) -> None:
    """Archive with 10,001 entries fails at step 5."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    entries: dict[str, bytes] = {
        "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
        "chunks.jsonl": b"",
        "pages.json": b"[]",
        "signatures/": b"",
    }
    for i in range(10001):
        entries[f"entry_{i:05d}.txt"] = b"x"
    _create_zip_with_entries(ctx, entries)
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 5
    assert (
        "entries" in result.reason.lower()
        or "10,000" in result.reason
        or "exceeds" in result.reason.lower()
    )


def test_step5_file_too_large(tmp_path: Path) -> None:
    """Archive with a single >50MB file entry fails at step 5."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    # 51 MB blob — small enough to actually create but above the 50 MB limit
    big_data = b"x" * (51 * 1024 * 1024)
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "huge.txt": big_data,
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 5
    assert (
        "limit" in result.reason.lower()
        or "exceeds" in result.reason.lower()
        or "size" in result.reason.lower()
    )


def test_step5_total_too_large(tmp_path: Path) -> None:
    """Archive with total uncompressed >500MB fails at step 5."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    # 260 MB each of two files = 520 MB total — above 500 MB limit
    big = b"x" * (260 * 1024 * 1024)
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "file_a.bin": big,
            "file_b.bin": big,
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 5
    assert (
        "limit" in result.reason.lower()
        or "exceeds" in result.reason.lower()
        or "size" in result.reason.lower()
    )


# ---------------------------------------------------------------------------
# Step 6 — recompute pack_digest
# ---------------------------------------------------------------------------


def test_step6_pack_digest_mismatch(tmp_path: Path) -> None:
    """Archive with tampered pack_digest fails at step 6."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    manifest["pack_digest"] = "sha256:" + "0" * 64
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "chunks.jsonl": b'{"id":1,"content":"hello"}\n',
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 6


# ---------------------------------------------------------------------------
# Step 7 — recompute normalized_content_hash
# ---------------------------------------------------------------------------


def test_step7_content_hash_mismatch(tmp_path: Path) -> None:
    """Archive with modified chunk content fails at step 7."""
    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "packs"
    output.mkdir()
    ctx_path, _ = build_pack(
        package="test-lib",
        version="1.0.0",
        source=_fixture_path(),
        output=output,
    )
    # Tamper a chunk's content and rebuild the archive with a valid digest
    rebuilt = _rewrite_archive_with_modified_chunks(ctx_path, {1: "tampered content"})
    policy = Policy.default()
    result = verify(rebuilt, policy)
    assert result.passed is False
    assert result.step == 7


# ---------------------------------------------------------------------------
# Step 8 — verify signature (MVP stub)
# ---------------------------------------------------------------------------


def test_step8_signature_required_but_missing(tmp_path: Path) -> None:
    """Policy requiring signatures but manifest.sig absent fails at step 8."""
    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "packs"
    output.mkdir()
    ctx_path, _ = build_pack(
        package="test-lib",
        version="1.0.0",
        source=_fixture_path(),
        output=output,
        lifecycle="approved",
    )
    # Remove the signatures directory from the archive
    no_sig_ctx = _rewrite_archive_keep_digest(
        ctx_path,
        remove_entries={"signatures/"},
    )
    strict_policy = Policy(
        require_signatures=True,
        require_attribution=True,
        allowed_lifecycle_states=["approved", "deprecated"],
        rejected_doc_version_statuses=[],
    )
    result = verify(no_sig_ctx, strict_policy)
    assert result.passed is False
    assert result.step == 8


def test_step8_signature_present_passes(tmp_path: Path) -> None:
    """Policy requiring signatures with manifest.sig present passes step 8."""
    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "packs"
    output.mkdir()
    ctx_path, _ = build_pack(
        package="test-lib",
        version="1.0.0",
        source=_fixture_path(),
        output=output,
        lifecycle="approved",
    )
    # Add signatures/manifest.sig
    sig_ctx = _rewrite_archive_keep_digest(
        ctx_path,
        extra_entries={"signatures/manifest.sig": b"fake-signature-data"},
    )
    strict_policy = Policy(
        require_signatures=True,
        require_attribution=True,
        allowed_lifecycle_states=["approved", "deprecated"],
        rejected_doc_version_statuses=[],
    )
    result = verify(sig_ctx, strict_policy)
    assert result.passed is True


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


def test_verify_does_not_extract_to_disk(tmp_path: Path) -> None:
    """verify() must not write any file to disk — assert tmp_path is empty after verify() returns."""
    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "packs"
    output.mkdir()
    ctx_path, _ = build_pack(
        package="test-lib",
        version="1.0.0",
        source=_fixture_path(),
        output=output,
    )
    before_files = set(tmp_path.rglob("*"))
    policy = Policy.default()
    result = verify(ctx_path, policy)
    assert result.passed is True
    after_files = set(tmp_path.rglob("*"))
    assert after_files == before_files, "verify() wrote files to disk"


def test_verify_stops_at_first_failure(tmp_path: Path) -> None:
    """Archive with step 2 AND step 4 failures must report step 2, not step 4."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    del manifest["package"]  # step 2 failure
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "foo/../evil.txt": b"pwned",  # step 4 failure (ignored)
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 2, "Must report step 2, not step 4"


def test_step6_does_not_pass_tampered_manifest(tmp_path: Path) -> None:
    """Changing lifecycle_state post-build must fail step 6 — pack_digest covers all manifest fields."""
    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "packs"
    output.mkdir()
    ctx, _ = build_pack(
        package="test-lib",
        version="1.0.0",
        source=_fixture_path(),
        output=output,
    )
    # Tamper the manifest inside the archive by changing lifecycle_state
    with zipfile.ZipFile(ctx, "r") as zf:
        manifest_raw = zf.read("manifest.json")
        entries = {name: zf.read(name) for name in zf.namelist()}
    manifest = json.loads(manifest_raw)
    manifest["lifecycle_state"] = "approved"  # was "draft"
    tampered_ctx = tmp_path / "tampered_manifest.ctx"
    _create_zip_with_entries(
        tampered_ctx,
        {
            "manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode(),
            **{k: v for k, v in entries.items() if k != "manifest.json"},
        },
    )
    policy = Policy.default()
    result = verify(tampered_ctx, policy)
    assert result.passed is False
    assert result.step == 6, "Step 6 must catch manifest tampering"


# ---------------------------------------------------------------------------
# Additional edge-case / verification_inputs tests
# ---------------------------------------------------------------------------


def test_verify_returns_verify_result_not_raises(tmp_path: Path) -> None:
    """verify() returns VerifyResult for expected failures, never raises."""
    ctx = tmp_path / "not_a_zip.ctx"
    ctx.write_text("not a zip")
    policy = Policy.default()
    result = verify(ctx, policy)
    assert isinstance(result, VerifyResult)
    assert result.passed is False


def test_step2_rejects_wrong_type(tmp_path: Path) -> None:
    """Manifest with chunks as a string is rejected at step 2."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest(chunks="bad")
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "chunks.jsonl": b'{"id":1,"content":"hello"}\n',
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 2


def test_step2_rejects_bad_lifecycle_enum(tmp_path: Path) -> None:
    """Manifest with lifecycle_state 'active' (not in enum) is rejected at step 2."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest(lifecycle_state="active")
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "chunks.jsonl": b'{"id":1,"content":"hello"}\n',
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    policy = Policy.default()
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 2


def test_step4_windows_drive_letter_rejected(tmp_path: Path) -> None:
    """Archive entry with Windows drive letter fails at step 4."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "C:/etc/passwd": b"win drive",
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    result = verify(ctx, Policy.load())
    assert result.passed is False
    assert result.step == 4
    assert "absolute" in result.reason.lower()


def test_step4_unc_path_rejected(tmp_path: Path) -> None:
    """Archive entry with UNC path fails at step 4."""
    ctx = tmp_path / "bad.ctx"
    manifest = _make_manifest()
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True).encode(),
            "//server/share/file.txt": b"unc path",
            "chunks.jsonl": b"",
            "pages.json": b"[]",
            "signatures/": b"",
        },
    )
    result = verify(ctx, Policy.load())
    assert result.passed is False
    assert result.step == 4
    assert "absolute" in result.reason.lower()


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "pack_format",
        "package",
        "version",
        "pack_digest",
        "normalized_content_hash",
        "chunks",
        "pages",
        "lifecycle_state",
        "doc_version_status",
        "created_at",
        "created_by",
    ],
)
def test_step2_missing_any_required_field(tmp_path: Path, field: str) -> None:
    """Missing any required manifest field fails at step 2."""
    manifest = _make_manifest()
    del manifest[field]
    ctx = tmp_path / "bad.ctx"
    _create_zip_with_entries(
        ctx,
        {
            "manifest.json": json.dumps(manifest).encode(),
            "chunks.jsonl": b'{"id":1,"content":"x","page_id":1,"heading_path":"h","summary":"s","token_count":1,"source_url":"a.md"}\n',
            "pages.json": b'[{"id":1,"package":"p","version":"1.0","url":"a.md","title":"T","content_hash":"sha256:'
            + b"a" * 64
            + b'"}]',
            "signatures/": b"",
        },
    )
    policy = Policy(
        require_signatures=False,
        require_attribution=False,
        allowed_lifecycle_states=["draft", "approved", "deprecated", "revoked"],
        rejected_doc_version_statuses=[],
    )
    result = verify(ctx, policy)
    assert result.passed is False
    assert result.step == 2
