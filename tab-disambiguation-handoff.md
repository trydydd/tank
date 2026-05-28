# Work Handoff: Tab Heading Disambiguation

## What you're working on

**Repo**: `trydydd/synaptic-drift`  
**Branch**: `claude/chunker-feature-CemK2` — develop all changes here, commit, and push when done.  
**Dev setup**: `python3.12 -m venv .venv && .venv/bin/pip install -e ".[all]"`

---

## The problem

Synaptic Drift builds documentation packs from `llms-full.txt` sources. Mintlify-hosted docs (like modelcontextprotocol.io) wrap multi-language tutorial content in `<Tabs><Tab title="Python">…</Tab><Tab title="TypeScript">…</Tab></Tabs>` JSX blocks.

The MDX pipeline in `src/synd/builder/mdx.py` strips the `<Tab>` wrapper and keeps the inner text — but **discards the `title` attribute**. The chunker then receives a flat document where all 7 language tabs have concatenated their headings without any language label. Every language produces a chunk for `### Implementing tool execution`, and all 7 chunks get the same `heading_path`.

**Measured impact** (from `mcp@2025-11-25` pack built from `https://modelcontextprotocol.io/llms-full.txt`):

```
build-server page: 111 chunks, only 45 unique heading_paths
x15  docs/develop/build-server / Testing your server with Claude for Desktop
x8   docs/develop/build-server / Building your server
x8   docs/develop/build-server / Building your server / Running the server
x5   docs/develop/build-server / Building your server / Implementing tool execution
```

A user searching "Python tool execution" gets 5 results all with the same `heading_path`. BM25 treats them identically; the agent gets no signal about language.

**Reproduce it yourself:**

```bash
mkdir -p /tmp/mcp-pack
.venv/bin/synd build mcp@2025-11-25 \
  --source https://modelcontextprotocol.io/llms-full.txt \
  --output /tmp/mcp-pack

unzip -p /tmp/mcp-pack/mcp@2025-11-25.ctx chunks.jsonl | python3 -c "
import json, sys
from collections import Counter
chunks = [json.loads(l) for l in sys.stdin if l.strip()]
bs = [c for c in chunks if 'build-server' in c.get('source_url', '')]
paths = Counter(c['heading_path'] for c in bs)
print(f'{len(bs)} chunks, {len(set(c[\"heading_path\"] for c in bs))} unique heading_paths')
for path, cnt in paths.most_common(8):
    print(f'  x{cnt}  {path}')
"
```

---

## Where the code lives

All work is in one file:

**`src/synd/builder/mdx.py`** — the MDX-to-CommonMark pipeline.

The relevant function is `unwrap_jsx_blocks()` (lines 69–83):

```python
_JSX_UNWRAP_RE = re.compile(
    r"<(Note|Warning|Tip|Tabs|Tab|Callout|Info|Check|Error|Accordion|AccordionGroup|Frame|CodeGroup)\b[^>]*>(.*?)</\1>",
    re.DOTALL,
)

def unwrap_jsx_blocks(text: str) -> str:
    text = _FRAME_IMAGE_RE.sub("", text)
    for _ in range(5):
        new_text = _JSX_UNWRAP_RE.sub(lambda m: textwrap.dedent(m.group(2)), text)
        if new_text == text:
            break
        text = new_text
    return text
```

Right now the lambda is `lambda m: textwrap.dedent(m.group(2))` — it extracts the inner text and dedents it, but `m.group(1)` (the tag name) and the `title` attribute are thrown away.

The test file is **`tests/test_builder/test_mdx.py`**.

---

## What the source looks like

A typical Mintlify tutorial section in the raw `llms-full.txt`:

```
## Building your server

<Tabs>
  <Tab title="Python">
    ### Importing packages and setting up the instance
    Content about Python setup.

    ### Helper functions
    Python helper code.

    ### Implementing tool execution
    ```python
    def handle_tool(name, args):
        ...
    ```
  </Tab>
  <Tab title="TypeScript">
    ### Importing packages and setting up the instance
    Content about TypeScript setup.

    ### Implementing tool execution
    ```typescript
    async function handleTool(name: string, args: any) {
        ...
    }
    ```
  </Tab>
</Tabs>
```

