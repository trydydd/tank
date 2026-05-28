"""MDX/JSX stripping pipeline for Mintlify .md endpoint content."""

from __future__ import annotations

import re
import textwrap

# JSX block tags whose inner text should be kept, wrappers discarded.
_JSX_UNWRAP_RE = re.compile(
    r"<(Note|Warning|Tip|Tabs|Tab|Callout|Info|Check|Error|Accordion|AccordionGroup|Frame|CodeGroup)\b[^>]*>(.*?)</\1>",
    re.DOTALL,
)

# Orphaned JSX closing tags left after strip_mdx removes unknown opening tags.
_ORPHAN_CLOSER_RE = re.compile(r"^\s*</[A-Z][\w.]*>\s*$", re.MULTILINE)

# Frame elements that contain only an image — discard entirely.
_FRAME_IMAGE_RE = re.compile(
    r"<Frame\b[^>]*>\s*(?:<img\b[^>]*/?>|<img\b[^>]*></img>)\s*</Frame>",
    re.DOTALL | re.IGNORECASE,
)

# Inline <sup>…</sup> anchor noise appended to heading lines.
_SUP_RE = re.compile(r"\s*<sup\b[^>]*>.*?</sup>", re.IGNORECASE)

# Extracts the title attribute value from a JSX opening tag.
_TAB_TITLE_RE = re.compile(r'\btitle=["\']([^"\']*)["\']')


def strip_mdx(text: str) -> str:
    """Remove JSX import/export lines, self-closing components, and bare expressions."""
    cleaned = text
    cleaned = re.sub(r"^\s*(?:import|export)\s+.+?$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(
        r"^\s*<([A-Z][\w.]*)\b[^>]*?/?>\s*$", "", cleaned, flags=re.MULTILINE
    )
    cleaned = re.sub(r"\{`([^`]*)`\}", r"\1", cleaned)
    cleaned = re.sub(r'\{\s*"([^"]*)"\s*\}', r"\1", cleaned)
    cleaned = re.sub(r"\{\s*'([^']*)'\s*\}", r"\1", cleaned)
    cleaned = re.sub(r"\{[^{}\n]*\}", "", cleaned)
    return cleaned


def _clean_fence_info(fence: str) -> str:
    """Strip MDX attributes from a code fence info string, keeping only the language token."""
    return re.sub(r"^(```[a-z]*)[ \t].*", r"\1", fence, flags=re.MULTILINE, count=1)


_INDENTED_FENCE_CLOSE_RE = re.compile(r"\n[ \t]+(```+)\s*$")


def _extract_code_fences(text: str) -> tuple[str, list[str]]:
    """Replace code fences with sentinels to protect them from MDX regexes.

    The closing ``` marker is normalised to column 0 before storage. In
    indented JSX blocks (e.g. <Tab> bodies) the closing fence inherits the
    block's 4-space indent. CommonMark allows at most 3 leading spaces on a
    closing fence; a 4-space-indented closer is not recognised by markdown-it-py,
    which then treats the rest of the document as fence content.
    """
    fences: list[str] = []

    def _repl(match: re.Match[str]) -> str:
        fence = _INDENTED_FENCE_CLOSE_RE.sub(r"\n\1", match.group(0))
        fences.append(_clean_fence_info(fence))
        return f"@@CODE_FENCE_{len(fences) - 1}@@"

    masked = re.sub(r"```[\s\S]*?```", _repl, text)
    return masked, fences


def _unwrap_tab_block(m: re.Match[str]) -> str:
    """Replacement for _JSX_UNWRAP_RE: injects Tab title as a heading and shifts body headings.

    For <Tab title="..."> blocks: extracts the title, dedents the body, shifts all
    ATX headings one level deeper (capped at H6), then prepends the title as a
    heading one level above the shallowest body heading.

    All other tags (Tabs, Note, Warning, etc.) fall back to plain textwrap.dedent.
    """
    tag = m.group(1)
    body = m.group(2)

    if tag != "Tab":
        return textwrap.dedent(body)

    title_match = _TAB_TITLE_RE.search(m.group(0))
    if not title_match:
        return textwrap.dedent(body)

    title = title_match.group(1)
    body = textwrap.dedent(body)

    heading_levels: list[int] = []
    for line in body.splitlines():
        hm = re.match(r"^(#{1,6})\s", line)
        if hm:
            heading_levels.append(len(hm.group(1)))

    if not heading_levels:
        return f"### {title}\n\n{body}"

    shallowest = min(heading_levels)

    def _shift(line: str) -> str:
        hm = re.match(r"^(#{1,6})(\s.*)$", line)
        if hm:
            new_level = min(len(hm.group(1)) + 1, 6)
            return "#" * new_level + hm.group(2)
        return line

    shifted_body = "\n".join(_shift(line) for line in body.splitlines())
    title_level = max(1, shallowest - 1)
    return f"{'#' * title_level} {title}\n\n{shifted_body}"


def unwrap_jsx_blocks(text: str) -> str:
    """Replace block-level JSX wrappers with their inner text.

    Handles: Note, Warning, Tip, Tabs, Tab, Callout, Info, Check, Error,
    Accordion, AccordionGroup, Frame (with non-image inner content).
    Discards: Frame elements that wrap only an <img> tag.
    Loops up to 5 times to handle one level of nesting (e.g. Tabs > Tab).
    """
    text = _FRAME_IMAGE_RE.sub("", text)
    for _ in range(5):
        new_text = _JSX_UNWRAP_RE.sub(_unwrap_tab_block, text)
        if new_text == text:
            break
        text = new_text
    return text


def clean_heading(line: str) -> str:
    """Strip inline <sup>…</sup> anchor pollution from an ATX heading line.

    Converts:
      ## ClassName <sup><a href="..."><Icon /></a></sup>
    to:
      ## ClassName

    Non-heading lines are returned unchanged.
    """
    if not line.lstrip().startswith("#"):
        return line
    return _SUP_RE.sub("", line).rstrip()


def process_mdx(text: str) -> str:
    """Full MDX-to-CommonMark pipeline for Mintlify .md endpoint content.

    Order of operations:
    1. Extract code fences (protect from regex passes)
    2. unwrap_jsx_blocks — keep inner text of block JSX, dedent, discard wrappers
       Must run before strip_mdx: strip_mdx removes uppercase-initial opening tags
       that appear alone on a line, which destroys the <Tag>…</Tag> pair that
       unwrap_jsx_blocks needs to see. Running unwrap first preserves the pairing.
    3. strip_mdx — remove import/export lines, remaining self-closing components,
       bare expressions, and orphaned closing tags
    4. Restore code fences
    5. clean_heading — strip <sup> anchor noise from heading lines
    6. Collapse runs of blank lines

    Returns CommonMark-compatible markdown ready for the chunker.
    """
    masked, fences = _extract_code_fences(text)
    masked = unwrap_jsx_blocks(masked)
    masked = strip_mdx(masked)
    masked = _ORPHAN_CLOSER_RE.sub("", masked)
    for i, fence in enumerate(fences):
        masked = masked.replace(f"@@CODE_FENCE_{i}@@", f"\n{fence}\n")
    lines = [clean_heading(line) for line in masked.split("\n")]
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
