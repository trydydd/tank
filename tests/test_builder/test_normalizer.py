import unicodedata

from synd.builder.normalizer import normalize


def test_collapse_blank_lines() -> None:
    result = normalize("hello\n\n\n\nworld")
    assert result == "hello\n\nworld"

    multi = "line1\n\n\n\n\n\nline2"
    assert normalize(multi) == "line1\n\nline2"

    assert normalize("para1\n   \n   \npara2") == "para1\n\npara2"
    assert normalize("para1\n\t\n\npara2") == "para1\n\npara2"


def test_strip_html_tags() -> None:
    result = normalize("Hello <b>world</b>")
    assert result == "Hello world"

    nested = "text <a href='#'>link</a> end"
    assert normalize(nested) == "text link end"


def test_normalize_unicode_whitespace() -> None:
    result = normalize("hello world")
    assert result == "hello world"


def test_preserve_fenced_code_blocks() -> None:
    before = "prose\n\n```\n  x = 1  \n  y = 2  \n```\n\nmore prose"
    result = normalize(before)
    assert "\n  x = 1  \n  y = 2  \n" in result


def test_preserve_tables() -> None:
    line = "| Col1 | Col2 |\n|------|------|\n| A    | B    |"
    result = normalize(line)
    assert result == line


def test_strip_leading_trailing_whitespace() -> None:
    result = normalize("  hello world  ")
    assert result == "hello world"


def test_unicode_nfc_normalization() -> None:
    # Construct NFD form of "naiveÇ" programmatically (the literal is NFC)
    nfd = unicodedata.normalize("NFD", "naiveÇ")
    assert nfd != "naiveÇ"  # verify input is actually NFD
    result = normalize(nfd)
    assert result == "naiveÇ"  # NFC form


def test_mixed_prose_and_code() -> None:
    content = "Before code.\n\n```\n  whitespace  preserved  \n```\n\nAfter code."
    result = normalize(content)
    assert "Before code." in result
    assert "\n  whitespace  preserved  \n" in result
    assert "After code." in result


def test_nested_code_fences() -> None:
    content = "outer\n\n```\n```\n\nend"
    result = normalize(content)
    assert "outer" in result
    assert "end" in result


def test_empty_input() -> None:
    assert normalize("") == ""
    assert normalize("\n\n") == ""


def test_all_code_input() -> None:
    content = "```\ndef foo():\n    pass\n```"
    result = normalize(content)
    assert result == content


def test_deterministic_output() -> None:
    content = "hello   world\n\n\n\n<tag>text</tag>\n\n```\ncode  \n```"
    result1 = normalize(content)
    result2 = normalize(result1)
    assert result1 == result2
