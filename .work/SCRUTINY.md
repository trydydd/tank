# SCRUTINY — chunk-06-review

Items flagged for deep-dive review. Not bugs — no immediate fix needed — but worth scrutiny before they propagate downstream.

---

## 1. `import sqlite3` is unused

**Location:** `src/tank/search/fts.py:4` (was line 4 in original; import was removed during fix)

The `sqlite3` import was removed when switching from `sqlite3.Connection` to `Database`. No code references `sqlite3` anymore.

**Question:** Is it worth leaving a comment explaining why `sqlite3` is no longer needed, or should it stay removed to avoid confusion?

---

## 2. `except Exception` swallows all errors

**Location:** `fts.py:76`

```python
    except Exception:
        return []
```

This catches *any* exception during query execution: `OperationalError` (malformed FTS query, missing tables), `ProgrammingError` (bad column names), `DatabaseError`, or even unexpected `AttributeError` if `db.conn` is broken.

**Why this was chosen:** The ledger spec says "FTS5 MATCH will raise sqlite3.OperationalError on malformed queries. Catch and return an empty result list." A bare `except sqlite3.OperationalError` is more precise, but FTS5 can raise other error types on edge cases (e.g., empty MATCH in some SQLite versions), and swallowing them silently avoids crashes in a search endpoint that should degrade gracefully.

**Tradeoff:** Correctness vs. robustness. If the DB schema is broken (missing `chunks_fts` table, wrong columns), the caller gets `[]` and may interpret it as "no matches" rather than "database is broken." This could mask schema issues in production.

**Potential fix (deferred):** Catch `sqlite3.OperationalError` specifically (per ledger spec) and let other exceptions propagate. Or add a warning log level.

---

## 3. Hardcoded tuple indices in SearchResult construction

**Location:** `fts.py:84-98`, `fts.py:133-149`

Both `search()` and `get_chunks_by_id()` build `SearchResult` using integer indices (`row[0]`, `row[1]`, etc.). A comment maps indices to columns but if the SQL SELECT column order changes, the mapping silently breaks.

**Example of silent break:** If `content` is moved from position 5 to position 7, `row[5]` would still return a value but it would be the wrong field — with no error and no test failure (tests happen to match).

**Mitigation:** The `row_factory = sqlite3.Row` on `Database.conn` means callers *could* use dict access, but that would reintroduce the row_factory dependency bug we just fixed.

**Question:** Should we keep the fragile tuple indexing as-is (connection-agnostic, but fragile on SQL change) or switch to dict access (robust on SQL change, but requires row_factory)?

---

## 4. `packages=[]` returns all packages (no filter)

**Location:** `fts.py:42`

```python
    if packages:
```

An empty list is falsy, so `search(db, "query", packages=[])` returns *all* results, not an empty list. This matches `packages=None` behavior.

**Question:** Should `packages=[]` mean "return no results" (explicit empty filter) or "return all results" (no filter)? The current behavior is "no filter." If a caller intentionally wants zero results, they should use `packages=None` + a custom filter or just pass an empty list and expect the current behavior.

---
