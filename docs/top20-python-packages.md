# Top 20 Intentionally Installed Python Packages

## Methodology

Raw PyPI download counts are dominated by transitive dependencies — boto3/botocore/s3transfer, urllib3, certifi, and charset-normalizer collectively account for enormous download volume simply because they ride along with everything AWS-related. This list filters those out and ranks by **intentional installation**: packages that developers or teams add directly to their own project dependencies.

Signals used to produce the ranking:

- PyPI download stats, filtered to exclude known pure-dependency packages (botocore, s3transfer, urllib3, charset-normalizer, idna, certifi, six, typing-extensions, packaging, python-dateutil)
- GitHub star counts and dependency graph breadth (how many other actively-maintained packages list this as a direct dependency)
- Developer survey data (JetBrains Python Developer Survey, Stack Overflow survey)
- Ecosystem role: packages that anchor a whole category (HTTP, data, web, CLI, testing) score higher

| # | Package | Category | Notes |
|---|---------|----------|-------|
| 1 | requests | HTTP client | Dominant HTTP library; found in nearly every project |
| 2 | numpy | Numerical computing | Foundation for scientific Python; pulled directly by most data projects |
| 3 | pandas | Data analysis | Primary DataFrame library |
| 4 | boto3 | AWS SDK | Installed directly by any AWS-using project |
| 5 | pydantic | Data validation | Explosion in use post-v2; powers FastAPI and many others |
| 6 | click | CLI framework | Most-used CLI toolkit |
| 7 | pytest | Testing | Standard test runner |
| 8 | sqlalchemy | ORM / DB toolkit | Covers both ORM and Core patterns |
| 9 | fastapi | Web framework | Fastest-growing async web framework |
| 10 | flask | Web framework | Dominant lightweight web framework |
| 11 | django | Web framework | Full-stack; largest installed web framework base |
| 12 | pillow | Image processing | Only mainstream PIL fork still maintained |
| 13 | scipy | Scientific computing | Direct install for statistical/signal work |
| 14 | matplotlib | Plotting | Default plotting library |
| 15 | httpx | HTTP client | Modern async HTTP; growing fast as requests successor |
| 16 | celery | Task queue | Standard distributed task queue |
| 17 | redis | Redis client | Installed wherever Redis is used |
| 18 | PyYAML | YAML parsing | Near-universal config file dependency |
| 19 | python-dotenv | Env config | Standard `.env` file loader |
| 20 | rich | Terminal output | Rapidly adopted for CLI formatting |

---

## llms.txt / llms-full.txt Coverage

