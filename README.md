# Synaptic Drift

Give your AI coding agent documentation it can trust.

---

Synaptic Drift builds versioned, verifiable documentation packs from your source files and serves them to AI agents locally. No cloud. No embeddings. No API keys. Just your docs, indexed and searchable in milliseconds.

## The Problem

AI coding agents are only as good as the context you give them. Documentation goes stale, gets mixed with outdated versions, or comes from sources you can't verify. When an agent gives you bad advice, you can't tell whether the docs it read were current, correct, or even real.

## How Synaptic Drift Solves It

Synaptic Drift packages documentation into `.ctx` packs — portable, versioned archives with built-in integrity verification. Every piece of content carries provenance: where it came from, when it was indexed, and whether it's still trusted.

Your agent queries Synaptic Drift's local index instead of guessing from training data. Results come back with source attribution so the agent (and you) can reason about freshness and trust.

## The Workflow

Synaptic Drift has two audiences with distinct command sets.

**Pack consumers** (most users — import and query pre-built packs):

```bash
# First time, or after git clone:
synd sync                               # import every pack listed in synd.lock

# Start the MCP server for your agent:
synd serve

# Search directly from the terminal (optional):
synd query "How do I configure auth?"
```

**Pack authors** (documentation maintainers — build and publish packs):

```bash
# Package your docs into a .ctx pack
synd build my-lib@1.0.0 --source ./docs --output ./packs

# Verify the pack is safe and policy-compliant
synd verify ./packs/my-lib@1.0.0.ctx

# Import into your local index
synd add ./packs/my-lib@1.0.0.ctx

# Remove a pack from the index
synd remove my-lib@1.0.0
```

> **Team setup** — Commit `synd.lock` to version control — analogous to `Cargo.lock` or `package-lock.json`. The lockfile records each imported pack's digest and source URL. On a fresh clone, `synd sync` reads the lockfile and reproduces the full index automatically.

## What Your Agent Sees

Synaptic Drift connects to your AI agent as an MCP server. When the agent needs documentation, it searches your local index and gets back results like this:

```
auth/oauth / Configure OAuth2
  "Configure OAuth2 client credentials flow"
  source: docs/auth/oauth.md
  version: 1.0.0 (stable, approved)
  score: 0.847
```

Every result tells the agent what it found, where it came from, and whether it should be trusted. Deprecated docs get warnings. Revoked docs are excluded entirely.

## Key Properties

**Local-first** — all data stays on your machine. No cloud dependency, no network calls at query time.

**Verifiable** — every pack carries cryptographic hashes. Tampering at any level is detectable before content enters your index.

**Fast** — sub-10ms queries via SQLite full-text search. No embedding model, no vector database, no GPU.

**Source-attributed** — every query result carries provenance metadata. Your agent knows exactly where its information came from.

**Governed** — packs carry lifecycle states (draft, approved, deprecated, revoked) and are checked against your policy before import. You control what enters your agents' context.

## Installation

```bash
# Full CLI (build, verify, add, query)
pip install synaptic-drift

# + MCP server for AI agents
pip install synaptic-drift[serve]
```

Requires Python 3.12+.

## Connect to Your Agent

Add Synaptic Drift as an MCP server in your editor's configuration:

```json
{
  "mcpServers": {
    "synd": {
      "command": "synd",
      "args": ["serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Works with Claude Code, Claude Desktop, Cursor, VS Code, and any MCP-compatible client.

## Documentation

| Document | What's Inside |
|---|---|
| [Architecture](docs/architecture.md) | System design, formats, schemas, validation rules |
| [Document Processing](docs/document-processing.md) | How `synd build` transforms source files into packs |
| [Decisions](docs/decisions.md) | Design decisions with reasoning and rejected alternatives |
| [Glossary](docs/glossary.md) | Definitions of all Synaptic Drift-specific terminology |
| [Roadmap](docs/roadmap.md) | Semver checklist and current focus |

## Status

Synaptic Drift v0.1.1 is code-complete. Active development is on v0.2.0 (339 tests passing). See [roadmap.md](docs/roadmap.md) for current focus.

## License

TBD
