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
