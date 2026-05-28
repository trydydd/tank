from pathlib import Path

import pytest

from synd.builder.chunking import (
    RawChunk,
    chunk_content,
    chunk_file,
    discover_files,
    generate_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(heading_path: str, content: str, page_id: int = 1) -> RawChunk:
    return RawChunk(
        heading_path=heading_path, content=content, source_url="x.md", page_id=page_id
    )


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestDiscoverFiles:
    def test_discover_files_lexicographic_order(self) -> None:
        source = _fixture_path()
        files = discover_files(source)
        relative = [f.relative_to(source) for f in files]
        paths = [str(p) for p in relative]
        assert paths == sorted(paths)

    def test_discover_files_extension_whitelist(self) -> None:
        source = _fixture_path()
        files = discover_files(source)
        for f in files:
            suffix = f.suffix.lower()
            assert suffix in (".md", ".html", ".htm")

    def test_discover_files_recursive(self) -> None:
        source = _fixture_path()
        files = discover_files(source)
        relative_names = {f.name for f in files}
        # config.md is top-level, api/endpoints.md is nested
        assert "config.md" in relative_names
        assert "endpoints.md" in relative_names

    def test_discover_files_does_not_include_non_whitelisted(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "docs"
        source.mkdir()
        (source / "readme.md").write_text("# README\n")
        (source / "page.html").write_text("<h1>Page</h1>\n")
        (source / "index.htm").write_text("<h1>Index</h1>\n")
        (source / "diagram.png").write_bytes(b"\x89PNG")
        (source / "notes.txt").write_text("notes")
        (source / "script.py").write_text("print('hi')")
        files = discover_files(source)
        suffixes = {f.suffix.lower() for f in files}
        assert ".png" not in suffixes
        assert ".txt" not in suffixes
        assert ".py" not in suffixes
        assert len(files) == 3

    def test_chunk_ids_not_filesystem_dependent(self, tmp_path: Path) -> None:
        source = tmp_path / "docs"
        source.mkdir()
        (source / "z_last.md").write_text("# Z Last\nContent Z.\n")
        (source / "a_first.md").write_text("# A First\nContent A.\n")
        (source / "m_middle.md").write_text("# M Middle\nContent M.\n")
        files = discover_files(source)
        relative = [str(f.relative_to(source)) for f in files]
        assert relative == ["a_first.md", "m_middle.md", "z_last.md"]


class TestChunkFile:
    def test_chunk_file_heading_path_construction(self) -> None:
        source = _fixture_path()
        file_path = source / "auth" / "oauth.md"
        chunks = chunk_file(file_path, source, page_id=1)
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, RawChunk)
            assert isinstance(chunk.heading_path, str)
            assert chunk.page_id == 1

    def test_oauth_fixture_heading_path_includes_all_ancestors(self) -> None:
        source = _fixture_path()
        file_path = source / "auth" / "oauth.md"
        chunks = chunk_file(file_path, source, page_id=1)
        paths = [c.heading_path for c in chunks]
        assert any("Client Credentials" in p for p in paths)
        assert any("Authorization Code" in p for p in paths)
        # H2 sections must include the H1 ancestor
        client_creds = next(c for c in chunks if "Client Credentials" in c.heading_path)
        assert "OAuth2" in client_creds.heading_path
        auth_code = next(c for c in chunks if "Authorization Code" in c.heading_path)
        assert "OAuth2" in auth_code.heading_path


class TestChunkContent:
    def test_preamble_chunk_uses_prefix_as_heading_path(self) -> None:
        content = "Intro text before any heading.\n"
        chunks = chunk_content(
            content,
            heading_prefix="guide/intro",
            source_url="guide/intro.md",
            page_id=1,
        )
        assert len(chunks) == 1
        assert chunks[0].heading_path == "guide/intro"

    def test_single_h1_no_preamble(self) -> None:
        content = "# Title\n\nContent under H1.\n"
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert chunks[0].heading_path == "doc / Title"

    def test_h2_section_includes_h1_ancestor(self) -> None:
        content = "# Title\n\n## Section\n\nContent.\n"
        chunks = chunk_content(
            content, heading_prefix="auth/oauth", source_url="auth/oauth.md", page_id=1
        )
        h2_chunk = next(c for c in chunks if "Section" in c.heading_path)
        assert h2_chunk.heading_path == "auth/oauth / Title / Section"

    def test_h3_section_includes_h1_and_h2_ancestors(self) -> None:
        content = "# Doc\n\n## Parent\n\n### Child\n\nDeep content.\n"
        chunks = chunk_content(
            content, heading_prefix="docs/guide", source_url="docs/guide.md", page_id=1
        )
        h3_chunk = next(c for c in chunks if "Child" in c.heading_path)
        assert h3_chunk.heading_path == "docs/guide / Doc / Parent / Child"

    def test_sibling_h3_pops_previous_h3(self) -> None:
        content = (
            "# Doc\n\n## Parent\n\n### First\n\nContent.\n\n### Second\n\nContent.\n"
        )
        chunks = chunk_content(
            content, heading_prefix="guide", source_url="guide.md", page_id=1
        )
        second = next(c for c in chunks if "Second" in c.heading_path)
        assert second.heading_path == "guide / Doc / Parent / Second"
        assert "First" not in second.heading_path

    def test_h2_after_h3_pops_h3_from_stack(self) -> None:
        content = "# Doc\n\n## A\n\n### A1\n\nContent.\n\n## B\n\nContent.\n"
        chunks = chunk_content(
            content, heading_prefix="prefix", source_url="x.md", page_id=1
        )
        b_chunk = next(c for c in chunks if c.heading_path.endswith("/ B"))
        assert b_chunk.heading_path == "prefix / Doc / B"
        assert "A1" not in b_chunk.heading_path

    def test_code_fence_is_atomic_not_split(self, tmp_path: Path) -> None:
        # A section that exceeds max_chunk_tokens but contains a fence — never split mid-fence
        fence_body = "\n".join(f"    line_{i} = {i}" for i in range(200))
        content = f"## Section\n\n```python\n{fence_body}\n```\n"
        chunks = chunk_content(
            content,
            heading_prefix="x",
            source_url="x.md",
            page_id=1,
            max_chunk_tokens=50,
        )
        # The fence body should not be split across chunks
        for chunk in chunks:
            if "line_0" in chunk.content:
                assert "line_199" in chunk.content, "Fence was split across chunks"
                break

    def test_oversized_section_splits_at_paragraph_boundary(self) -> None:
        # Build content whose paragraphs each contribute ~60 tokens (240 chars)
        paras = [f"Para {i}: " + ("word " * 40) for i in range(6)]
        content = "## Section\n\n" + "\n\n".join(paras) + "\n"
        chunks = chunk_content(
            content,
            heading_prefix="x",
            source_url="x.md",
            page_id=1,
            max_chunk_tokens=100,
        )
        assert len(chunks) >= 2
        # Every chunk must share the same heading path
        for chunk in chunks:
            assert "Section" in chunk.heading_path
        # No chunk should exceed 2× the limit (paragraph splits must be happening)
        for chunk in chunks:
            assert len(chunk.content) // 4 <= 200, (
                f"Chunk too large: {len(chunk.content)}"
            )

    def test_no_headings_is_single_chunk(self) -> None:
        content = "Just a paragraph.\n\nAnother paragraph.\n"
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert chunks[0].heading_path == "doc"

    def test_fastmcp_fixture_transport_protocols_split(self) -> None:
        fixture = (
            Path(__file__).parent.parent
            / "benchmarks"
            / "fixtures"
            / "fastmcp-running-server.md"
        )
        content = fixture.read_text(encoding="utf-8")
        chunks = chunk_content(
            content,
            heading_prefix="fastmcp-running-server",
            source_url="fastmcp-running-server.md",
            page_id=1,
        )
        paths = [c.heading_path for c in chunks]
        # The four ### subsections must now be separate chunks
        assert any("STDIO Transport" in p for p in paths), (
            "STDIO Transport chunk missing"
        )
        assert any("SSE Transport" in p for p in paths), "SSE Transport chunk missing"
        assert any("HTTP Transport" in p for p in paths), "HTTP Transport chunk missing"
        # No chunk should have 900+ tokens (the old 932-token multi-section blob)
        for chunk in chunks:
            assert len(chunk.content) // 4 < 900, (
                f"Oversized chunk detected ({len(chunk.content) // 4} tokens): "
                f"{chunk.heading_path[:80]}"
            )

    def test_heading_path_separator(self) -> None:
        content = "# A\n\n## B\n\nContent.\n"
        chunks = chunk_content(
            content, heading_prefix="x", source_url="x.md", page_id=1
        )
        b_chunk = next(c for c in chunks if "B" in c.heading_path)
        assert " / " in b_chunk.heading_path

    def test_source_url_and_page_id_on_every_chunk(self) -> None:
        content = "# A\n\nContent.\n\n## B\n\nMore.\n"
        chunks = chunk_content(
            content, heading_prefix="x", source_url="my/path.md", page_id=42
        )
        assert all(c.source_url == "my/path.md" for c in chunks)
        assert all(c.page_id == 42 for c in chunks)


