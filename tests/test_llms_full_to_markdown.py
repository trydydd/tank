from scripts.llms_full_to_markdown import convert_to_markdown, strip_mdx


def test_strip_mdx_keeps_markdown_code_fences() -> None:
    raw = """import X from 'y'\n# Title\n```python\nprint('ok')\n```\n"""
    cleaned = strip_mdx(raw)
    assert "import X" not in cleaned
    assert "```python" in cleaned
    assert "print('ok')" in cleaned


def test_convert_to_markdown_with_html_lists() -> None:
    raw = """# Heading\n<div><p>Hello <b>world</b></p><ul><li>One</li><li>Two</li></ul></div>"""
    converted = convert_to_markdown(raw)
    assert "# Heading" in converted
    assert "Hello world" in converted
    assert "- One" in converted
    assert "- Two" in converted