After the current pipeline (before your fix), the document becomes:

```markdown
## Building your server

### Importing packages and setting up the instance
Content about Python setup.

### Helper functions
Python helper code.

### Implementing tool execution
(python code fence)

### Importing packages and setting up the instance
Content about TypeScript setup.

### Implementing tool execution
(typescript code fence)
```

The language context is gone. Both `### Implementing tool execution` chunks get `heading_path = "docs/develop/build-server / Building your server / Implementing tool execution"`.

---

## What you need to implement

### Goal

After your fix, the same input should produce:

```markdown
## Building your server

### Python
#### Importing packages and setting up the instance
Content about Python setup.

#### Helper functions
Python helper code.

#### Implementing tool execution
(python code fence)

### TypeScript
#### Importing packages and setting up the instance
Content about TypeScript setup.

#### Implementing tool execution
(typescript code fence)
```

Resulting `heading_path` values:
- `docs/develop/build-server / Building your server / Python / Implementing tool execution`
- `docs/develop/build-server / Building your server / TypeScript / Implementing tool execution`

### Algorithm

Modify `unwrap_jsx_blocks()` in `src/synd/builder/mdx.py`. When the matched tag is specifically `Tab` (not `Tabs`, `Note`, `Warning`, or any other tag), apply this transform instead of a plain dedent:

1. **Extract the `title` attribute** from the opening tag. The attribute appears as `title="Python"` or `title='TypeScript'`. If there is no `title` attribute, fall back to the existing plain-dedent behaviour.

2. **Dedent the body** (same as the current `textwrap.dedent(m.group(2))`).

3. **Find the shallowest heading level** in the dedented body. Scan lines starting with `#`; the minimum `#` count is the shallowest level (e.g. `### Foo` → level 3).

4. **Shift all headings one level deeper**: `### Foo` → `#### Foo`, `## Bar` → `### Bar`, etc. Cap at H6 — `###### Foo` stays `###### Foo`.

5. **Prepend the title as a heading one level above the shifted content**: if the shallowest heading in the body was level 3 (H3), inject `## {title}\n\n` at the start. If the body has no headings at all, inject `### {title}\n\n`.

The substitution lambda currently reads:
```python
lambda m: textwrap.dedent(m.group(2))
```

You'll need to replace it with a named function (or a helper called from the lambda) that implements the above logic only when `m.group(1) == "Tab"`.

### Edge cases to handle

| Case | Expected behaviour |
|---|---|
| `<Tab>` with no `title` attribute | Fall back to plain dedent, no heading injected |
| Tab body with no headings | Inject `### {title}\n\n` before the dedented content |
| Tab body where shallowest heading is already H6 | Shift is a no-op (already at max depth); inject `##### {title}\n\n` |
| `<Tabs>` tag (the container) | Unchanged — plain dedent, no title injection |
| `<Note>`, `<Warning>`, etc. | Unchanged — plain dedent, no title injection |
| Nested `<Tab>` inside a `<Note>` | Outer `<Note>` processed on a later loop iteration; inner `<Tab>` processed first — correct by construction |
| Tab title containing special markdown characters (e.g. `C#`) | Inject literally — `### C#\n\n` — no escaping needed |

---

## Tests to write

Add these to `tests/test_builder/test_mdx.py`:

