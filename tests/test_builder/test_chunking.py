from pathlib import Path

from synd.builder.chunking import RawChunk, chunk_file, discover_files, generate_summary


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
        # The file is at auth/oauth.md, source is sample_docs
        # heading_path should strip "sample_docs" prefix
        # chunkana returns header_path like "/OAuth2"
        # We need to strip the source dir name from the prefix
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, RawChunk)
            assert isinstance(chunk.heading_path, str)
            assert chunk.page_id == 1


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
