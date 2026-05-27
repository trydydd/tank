import re
import unicodedata


def normalize(content: str) -> str:
    """Normalize chunk content for hashing.

    Rules (prose only — fenced code blocks are preserved verbatim):
      1. Collapse runs of blank lines to a single blank line
      2. Strip HTML tags (basic <[^>]+> removal)
      3. Normalize Unicode whitespace to ASCII spaces
      4. Normalize Unicode to NFC form
      5. Strip leading/trailing whitespace
      6. Preserve fenced code blocks (```...```) exactly
      7. Preserve table formatting
    """
    if not content:
        return ""

    segments = _split_prose_and_code(content)
    # Normalize prose segments, pass code blocks through verbatim
    normalized_parts: list[str] = []
    for is_code, text in segments:
        if is_code:
            normalized_parts.append(text)
        else:
            normalized_parts.append(_normalize_prose(text))

    # Join with single newlines, then apply blank-line collapsing across
    # segment boundaries to handle cases where multiple prose/code transitions
    # created runs of blank lines.
    joined = "\n".join(normalized_parts)
    result = _collapse_blank_lines(joined)
    return result.strip()


def _split_prose_and_code(content: str) -> list[tuple[bool, str]]:
    """Split content into (is_code, text) segments.

    Fenced code blocks start with a line beginning with ``` (optionally followed
    by a language identifier) and end with a line that is exactly ```.
    """
    result: list[tuple[bool, str]] = []
    lines = content.split("\n")
    i = 0
    current_prose_parts: list[str] = []

    fence_re = re.compile(r"^```")

    while i < len(lines):
        line = lines[i]

        if fence_re.match(line):
            if current_prose_parts:
                result.append((False, "\n".join(current_prose_parts)))
                current_prose_parts = []

            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if fence_re.match(lines[i]):
                    break
                i += 1
            result.append((True, "\n".join(code_lines)))
            i += 1
        else:
            current_prose_parts.append(line)
            i += 1

    if current_prose_parts:
        result.append((False, "\n".join(current_prose_parts)))

    return result


def _normalize_prose(text: str) -> str:
    """Apply normalization rules to prose content (outside code blocks)."""
    # Normalize Unicode whitespace characters (Zs category) to ASCII spaces
    text = _normalize_whitespace_to_ascii(text)

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize Unicode to NFC form
    text = unicodedata.normalize("NFC", text)

    return text


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n([ \t]*\n){2,}", "\n\n", text)


def _normalize_whitespace_to_ascii(text: str) -> str:
    """Replace Unicode whitespace characters with ASCII spaces."""
    result: list[str] = []
    for char in text:
        if unicodedata.category(char) == "Zs":
            result.append(" ")
        else:
            result.append(char)
    return "".join(result)
