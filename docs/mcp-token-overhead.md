# MCP Token Overhead: Findings and Mitigation Strategies

MCP tool schemas are injected into the context window on every request. At scale,
this consumes a significant fraction of available context before any user work begins.
This document summarises findings from three independent benchmarks and maps the
mitigations to Synaptic Drift's architecture.

---

## The Problem

Each MCP tool definition costs tokens — its name, description, parameter schema, and
examples all count against the context window. With many tools registered, the upfront
cost before the first user message can be substantial:

| Source | Observed overhead |
|---|---|
| Single tool (average) | 550–1,400 tokens |
| GitHub Copilot MCP server (43 tools) | ~43,000 tokens per request |
| Three MCP servers combined | 143,000 of 200,000 tokens (72%) |
| Full OpenAPI spec loaded as MCP | 30,000–100,000+ tokens |

The overhead is not one-time — the full schema is re-injected on every tool call within
a conversation.

---

## Benchmark Findings

### Scalekit — MCP vs CLI (75 controlled runs)

**Sources**: [Blog post](https://www.scalekit.com/blog/mcp-vs-cli-use) · [GitHub benchmark repo](https://github.com/scalekit-inc/mcp-vs-cli-benchmark)  
**Methodology**: 75 runs, same model (Claude Sonnet 4), same tasks, same prompts. Only
the tool interface changed. GitHub's official Copilot MCP server tested against read-only
repository operations. Statistical significance via Wilcoxon signed-rank test with
Bonferroni correction.

**Token usage by task**:

| Task | CLI | MCP | Overhead |
|---|---|---|---|
| Repo language & license | 1,365 | 44,026 | 32× |
| PR details & review status | 1,648 | 32,279 | 20× |
| Repo metadata & install | 9,386 | 82,835 | 9× |
| Merged PRs by contributor | 5,010 | 33,712 | 7× |
| Latest release & dependencies | 8,750 | 37,402 | 4× |

Root cause: all 43 tool schemas travel in the conversation context on every call.
The agent uses one or two tools; it pays for all 43.

**Reliability**: MCP achieved 72% success (18/25 runs) vs 100% for CLI. Failures were
TCP-level timeouts, not logic errors.

**Cost (10,000 operations/month)**:
- CLI: ~$3.20
- Direct MCP: ~$55.20 (17× higher)
- MCP via gateway with filtering: ~$5 (estimated)

---

### Apideck — Real-World Context Window Consumption

**Sources**: [Blog post](https://www.apideck.com/blog/mcp-server-eating-context-window-cli-alternative) · [Mirror on DEV Community](https://dev.to/amzani/your-mcp-server-is-eating-your-context-window-theres-a-simpler-way-3ja2)

Key observations:

- A CLI agent prompt costs ~80 tokens. An individual MCP tool definition costs 550–1,400.
- Three MCP servers in a typical developer setup consumed 143,000 of 200,000 tokens —
  72% of the context window — before any user message was processed.
- The Sideko benchmark (12 Stripe tasks) found Code Mode MCP used 58% fewer tokens than
  raw MCP and 56% fewer than CLI, by collapsing multi-step tasks (19 LLM round trips for
  CLI → 4 for Code Mode).

Recommended situations where MCP remains appropriate despite overhead:
- Tightly scoped, high-frequency operations with few tools
- B2B multi-tenant scenarios requiring per-user OAuth flows

---

### StackOne — Four Optimisation Approaches Compared

**Source**: [MCP Token Optimization: 4 Approaches Compared](https://www.stackone.com/blog/mcp-token-optimization/)

Two distinct problems require separate treatment:

1. **Schema bloat** — tool definitions consumed upfront per request
2. **Response bloat** — tool output accumulating in context across a multi-step session

#### Approach 1: Schema Compression

Strip descriptions and metadata from tool definitions while preserving parameter
structure.

| Compression level | Tokens (vs 17,600 baseline) | Reduction |
|---|---|---|
| Low | 3,900 | 78% |
| Medium | 3,300 | 81% |
| High | 2,200 | 88% |
| Max | 500 | 97% |

Tradeoff: minimal descriptions reduce tool-selection accuracy. Best for narrow,
well-named tools where parameter names alone are self-documenting.

#### Approach 2: Search-First Discovery

Load 2–3 meta-tools that let the agent search for capabilities on demand rather
than registering the full catalog upfront.

| Scenario | Full catalog | Search-first | Reduction |
|---|---|---|---|
| Simple task, 400 tools | 400,000+ tokens | 6,000 | 98.5% |
| Complex task, 400 tools | 400,000+ tokens | 35,000 | 91.2% |

Accuracy gains with Claude Opus 4: +25 percentage points (49% → 74%).  
Tradeoff: ~50% more round trips per tool call (latency increases).

#### Approach 3: Response Filtering

Return only requested fields from tool outputs before they enter the context.

Token savings: ~95%+ per call (hundreds of thousands of characters → ~8,000).  
Tradeoff: does not solve accumulation across multi-step workflows; requires
MCP server cooperation.

#### Approach 4: Code-Based Execution

Agent writes code that runs in a sandboxed isolate; only the filtered result
re-enters context.

| Implementation | Reduction |
|---|---|
| StackOne Code Mode | 99.3% (55,000+ chars → 416) |
| Anthropic pattern | 98.7% (150,000 tokens → 2,000) |
| Cloudflare pattern | 99.9% (1,170,000 tokens → ~1,000) |

Accuracy gains with Sonnet 4.6: 42% → 80%.  
Tradeoff: requires sandbox infrastructure; highest setup complexity.

**Selection guide**:

| Scenario | Recommended approach |
|---|---|
| Few tools, small responses | Schema compression |
| Many tools, small responses | Search-first discovery |
| Few tools, large API responses | Response filtering |
| Both schema and response bloat | Code-based execution |
| Most production systems | Combine 2–3 approaches |

---

## What This Means for Synaptic Drift

Synaptic Drift registers two MCP tools (`search`, `fetch`). The schema cost is low
compared to the benchmarks above. The relevant risk is **response bloat**, not schema
bloat.

### Synaptic Drift's existing mitigation: two-tool progressive disclosure

The tools structurally enforce the two-step pattern:

- `search` — returns heading path and one-sentence summary per chunk, never full content.
  Token cost is proportional to the number of results, but each result is small (~20–40 tokens).
- `fetch` — returns complete chunk content for a list of `chunk_ids`. Token cost scales with
  chunk size (average ~400 tokens per chunk based on the `token_count` estimates in `index.db`).

The intended agent pattern is:
1. Call `search` to identify relevant chunks (low cost).
2. Call `fetch` with the selected `chunk_ids` to retrieve only the chunks that matter (targeted cost).

This matches the search-first discovery and response filtering patterns from StackOne,
without requiring sandbox infrastructure.

### What is not yet measured

The industry benchmarks above (Scalekit: 4–32× overhead, Apideck: 72% of context window consumed) cite the progressive disclosure pattern as a primary mitigation. Synaptic Drift's two-step design aligns with this, but Synaptic Drift has no internal benchmark confirming its own tool's token footprint.

**A token overhead benchmark for Synaptic Drift should measure**:

1. Schema cost — serialise the `search` and `fetch` tool definitions,
   count tokens (`len(json) // 4`), express as a percentage of a 200K context window.
2. Summary response cost — total tokens returned by `search` for N results
   (measure across N = 5, 10, 20).
3. Full response cost — total tokens returned by `fetch` for the same N chunks.
4. Progressive disclosure saving — (full cost − summary cost) / full cost, to
   quantify what the two-step pattern saves per query session.

This benchmark belongs in `tests/benchmarks/` and requires no new dependencies.
It would give Synaptic Drift a concrete, internally reproducible number to cite instead of
borrowing figures measured against a different tool.

### Recommendations for the roadmap

| Item | Priority | Action |
|---|---|---|
| ~~Write token overhead benchmark~~ | ~~v0.2.0~~ | ✅ Done — `tests/benchmarks/test_token_overhead.py` with baseline in `tests/benchmarks/results/latest.json` |
| Document progressive disclosure pattern | v0.1.0 | Add agent usage example to README showing the two-step summary→full pattern |
| Expose `token_budget` on `search`/`fetch` | v0.3.0 | Return maximum content within a caller-specified token budget, auto-balancing result count vs. chunk size |
| Consider schema compression | v1.0.0 | If Synaptic Drift registers more tools in future, audit description verbosity against StackOne's compression tradeoffs |
| ~~Fix silent failure in `fts.py:76`~~ | ~~open bug~~ | ✅ Fixed — `search()` now raises `SearchError` on `sqlite3.Error` |

---

## References

- Scalekit — [MCP vs CLI: Benchmarking AI Agent Cost & Reliability](https://www.scalekit.com/blog/mcp-vs-cli-use)
- Scalekit — [mcp-vs-cli-benchmark (GitHub, MIT)](https://github.com/scalekit-inc/mcp-vs-cli-benchmark)
- Apideck — [Your MCP Server Is Eating Your Context Window](https://www.apideck.com/blog/mcp-server-eating-context-window-cli-alternative)
- Apideck — [DEV Community mirror](https://dev.to/amzani/your-mcp-server-is-eating-your-context-window-theres-a-simpler-way-3ja2)
- StackOne — [MCP Token Optimization: 4 Approaches Compared](https://www.stackone.com/blog/mcp-token-optimization/)
- Sideko — referenced in Apideck post; 12 Stripe task benchmark comparing raw MCP, CLI, and Code Mode token usage
- MCP Playground — [MCP Token Counter](https://mcpplaygroundonline.com/blog/mcp-token-counter-optimize-context-window)
