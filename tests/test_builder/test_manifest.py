import json
import tempfile
import zipfile
from pathlib import Path

from synd.builder.manifest import (
    build_manifest,
    compute_normalized_content_hash,
    compute_pack_digest,
)


class TestBuildManifest:
    def test_build_manifest_required_fields(self) -> None:
        manifest = build_manifest(
            package="my-lib",
            version="1.0.0",
            chunks_count=10,
            pages_count=3,
            normalized_content_hash="sha256:abc123",
            lifecycle="draft",
            doc_version_status="stable",
            owner=None,
            policy_profile=None,
            source_url="docs",
            source_commit=None,
        )
        assert manifest["schema_version"] == 2
        assert manifest["pack_format"] == "synd-text-v1"
        assert manifest["package"] == "my-lib"
        assert manifest["version"] == "1.0.0"
        assert manifest["chunks"] == 10
        assert manifest["pages"] == 3
        assert manifest["lifecycle_state"] == "draft"
        assert manifest["doc_version_status"] == "stable"
        assert manifest["source_url"] == "docs"
        assert manifest["created_by"] == "synd/0.1.1"
        # Optional fields should not be present when None
        assert "owner" not in manifest
        assert "policy_profile" not in manifest
        assert "source_commit" not in manifest

    def test_build_manifest_optional_fields(self) -> None:
        manifest = build_manifest(
            package="my-lib",
            version="1.0.0",
            chunks_count=10,
            pages_count=3,
            normalized_content_hash="sha256:abc123",
            lifecycle="approved",
            doc_version_status="stable",
            owner="platform-team",
            policy_profile="internal-strict",
            source_url="docs",
            source_commit="abc123",
        )
        assert manifest["owner"] == "platform-team"
        assert manifest["policy_profile"] == "internal-strict"
        assert manifest["source_commit"] == "abc123"

    def test_build_manifest_doc_version_status_prerelease(self) -> None:
        manifest = build_manifest(
            package="my-lib",
            version="2.0.0-beta",
            chunks_count=5,
            pages_count=2,
            normalized_content_hash="sha256:abc123",
            lifecycle="draft",
            doc_version_status="prerelease",
            owner=None,
            policy_profile=None,
            source_url="docs",
            source_commit=None,
        )
        assert manifest["doc_version_status"] == "prerelease"

    def test_build_manifest_doc_version_status_archived(self) -> None:
        manifest = build_manifest(
            package="my-lib",
            version="0.9.0",
            chunks_count=5,
            pages_count=2,
            normalized_content_hash="sha256:abc123",
            lifecycle="deprecated",
            doc_version_status="archived",
            owner=None,
            policy_profile=None,
            source_url="docs",
            source_commit=None,
        )
        assert manifest["doc_version_status"] == "archived"

    def test_build_manifest_doc_version_status_unknown(self) -> None:
        manifest = build_manifest(
            package="my-lib",
            version="1.0.0",
            chunks_count=5,
            pages_count=2,
            normalized_content_hash="sha256:abc123",
            lifecycle="draft",
            doc_version_status="unknown",
            owner=None,
            policy_profile=None,
            source_url="docs",
            source_commit=None,
        )
        assert manifest["doc_version_status"] == "unknown"

    def test_build_manifest_doc_version_status_passed_through(self) -> None:
        """doc_version_status is taken from the parameter, not hardcoded."""
        for status in ("stable", "prerelease", "archived", "unknown"):
            manifest = build_manifest(
                package="my-lib",
                version="1.0.0",
                chunks_count=1,
                pages_count=1,
                normalized_content_hash="sha256:abc123",
                lifecycle="draft",
                doc_version_status=status,
                owner=None,
                policy_profile=None,
                source_url="docs",
                source_commit=None,
            )
            assert manifest["doc_version_status"] == status, (
                f"expected {status!r}, got {manifest['doc_version_status']!r}"
            )


class TestComputePackDigest:
    def test_compute_pack_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            archive = path / "test.ctx"
            # Create a simple zip with a manifest
            manifest = {
                "package": "x",
                "version": "1.0",
                "pack_digest": "sha256:original",
            }
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(
                    "manifest.json", json.dumps(manifest, indent=2, sort_keys=True)
                )
                zf.writestr("chunks.jsonl", "")
                zf.writestr("pages.json", "[]")
            digest = compute_pack_digest(archive)
            assert digest.startswith("sha256:")
            assert len(digest) > len("sha256:")


class TestComputeNormalizedContentHash:
    def test_compute_normalized_content_hash(self) -> None:
        class FakeChunk:
            def __init__(self, cid: int, content: str) -> None:
                self.id = cid
                self.content = content

        chunks = [
            FakeChunk(2, "hello   world"),
            FakeChunk(1, "  foo  "),
        ]
        result = compute_normalized_content_hash(
            chunks, lambda c: c.strip().replace("   ", " ")
        )
        assert result.startswith("sha256:")
        # Deterministic: same chunks in any order should produce same hash
        chunks2 = [
            FakeChunk(1, "  foo  "),
            FakeChunk(2, "hello   world"),
        ]
        result2 = compute_normalized_content_hash(
            chunks2, lambda c: c.strip().replace("   ", " ")
        )
        assert result == result2

    def test_pack_digest_empty_string_zeroing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            archive = path / "test.ctx"
            # Create archive with a non-empty pack_digest
            manifest = {
                "package": "x",
                "version": "1.0",
                "pack_digest": "sha256:deadbeef",
            }
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(
                    "manifest.json", json.dumps(manifest, indent=2, sort_keys=True)
                )
                zf.writestr("chunks.jsonl", "")
                zf.writestr("pages.json", "[]")

            # Verify: zeroing the manifest and re-hashing should produce a digest
            digest = compute_pack_digest(archive)
            assert digest.startswith("sha256:")
            # The digest should NOT be "sha256:deadbeef"
            assert digest != "sha256:deadbeef"