class TestGenerateSummary:
    def test_generate_summary_prose(self) -> None:
        content = "This function configures OAuth2. It requires a client ID and secret."
        result = generate_summary(content)
        assert result == "This function configures OAuth2."

    def test_generate_summary_code_heavy(self) -> None:
        content = (
            "```python\n"
            "def configure_oauth(client_id: str) -> Config:\n"
            "    pass\n"
            "def another_func() -> None:\n"
            "    pass\n"
            "```"
        )
        result = generate_summary(content)
        assert "def configure_oauth(client_id: str) -> Config:" in result

    def test_generate_summary_truncation(self) -> None:
        long = "This is a very long sentence that goes on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on until it exceeds two hundred characters easily."
        result = generate_summary(long)
        assert len(result) <= 203  # 200 + "..."
        assert result.endswith("...")

    def test_generate_summary_with_heading_path(self) -> None:
        content = "You can now run this MCP server by executing `python my_server.py`."
        result = generate_summary(
            content,
            heading_path="fastmcp / Running Your Server / STDIO Transport (Default)",
        )
        assert result.startswith("STDIO Transport (Default):")

    def test_generate_summary_no_heading_path_fallback(self) -> None:
        content = "This function configures OAuth2. It requires a client ID and secret."
        without = generate_summary(content, heading_path="")
        same = generate_summary(content)
        assert without == same == "This function configures OAuth2."

    def test_generate_summary_preamble_no_prefix(self) -> None:
        # heading_path is just the file prefix — no heading parts — no prefix applied
        content = "Introductory text before any section."
        result = generate_summary(content, heading_path="guide/intro")
        assert result == "Introductory text before any section."
        assert "guide/intro" not in result

    def test_generate_summary_long_heading_returns_heading_only(self) -> None:
        leaf = "A" * 61  # 61 chars > 60 threshold
        content = "Some prose content here."
        result = generate_summary(content, heading_path=f"doc / {leaf}")
        assert result == leaf

    def test_generate_summary_skips_redundant_prefix(self) -> None:
        # If prose already starts with the leaf heading text, don't double it
        leaf = "STDIO Transport"
        content = f"{leaf} is the default transport for FastMCP servers."
        result = generate_summary(content, heading_path=f"doc / {leaf}")
        assert not result.startswith(f"{leaf}: {leaf}")

    def test_generate_summary_heading_line_not_used_as_prose(self) -> None:
        # Chunk content that starts with a markdown heading
        content = "## My Section\n\nThis is the actual description."
        result = generate_summary(content, heading_path="doc / My Section")
        # The heading markdown line should not pollute the prose summary
        assert "##" not in result

    @pytest.mark.parametrize(
        "heading_path,expected_prefix",
        [
            ("doc / Client Credentials", "Client Credentials"),
            ("auth/oauth / OAuth2 / Client Credentials", "Client Credentials"),
        ],
    )
    def test_generate_summary_uses_leaf_not_full_path(
        self, heading_path: str, expected_prefix: str
    ) -> None:
        content = "To use the client credentials flow, provide a client ID."
        result = generate_summary(content, heading_path=heading_path)
        assert result.startswith(f"{expected_prefix}:")
        assert result.count("/") == 0  # full path should not appear in summary


