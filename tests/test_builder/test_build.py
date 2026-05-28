import json
import zipfile
from pathlib import Path
from unittest.mock import patch

from synd.builder.build import build_pack, build_pack_from_url
from synd.builder.llms_full import LlmsFullPage
from synd.errors import BuildError


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


def _build(tmp_path: Path, source: Path | None = None) -> Path:
    src = source or _fixture_path()
    output = tmp_path / "packs"
    return build_pack(
        package="test-lib",
        version="1.0.0",
        source=src,
        output=output,
    )


def test_build_produces_valid_ctx(tmp_path: Path) -> None:
    ctx_path = _build(tmp_path)
    assert ctx_path.exists()
    assert ctx_path.suffix == ".ctx"

    with zipfile.ZipFile(ctx_path, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "chunks.jsonl" in names
        assert "pages.json" in names
        assert "signatures/" in names

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["package"] == "test-lib"
        assert manifest["version"] == "1.0.0"
        assert manifest["pack_digest"].startswith("sha256:")
        assert manifest["normalized_content_hash"].startswith("sha256:")
        assert manifest["schema_version"] == 2
        assert manifest["pack_format"] == "synd-text-v1"


def test_build_deterministic_hash(tmp_path: Path) -> None:
    output1 = tmp_path / "out1"
    output1.mkdir()
    hash1 = _build_with_output(tmp_path / "out1")

    output2 = tmp_path / "out2"
    output2.mkdir()
    hash2 = _build_with_output(tmp_path / "out2")

    with zipfile.ZipFile(hash1, "r") as zf1:
        m1 = json.loads(zf1.read("manifest.json"))
    with zipfile.ZipFile(hash2, "r") as zf2:
        m2 = json.loads(zf2.read("manifest.json"))

    assert m1["normalized_content_hash"] == m2["normalized_content_hash"]


def _build_with_output(output: Path) -> Path:
    return build_pack(
        package="test-lib",
        version="1.0.0",
        source=_fixture_path(),
        output=output,
    )


def test_build_source_url_relative_paths(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "intro.md").write_text("# Intro\nHello world.\n")
    sub = docs / "auth"
    sub.mkdir()
    (sub / "oauth.md").write_text("# OAuth2\nOAuth setup guide.\n")

    import os

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ctx_path = build_pack(
            package="test-lib",
            version="1.0.0",
            source=Path("./docs"),
            output=tmp_path / "packs",
        )
    finally:
        os.chdir(old_cwd)

    with zipfile.ZipFile(ctx_path, "r") as zf:
        chunks_text = zf.read("chunks.jsonl").decode("utf-8")
        for line in chunks_text.strip().split("\n"):
            record = json.loads(line)
            url = record["source_url"]
            assert url is not None
            assert not url.startswith("./"), (
                f"source_url should not start with './': {url}"
            )
            assert url.startswith("docs/"), (
                f"source_url must include source dir name: {url}"
            )

        pages = json.loads(zf.read("pages.json"))
        for page in pages:
            assert page["url"].startswith("docs/"), (
                f"page url must include source dir name: {page['url']}"
            )


def test_build_nonexistent_source_raises(tmp_path: Path) -> None:
    source = tmp_path / "does_not_exist"
    output = tmp_path / "packs"
    output.mkdir()
    try:
        build_pack(
            package="test-lib",
            version="1.0.0",
            source=source,
            output=output,
        )
    except BuildError as e:
        assert "does not exist" in str(e)
    else:
        assert False, "Expected BuildError"


def test_source_url_does_not_strip_source_dir_name(tmp_path: Path) -> None:
    """D4: source_url must include the --source directory name."""
    docs = tmp_path / "docs"
    docs.mkdir()
    auth = docs / "auth"
    auth.mkdir()
    (auth / "oauth.md").write_text("# OAuth2\nSetup guide.\n")

    import os

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ctx_path = build_pack(
            package="test-lib",
            version="1.0.0",
            source=Path("./docs"),
            output=tmp_path / "packs",
        )
    finally:
        os.chdir(old_cwd)

    with zipfile.ZipFile(ctx_path, "r") as zf:
        chunks_text = zf.read("chunks.jsonl").decode("utf-8")
        for line in chunks_text.strip().split("\n"):
            record = json.loads(line)
            assert not record["source_url"].startswith("auth/"), (
                "source_url must not strip the source dir name"
            )


def test_build_empty_source_raises(tmp_path: Path) -> None:
    source = tmp_path / "empty_source"
    source.mkdir()
    output = tmp_path / "packs"
    output.mkdir()
    try:
        build_pack(
            package="test-lib",
            version="1.0.0",
            source=source,
            output=output,
        )
    except BuildError as e:
        assert "No documentation files" in str(e)
    else:
        assert False, "Expected BuildError"


def test_build_doc_version_status_passed_through(tmp_path: Path) -> None:
    """doc_version_status parameter is written to the manifest."""
    source = _fixture_path()
    for status in ("stable", "prerelease", "archived", "unknown"):
        output = tmp_path / f"packs_{status}"
        ctx_path = build_pack(
            package="test-lib",
            version="1.0.0",
            source=source,
            output=output,
            doc_version_status=status,
        )
        with zipfile.ZipFile(ctx_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["doc_version_status"] == status, (
            f"expected {status!r}, got {manifest['doc_version_status']!r}"
        )


def test_build_doc_version_status_defaults_to_stable(tmp_path: Path) -> None:
    """Omitting doc_version_status produces 'stable' in the manifest."""
    ctx_path = _build(tmp_path)
    with zipfile.ZipFile(ctx_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["doc_version_status"] == "stable"


def test_source_urls_use_forward_slashes(tmp_path: Path) -> None:
    """All source_url values in a built pack must use forward slashes only."""
    ctx_path = _build(tmp_path)
    with zipfile.ZipFile(ctx_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        chunks_lines = zf.read("chunks.jsonl").decode()
        pages = json.loads(zf.read("pages.json"))

    # manifest source_url
    assert "\\" not in (manifest.get("source_url") or ""), (
        f"manifest source_url contains backslash: {manifest.get('source_url')}"
    )

    # chunk source_urls
    for line in chunks_lines.strip().split("\n"):
        if not line:
            continue
        chunk = json.loads(line)
        assert "\\" not in (chunk.get("source_url") or ""), (
            f"chunk source_url contains backslash: {chunk.get('source_url')}"
        )

    # page urls
    for page in pages:
        assert "\\" not in (page.get("url") or ""), (
            f"page url contains backslash: {page.get('url')}"
        )


def test_discover_files_sorted_by_forward_slash_path(tmp_path: Path) -> None:
    """discover_files returns files sorted by their forward-slash relative path."""
    from synd.builder.chunking import discover_files

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "z_file.md").write_text("# Z\n")
    sub = docs / "a_sub"
    sub.mkdir()
    (sub / "first.md").write_text("# First\n")
    result = discover_files(docs)
    # "a_sub/first.md" sorts before "z_file.md" in forward-slash lexicographic order
    assert len(result) == 2
    rel_paths = [p.relative_to(docs).as_posix() for p in result]
    assert rel_paths == sorted(rel_paths), f"Not sorted: {rel_paths}"


# --- build_pack_from_url ---

_FAKE_LLMS_TXT_PAGES = [
    (
        "https://docs.example.com/intro.md",
        "# Introduction\n\nWelcome to the library.\n",
    ),
    (
        "https://docs.example.com/api.md",
        "# API Reference\n\nUse `client.get()` to fetch data.\n",
    ),
]

_FAKE_LLMS_FULL_PAGES = [
    LlmsFullPage(
        url="https://docs.example.com/intro.md", content="# Introduction\n\nWelcome.\n"
    ),
    LlmsFullPage(
        url="https://docs.example.com/api.md",
        content="# API Reference\n\nDetails here.\n",
    ),
]


def test_build_pack_from_url_llms_txt_produces_valid_ctx(tmp_path: Path) -> None:
    with patch("synd.builder.build.fetch_pages", return_value=_FAKE_LLMS_TXT_PAGES):
        ctx_path = build_pack_from_url(
            package="test-lib",
            version="1.0.0",
            source_url="https://docs.example.com/llms.txt",
            output=tmp_path / "packs",
        )

    assert ctx_path.exists()
    assert ctx_path.suffix == ".ctx"
    with zipfile.ZipFile(ctx_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["package"] == "test-lib"
        assert manifest["version"] == "1.0.0"
        assert manifest["pack_digest"].startswith("sha256:")
        assert manifest["source_url"] == "https://docs.example.com/llms.txt"


def test_build_pack_from_url_llms_full_txt_produces_valid_ctx(tmp_path: Path) -> None:
    with patch(
        "synd.builder.build.fetch_llms_full_pages", return_value=_FAKE_LLMS_FULL_PAGES
    ):
        ctx_path = build_pack_from_url(
            package="test-lib",
            version="1.0.0",
            source_url="https://docs.example.com/llms-full.txt",
            output=tmp_path / "packs",
        )

    assert ctx_path.exists()
    with zipfile.ZipFile(ctx_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["source_url"] == "https://docs.example.com/llms-full.txt"


def test_build_pack_from_url_chunk_source_url_is_page_url(tmp_path: Path) -> None:
    with patch("synd.builder.build.fetch_pages", return_value=_FAKE_LLMS_TXT_PAGES):
        ctx_path = build_pack_from_url(
            package="test-lib",
            version="1.0.0",
            source_url="https://docs.example.com/llms.txt",
            output=tmp_path / "packs",
        )

    with zipfile.ZipFile(ctx_path) as zf:
        chunks = [
            json.loads(ln)
            for ln in zf.read("chunks.jsonl").decode().strip().split("\n")
        ]
    urls = {c["source_url"] for c in chunks}
    assert "https://docs.example.com/intro.md" in urls
    assert "https://docs.example.com/api.md" in urls


def test_build_pack_from_url_page_url_is_full_url(tmp_path: Path) -> None:
    with patch("synd.builder.build.fetch_pages", return_value=_FAKE_LLMS_TXT_PAGES):
        ctx_path = build_pack_from_url(
            package="test-lib",
            version="1.0.0",
            source_url="https://docs.example.com/llms.txt",
            output=tmp_path / "packs",
        )

    with zipfile.ZipFile(ctx_path) as zf:
        pages = json.loads(zf.read("pages.json"))
    page_urls = {p["url"] for p in pages}
    assert "https://docs.example.com/intro.md" in page_urls


def test_build_pack_from_url_heading_path_uses_url_stem(tmp_path: Path) -> None:
    with patch("synd.builder.build.fetch_pages", return_value=_FAKE_LLMS_TXT_PAGES):
        ctx_path = build_pack_from_url(
            package="test-lib",
            version="1.0.0",
            source_url="https://docs.example.com/llms.txt",
            output=tmp_path / "packs",
        )

    with zipfile.ZipFile(ctx_path) as zf:
        chunks = [
            json.loads(ln)
            for ln in zf.read("chunks.jsonl").decode().strip().split("\n")
        ]
    prefixes = {c["heading_path"].split(" / ")[0] for c in chunks}
    assert "intro" in prefixes
    assert "api" in prefixes


def test_build_pack_from_url_unsupported_url_raises(tmp_path: Path) -> None:
    try:
        build_pack_from_url(
            package="test-lib",
            version="1.0.0",
            source_url="https://docs.example.com/README.md",
            output=tmp_path / "packs",
        )
    except BuildError as exc:
        assert "Unsupported URL source" in str(exc)
    else:
        assert False, "Expected BuildError"


def test_build_pack_from_url_no_pages_raises(tmp_path: Path) -> None:
    with patch("synd.builder.build.fetch_pages", return_value=[]):
        try:
            build_pack_from_url(
                package="test-lib",
                version="1.0.0",
                source_url="https://docs.example.com/llms.txt",
                output=tmp_path / "packs",
            )
        except BuildError as exc:
            assert "No pages" in str(exc)
        else:
            assert False, "Expected BuildError"
