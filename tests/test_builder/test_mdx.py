from synd.builder.mdx import (
    clean_heading,
    process_mdx,
    strip_mdx,
    unwrap_jsx_blocks,
)


# --- strip_mdx ---


def test_strip_mdx_removes_import_lines() -> None:
    raw = "import X from 'y'\n# Title\n"
    assert "import X" not in strip_mdx(raw)
    assert "# Title" in strip_mdx(raw)


def test_strip_mdx_keeps_markdown_code_fences() -> None:
    raw = "import X from 'y'\n# Title\n```python\nprint('ok')\n```\n"
    cleaned = strip_mdx(raw)
    assert "import X" not in cleaned
    assert "```python" in cleaned
    assert "print('ok')" in cleaned


def test_strip_mdx_removes_self_closing_component_lines() -> None:
    raw = "# Title\n<FeatureBadge />\nSome prose.\n"
    cleaned = strip_mdx(raw)
    assert "<FeatureBadge" not in cleaned
    assert "Some prose." in cleaned


def test_strip_mdx_unwraps_backtick_expression() -> None:
    raw = "Value is {`hello`}."
    assert "hello" in strip_mdx(raw)
    assert "{`" not in strip_mdx(raw)


# --- unwrap_jsx_blocks ---


def test_unwrap_note_block_keeps_inner_text() -> None:
    raw = "<Note>This is a note.</Note>"
    result = unwrap_jsx_blocks(raw)
    assert "This is a note." in result
    assert "<Note>" not in result


def test_unwrap_warning_block() -> None:
    raw = "<Warning>Be careful!</Warning>"
    result = unwrap_jsx_blocks(raw)
    assert "Be careful!" in result
    assert "<Warning>" not in result


def test_unwrap_tip_block() -> None:
    raw = "<Tip>Pro tip: use this.</Tip>"
    result = unwrap_jsx_blocks(raw)
    assert "Pro tip: use this." in result
    assert "<Tip>" not in result


def test_unwrap_tab_block_with_attribute() -> None:
    raw = '<Tab title="Python">```python\nprint(1)\n```</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "print(1)" in result
    assert "<Tab" not in result


def test_unwrap_tabs_containing_tab_children() -> None:
    raw = "<Tabs>\n<Tab title='A'>alpha</Tab>\n<Tab title='B'>beta</Tab>\n</Tabs>"
    result = unwrap_jsx_blocks(raw)
    assert "alpha" in result
    assert "beta" in result
    assert "<Tabs>" not in result
    assert "<Tab" not in result


def test_discard_frame_image() -> None:
    raw = "<Frame>\n<img src='diagram.png' />\n</Frame>"
    result = unwrap_jsx_blocks(raw)
    assert "diagram.png" not in result
    assert "<Frame>" not in result


def test_frame_with_text_content_keeps_text() -> None:
    raw = "<Frame>\nSome caption text.\n</Frame>"
    result = unwrap_jsx_blocks(raw)
    assert "Some caption text." in result


def test_unwrap_tab_dedents_4space_indented_body() -> None:
    # Mintlify pattern: Tab body is 4-space indented in the MDX source.
    # After unwrapping, headings and prose must be at column 0 so that
    # markdown-it-py parses them as heading/paragraph tokens, not code_block.
    raw = '<Tab title="Python">\n    ## System Requirements\n\n    Install with pip.\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "## System Requirements" in result
    assert "    ## System Requirements" not in result
    assert "Install with pip." in result


def test_unwrap_tab_dedents_2space_indented_body() -> None:
    # 2-space indented Tab content must not have content characters stripped.
    raw = '<Tab title="TS">\n  ## Setup\n\n  Run npm install.\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "## Setup" in result
    assert "  ## Setup" not in result
    assert "Run npm install." in result


def test_unwrap_nested_tabs_dedents_inner_content() -> None:
    raw = '<Tabs>\n<Tab title="A">\n    alpha content\n</Tab>\n<Tab title="B">\n    beta content\n</Tab>\n</Tabs>'
    result = unwrap_jsx_blocks(raw)
    assert "alpha content" in result
    assert "beta content" in result
    assert "    alpha content" not in result


# --- Tab heading disambiguation ---


def test_tab_injects_title_heading_for_h3_body() -> None:
    raw = (
        '<Tab title="Python">\n### Implementing tool execution\n\nSome content.\n</Tab>'
    )
    result = unwrap_jsx_blocks(raw)
    assert "## Python" in result
    assert "#### Implementing tool execution" in result
    assert "<Tab" not in result


def test_tab_injects_title_heading_for_h2_body() -> None:
    raw = '<Tab title="TypeScript">\n## Setup\n\nContent.\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "# TypeScript" in result
    assert "### Setup" in result
    assert "<Tab" not in result