```python
def test_tab_title_injected_as_heading() -> None:
    raw = '<Tab title="Python">\n    ### Implementing tool execution\n\n    Some content.\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    # Title injected one level above shallowest heading (H3 → ## Python)
    assert "## Python" in result
    # Original H3 shifted to H4
    assert "#### Implementing tool execution" in result
    assert "### Implementing tool execution" not in result
    assert "Some content." in result

def test_tab_title_no_headings_in_body() -> None:
    raw = '<Tab title="Python">\n    Just some prose.\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    # No headings in body → inject ### {title}
    assert "### Python" in result
    assert "Just some prose." in result

def test_tab_without_title_falls_back_to_dedent() -> None:
    raw = '<Tab>\n    ### Some section\n\n    Content.\n</Tab>'
    result = unwrap_jsx_blocks(raw)
    # No title attribute → plain dedent, no injected heading
    assert "## " not in result
    assert "### Some section" in result

def test_tabs_container_not_affected() -> None:
    # The outer <Tabs> wrapper should never inject a heading
    raw = '<Tabs>\n<Tab title="A">\n    ### Section\n</Tab>\n</Tabs>'
    result = unwrap_jsx_blocks(raw)
    # Tabs wrapper: no heading injection
    # Tab "A": injects ## A, shifts ### → ####
    assert "## A" in result
    assert "#### Section" in result

def test_multi_tab_heading_paths_disambiguated() -> None:
    # The core regression: two tabs with identical section names must
    # produce different heading contexts after unwrapping.
    raw = (
        '<Tabs>\n'
        '<Tab title="Python">\n    ### Setup\n\n    pip install.\n</Tab>\n'
        '<Tab title="TypeScript">\n    ### Setup\n\n    npm install.\n</Tab>\n'
        '</Tabs>'
    )
    result = unwrap_jsx_blocks(raw)
    assert "## Python" in result
    assert "## TypeScript" in result
    # Both ### Setup shifted to #### Setup
    assert result.count("#### Setup") == 2
    assert "### Setup" not in result

def test_note_block_unaffected_by_tab_logic() -> None:
    raw = '<Note>\n    Some warning text.\n</Note>'
    result = unwrap_jsx_blocks(raw)
    assert "Some warning text." in result
    # No spurious heading injected
    assert "#" not in result
```

Also add an integration test in `tests/test_builder/test_mdx.py` under `# --- process_mdx ---`:

```python
def test_process_mdx_tab_titles_disambiguate_headings() -> None:
    raw = (
        "## Building your server\n\n"
        "<Tabs>\n"
        '<Tab title="Python">\n'
        "    ### Setup\n\n"
        "    pip install mcp\n"
        "</Tab>\n"
        '<Tab title="TypeScript">\n'
        "    ### Setup\n\n"
        "    npm install @modelcontextprotocol/sdk\n"
        "</Tab>\n"
        "</Tabs>\n"
    )
    result = process_mdx(raw)
    assert "## Python" in result
    assert "## TypeScript" in result
    assert "#### Setup" in result
    assert "### Setup" not in result
```

---

## Definition of done

- [ ] `unwrap_jsx_blocks()` injects the `<Tab title>` as a heading and depth-shifts body headings
- [ ] All existing 23 tests in `tests/test_builder/test_mdx.py` still pass
- [ ] All new tests listed above pass
- [ ] Running `synd build mcp@2025-11-25 --source https://modelcontextprotocol.io/llms-full.txt --output /tmp/mcp-check` and inspecting `build-server` chunks shows unique `heading_path` values that include the language name (e.g. `Python`, `TypeScript`, `Java`)
- [ ] `build-server` unique heading_path count is ≥ 70 (up from 45 out of 111 chunks)
- [ ] `.venv/bin/ruff check src/ tests/` — zero errors
- [ ] `.venv/bin/ruff format --check src/ tests/` — clean
- [ ] `.venv/bin/mypy src/` — clean
- [ ] `.venv/bin/pytest tests/ -q` — all pass (currently 376 passed, 3 skipped)
- [ ] Changes committed and pushed to `claude/chunker-feature-CemK2`

---

## What not to touch

- `src/synd/builder/chunking.py` — the chunker itself does not need changes; the fix lives entirely in the MDX pipeline
- `src/synd/builder/build.py` — no changes needed
- `pyproject.toml` — no new dependencies needed
- Any other file not mentioned above

---

## Key invariants to preserve

- `<Tabs>` (the container tag) must never inject a heading — only `<Tab>` (the child)
- `<Note>`, `<Warning>`, `<Tip>`, `<Frame>`, and all other non-`Tab` tags must be completely unaffected
- The `textwrap.dedent` that removes Tab body indentation must still happen for `Tab` tags (it already happens; keep it)
- Fence extraction (`_extract_code_fences`) runs before `unwrap_jsx_blocks` and restores after — do not change this order
- `strip_mdx` runs after `unwrap_jsx_blocks` — do not change this order (prior bugs were caused by the wrong order)
