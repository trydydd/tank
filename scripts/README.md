# Scripts

## `llms_full_to_markdown.py`

Convert an `llms-full.txt` file (or URL) that may contain MDX/JSX and embedded HTML into cleaner Markdown-style output.

### Requirements

- Python 3.11+

### Usage

From the repository root:

```bash
python scripts/llms_full_to_markdown.py <source>
```

- `<source>` can be:
  - a local file path, or
  - an `http://` / `https://` URL.

Write output to a file:

```bash
python scripts/llms_full_to_markdown.py <source> -o output.md
```

### Examples

Local input:

```bash
python scripts/llms_full_to_markdown.py ./llms-full.txt -o cleaned.md
```

Remote input:

```bash
python scripts/llms_full_to_markdown.py https://modelcontextprotocol.io/llms-full.txt -o mcp-cleaned.md
```

### What it does

- removes common MDX wrapper noise (such as import/export lines)
- keeps fenced code blocks intact
- extracts readable text from embedded HTML
- converts HTML list items into markdown bullet points

### Notes

- If remote URL fetch fails in restricted environments (proxy/firewall), download the file locally first and run the script on the local path.