def test_tab_no_title_attribute_falls_back_to_plain_dedent() -> None:
    raw = "<Tab>\n### A heading\n\nsome content\n</Tab>"
    result = unwrap_jsx_blocks(raw)
    assert "### A heading" in result
    assert "<Tab" not in result
    # No extra heading injected — result should start directly with the body content
    assert result.strip().startswith("### A heading")


def test_tab_body_no_headings_injects_h3_title() -> None:
    raw = '<Tab title="Go">\nsome prose without headings\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "### Go" in result
    assert "some prose without headings" in result


def test_tab_body_h6_heading_shift_is_noop() -> None:
    raw = '<Tab title="Rust">\n###### Deep heading\n\ncontent\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "##### Rust" in result
    assert "###### Deep heading" in result


def test_tabs_container_not_title_injected() -> None:
    raw = "<Tabs>\nsome content\n</Tabs>"
    result = unwrap_jsx_blocks(raw)
    assert "<Tabs>" not in result
    assert "## Tabs" not in result
    assert "### Tabs" not in result


def test_note_block_not_title_injected() -> None:
    raw = "<Note>\n### A heading\n</Note>"
    result = unwrap_jsx_blocks(raw)
    assert "<Note>" not in result
    assert "## Note" not in result
    assert "### A heading" in result


def test_tab_title_with_special_markdown_chars() -> None:
    raw = '<Tab title="C#">\n### A heading\n\ncontent\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    assert "## C#" in result
    assert "#### A heading" in result


# --- _extract_code_fences ---


def test_extract_code_fences_normalises_indented_closer() -> None:
    # A fence with 4-space-indented closing ``` (Mintlify Tab body pattern).
    # The restored fence must have the closer at column 0 so that markdown-it-py
    # recognises it as a valid CommonMark fence closer (max 3 leading spaces).
    from synd.builder.mdx import _extract_code_fences

    raw = "    ```python\n    code line\n    ```"
    masked, fences = _extract_code_fences(raw)
    assert len(fences) == 1
    # Closing ``` must be at column 0 in the stored fence
    closing_line = fences[0].splitlines()[-1]
    assert not closing_line.startswith(" "), f"Closing still indented: {closing_line!r}"
    assert closing_line.startswith("```")


# --- clean_heading ---


def test_clean_heading_strips_sup_anchor() -> None:
    line = '## ClassName <sup><a href="#ref"><Icon /></a></sup>'
    assert clean_heading(line) == "## ClassName"


def test_clean_heading_noop_on_plain_heading() -> None:
    line = "## Plain Heading"
    assert clean_heading(line) == "## Plain Heading"


def test_clean_heading_noop_on_non_heading_line() -> None:
    line = "Some prose with <sup>footnote</sup>."
    assert clean_heading(line) == line


def test_clean_heading_strips_trailing_whitespace() -> None:
    line = "# Title   "
    assert clean_heading(line) == "# Title"


# --- process_mdx ---


def test_process_mdx_preserves_fences() -> None:
    raw = "# Title\n\n```python\nimport foo\n```\n"
    result = process_mdx(raw)
    assert "```python" in result
    assert "import foo" in result


def test_process_mdx_unwraps_note_and_cleans_heading() -> None:
    raw = (
        "## API <sup><a href='#api'><Icon /></a></sup>\n\n<Note>Read the docs.</Note>\n"
    )
    result = process_mdx(raw)
    assert "## API" in result
    assert "<sup>" not in result
    assert "Read the docs." in result
    assert "<Note>" not in result


def test_process_mdx_removes_imports() -> None:
    raw = "import Foo from 'bar'\n\n# Title\n\nContent.\n"
    result = process_mdx(raw)
    assert "import Foo" not in result
    assert "# Title" in result
    assert "Content." in result


def test_process_mdx_collapses_blank_lines() -> None:
    raw = "# Title\n\n\n\n\nContent.\n"
    result = process_mdx(raw)
    assert "\n\n\n" not in result


def test_process_mdx_tab_language_disambiguation() -> None:
    raw = (
        "## Building your server\n\n"
        "<Tabs>\n"
        '<Tab title="Python">\n\n'
        "### Implementing tool execution\n\n"
        "Python content here.\n\n"
        "</Tab>\n"
        '<Tab title="TypeScript">\n\n'
        "### Implementing tool execution\n\n"
        "TypeScript content here.\n\n"
        "</Tab>\n"
        "</Tabs>\n"
    )
    result = process_mdx(raw)
    assert "## Python" in result
    assert "## TypeScript" in result
    lines_with_impl = [
        line for line in result.splitlines() if "Implementing tool execution" in line
    ]
    assert len(lines_with_impl) == 2
    for line in lines_with_impl:
        assert line.startswith("####"), f"Expected ####, got: {line!r}"