class TestMinTokenMerge:
    """Heading-only stubs are absorbed into the next section inside chunk_content."""

    def test_heading_only_stub_absorbed_into_next(self) -> None:
        # ## A has no prose — stub should be absorbed forward into ## A / B
        content = "## A\n\n### B\n\nReal content for B.\n"
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert chunks[0].heading_path == "doc / A / B"

    def test_stub_heading_text_present_in_merged_content(self) -> None:
        content = (
            "## Authorization\n\n### Introduction\n\nOAuth2 requires a client ID.\n"
        )
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert "## Authorization" in chunks[0].content

    def test_merged_chunk_heading_path_is_deeper_heading(self) -> None:
        content = (
            "## Authorization\n\n### Introduction\n\nOAuth2 requires a client ID.\n"
        )
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert chunks[0].heading_path == "doc / Authorization / Introduction"

    def test_consecutive_stubs_all_absorbed(self) -> None:
        # Three heading-only sections; all absorbed into the final real section
        content = "## A\n\n## B\n\n## C\n\nActual content here.\n"
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert chunks[0].heading_path == "doc / C"
        assert "## A" in chunks[0].content
        assert "## B" in chunks[0].content

    def test_non_stub_section_emitted_normally(self) -> None:
        # Section with enough prose stays as its own chunk
        prose = "word " * 30  # ~120 chars = 30 tokens
        content = f"## Section\n\n{prose}\n\n## Next\n\nMore content.\n"
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 2
        assert any("Section" in c.heading_path for c in chunks)
        assert any("Next" in c.heading_path for c in chunks)

    def test_preamble_stub_absorbed_into_first_section(self) -> None:
        # Short preamble before any heading — below threshold, folds into first section
        content = "Tiny intro.\n\n## Section\n\nSection content here.\n"
        # "Tiny intro." = 3 tokens → below 20 → absorbed into ## Section chunk
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert "Section" in chunks[0].heading_path
        assert "Tiny intro." in chunks[0].content

    def test_all_stubs_page_emits_one_chunk(self) -> None:
        # Page consisting entirely of heading-only lines — must not produce empty result
        content = "# A\n\n## B\n\n### C\n\n#### D\n"
        chunks = chunk_content(
            content, heading_prefix="doc", source_url="doc.md", page_id=1
        )
        assert len(chunks) == 1
        assert chunks[0].content  # not empty

    def test_min_chunk_tokens_zero_disables_merge(self) -> None:
        # min_chunk_tokens=0 means every non-empty chunk is emitted, including stubs
        content = "## A\n\n### B\n\nContent.\n"
        chunks = chunk_content(
            content,
            heading_prefix="doc",
            source_url="doc.md",
            page_id=1,
            min_chunk_tokens=0,
        )
        assert len(chunks) == 2
        stub = next(c for c in chunks if c.heading_path == "doc / A")
        assert stub.content.strip() == "## A"