The [llms.txt standard](https://llmstxt.org/) defines two files that documentation sites can serve to make their content accessible to LLMs:

- **`llms.txt`** — a structured markdown index of documentation pages with links
- **`llms-full.txt`** — a single concatenated file containing the full text of all documentation pages, separated by `Source: <url>` boundaries

Both files, when present, allow `synd build` to build a `.ctx` pack directly from a URL without needing to mirror or clone the documentation source.

All 20 sites were checked directly by fetching `<docs-root>/llms.txt` and `<docs-root>/llms-full.txt`. Multiple URL path patterns were tried per package (root, `/en/latest/`, `/doc/stable/`, versioned paths) to account for different documentation hosting conventions.

| # | Package | Docs URL | llms.txt | llms-full.txt | Notes |
|---|---------|----------|----------|---------------|-------|
| 1 | requests | requests.readthedocs.io/en/latest | No | No | |
| 2 | numpy | numpy.org/doc/stable | No | No | |
| 3 | pandas | pandas.pydata.org/docs | No | No | |
| 4 | boto3 | boto3.amazonaws.com / docs.aws.amazon.com | No | No | Redirects to AWS docs |
| 5 | pydantic | docs.pydantic.dev / pydantic.dev | **Yes** | **Yes** | At `/docs/validation/latest/llms.txt` |
| 6 | click | click.palletsprojects.com/en/stable | No | No | |
| 7 | pytest | docs.pytest.org/en/stable | No | No | |
| 8 | sqlalchemy | docs.sqlalchemy.org/en/20 | No | No | Multiple redirects, all 404 |
| 9 | fastapi | fastapi.tiangolo.com | No | No | |
| 10 | flask | flask.palletsprojects.com/en/stable | No | No | |
| 11 | django | docs.djangoproject.com/en/stable | No | No | |
| 12 | pillow | pillow.readthedocs.io/en/stable | No | No | |
| 13 | scipy | docs.scipy.org/doc/scipy | No | No | |
| 14 | matplotlib | matplotlib.org/stable | Unknown | Unknown | 403 on all attempts; may exist but blocked |
| 15 | httpx | python-httpx.org | No | No | |
| 16 | celery | docs.celeryq.dev/en/stable | No | No | |
| 17 | redis | redis-py.readthedocs.io/en/stable | No | No | |
| 18 | PyYAML | pyyaml.org | No | No | |
| 19 | python-dotenv | saurabh-kumar.com/python-dotenv | No | No | |
| 20 | rich | rich.readthedocs.io/en/stable | No | No | |

**Summary: 1 of 20 confirmed** (pydantic). Matplotlib is unresolved due to 403 responses.

---

## Building a .ctx Pack Without llms.txt: requests

For packages without `llms.txt` or `llms-full.txt`, `synd build` cannot use a URL source directly — `build_pack_from_url` hard-requires a URL ending in one of those two filenames. The workaround is to obtain the documentation as local files and use the directory build path instead.

The script [`scripts/build-pack-html.sh`](../scripts/build-pack-html.sh) automates this process: it mirrors the docs site with wget, removes readthedocs boilerplate directories, builds the pack, and cleans up the mirror.

### Process used for requests@2.34.2

```bash
scripts/build-pack-html.sh \
    https://requests.readthedocs.io/en/latest/ requests@2.34.2 \
    --exclude-dir community/updates
```

Output: `packs/requests@2.34.2.ctx`

The script ran the following steps:

**Step 1 — Mirror the live HTML documentation**

```bash
wget --mirror -p --html-extension --convert-links \
     -e robots=off --no-parent \
     -P ./requests-html \
     https://requests.readthedocs.io/en/latest/
```

Downloaded 26 HTML files. `--no-parent` prevents wget from crawling outside `/en/latest/`.

**Step 2 — Remove noise directories**

The script removes these by default (readthedocs boilerplate, not documentation content):

| Directory | Reason |
|-----------|--------|
| `_modules/` | Raw source viewer pages |
| `genindex/` | Generated symbol index |
| `search/` | Search UI page |

`community/updates/` was added via `--exclude-dir` for this build:

| Directory | Reason |
|-----------|--------|
| `community/updates/` | Full changelog — 15k tokens, noise |

**Step 3 — Build the pack**

```bash
synd build requests@2.34.2 \
     --source ./requests-html/requests.readthedocs.io/en/latest/ \
     --output ./packs
```

**Oversized chunks observed on an unfiltered first build** (before exclusions):

| Chunk | Tokens | Cause |
|-------|--------|-------|
| community/updates/index | 15,115 | Full changelog |
| api/index (×2) | 6,357 / 5,899 | Large API reference pages |
| _modules/requests/models/index | 3,305 | Raw source viewer |
| genindex/index | 2,049 | Generated symbol index |

### Notes on HTML quality

`synd`'s `html_to_markdown` converter targets `<main>`, `<article>`, or `role="main"` elements and strips `<nav>`, `<header>`, `<footer>`, `<aside>`, `<script>`, and `<style>` tags before converting. ReadTheDocs HTML generally has a clean `<main>` element, so boilerplate stripping works well. Run `synd inspect packs/requests@2.34.2.ctx` to review chunk content and headings after building.

### Generalising to other packages

`build-pack-html.sh` applies to any package hosted on ReadTheDocs or a similar static HTML site:

```bash
scripts/build-pack-html.sh <docs-root-url> <name@version> [--exclude-dir <dir> ...]
```

For packages with source docs in a Git repository (Sphinx `.rst`, MkDocs `.md`, etc.), an alternative is to clone the repo and either:
- Build the docs to HTML with Sphinx/MkDocs, then point `--source` at the HTML output directory
- Point `--source` directly at the `.md` source directory if the package uses MkDocs (`.md` files are natively supported)
