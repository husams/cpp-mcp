run_id: cpp-mcp-v4
story: S7 — readme-install-fix-and-dependency-missing-wording
date: 2026-05-17
developer: Claude (Sonnet 4.6)

## Skills loaded
- python-conventions

## Skills considered but not loaded
- implement-story — simple targeted edits, no story scaffold needed
- cpp-conventions — Python-only task
- simplify — no duplication found; scope is 3-file edit + 1 new test

## Pre/post wording — AC-7-2

### indradb_driver.py DependencyMissingError (lines 107-110)

**Before:**
```
"indradb Python driver is not installed. "
'Install with: pip install "cpp-mcp[graphdb-indradb]"'
```

**After:**
```
"indradb Python driver is not installed. "
"Install with: uv sync --extra graphdb-indradb  "
'or: pip install "cpp-mcp[graphdb-indradb]"'
```

### neo4j_driver.py DependencyMissingError (lines 53-56)

**Before:**
```
"neo4j Python driver is not installed. "
'Install with: pip install "cpp-mcp[graphdb-neo4j]"'
```

**After:**
```
"neo4j Python driver is not installed. "
"Install with: uv sync --extra graphdb-neo4j  "
'or: pip install "cpp-mcp[graphdb-neo4j]"'
```

## Commands run

- `grep -rn 'pip install.*cpp-mcp\|DependencyMissing' tests/` — found existing tests asserting `match="pip install"` and `match="graphdb-<name>"`. Kept pip install form; prepended uv sync form.
- All S7 exit-criteria commands — see outcomes in implementation-notes.md.

## Deviations from plan.md
- None. Both pip install and uv sync forms are retained in the message to preserve backwards compat with existing tests (test_dependency_missing.py:154, test_indradb_driver.py:193 assert `match="pip install"`).

## Open items
- None.
