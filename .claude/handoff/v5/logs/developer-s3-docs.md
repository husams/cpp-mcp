# Developer log — S3: Update README, ADRs, and wiki pages for v5 tool names

**Story:** US-V5-R3  
**Date:** 2026-05-17  
**run_id:** cpp-mcp-v5-rename  

---

## Skills loaded

- `python-conventions` — loaded per dispatch instruction (pyproject.toml present)

## Skills considered but not loaded

- `implement-story` — not loaded; S3 is pure doc edits, no source/test changes
- `simplify` — not applicable; no code written

## Commands run + outcomes

```
grep -F 'cpp_export_to_graphdb' README.md && grep -F 'ingest_code' README.md
  → both sentinel strings found (PASS — S3 gate 2)

grep -F '0.3.0' ~/workspace/wiki/index.md
  → line found with v0.3.0 (PASS — S3 gate 3)

grep -RIE 'cpp_(get|export)_' --exclude-dir=.git --exclude-dir=.claude \
  --exclude=CHANGELOG.md --exclude=README.md . || true
  → hits only in pyproject.toml (test marker string, historical) and REQUIREMENTS.md
    (v1 spec, historical) — both expected per ADR-21; no defects
```

## Files changed

### README.md (`/Users/husam/workspace/cpp-mcp/README.md`)
- Test count line: "453 tests pass" → "618 tests pass"
- Install section: `--extra graphdb-neo4j`/`graphdb-indradb` comments updated to `ingest_code`
- Config table: `CPP_MCP_AST_MAX_NODES` description updated from `cpp_get_ast` to `get_ast`
- Tools table: all 7 tool names updated to unprefixed names; `ingest_code` replaces `cpp_export_to_graphdb`
- Error envelope example: `cpp_get_definition` → `get_definition`
- Graph database backends section: `cpp_export_to_graphdb` → `ingest_code`
- Testing section: updated expected count line
- Added `## Migration from 0.2.x` section with 7-row old→new migration table

### ADR-16 (`/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/adr-16.md`)
- Added `> **v5 note:**` annotation after Decision section explaining the `cpp_export_to_graphdb` → `ingest_code` rename

### ADR-17 (`/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/adr-17.md`)
- Three body-text refs to `tools/export_to_graphdb.py` annotated with `(renamed to tools/ingest_code.py in v5)` or `(renamed to ingest_code.py in v5)`. Historical claims not rewritten.

### ADR-18 (`/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/adr-18.md`)
- Added `> **v5 note:**` annotation in Forces section noting the `cpp_export_to_graphdb` → `ingest_code` rename for tests bound to this ADR

### Wiki: cpp-mcp.md (`/Users/husam/workspace/wiki/pages/code/cpp-mcp.md`)
- Added `version: 0.3.0` to frontmatter
- Module layout: `export_to_graphdb.py` → `ingest_code.py` with rename annotation
- Tools table: all 7 tool rows updated to unprefixed names; `ingest_code` includes rename note
- Graph DB section header: updated to `ingest_code`
- CI/CD artifacts: version bumped 0.2.0 → 0.3.0 in wheel filenames

### Wiki: cpp-mcp-v4.md (`/Users/husam/workspace/wiki/pages/code/cpp-mcp-v4.md`)
- Appended `## Tools renamed in v5` section before References with cross-reference to cpp-mcp.md and handoff/v5/

### Wiki: cpp-mcp-codexgraph-gap.md (`/Users/husam/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md`)
- S1: `cpp_query_graphdb` → `query_graphdb` (unprefixed, per v5 rename convention)
- S2: `cpp_translate_query` → `translate_query` (unprefixed, per v5 rename convention)

### Wiki: index.md (`/Users/husam/workspace/wiki/index.md`)
- cpp-mcp entry: updated to mention v0.3.0 and the rename
- cpp-mcp-v4 entry: appended "Note: tools renamed in v5" cross-reference

## Deviations from plan

1. The plan says to bump the cpp-mcp.md "version line" — the page had no explicit version field.
   Added `version: 0.3.0` to frontmatter instead.
2. ADR-18 body did not directly reference `export_to_graphdb` by filename, only indirectly via
   "all seven tool stories". Added the annotation in the Forces section where the seven tools
   are mentioned contextually.
3. `REQUIREMENTS.md` and a pyproject.toml test-marker string show up in the informational grep.
   Both are historical/non-gated and correctly excluded per ADR-21. No action taken.

## Exit criteria results

| Gate | Command | Result |
|---|---|---|
| Informational grep | `grep -RIE 'cpp_(get\|export)_' --exclude-dir=.git --exclude-dir=.claude --exclude=CHANGELOG.md --exclude=README.md . \|\| true` | Non-gating; only REQUIREMENTS.md + pyproject marker hit (expected) |
| README sentinel | `grep -F 'cpp_export_to_graphdb' README.md && grep -F 'ingest_code' README.md` | PASS (exit 0) |
| Wiki index sentinel | `grep -F '0.3.0' ~/workspace/wiki/index.md` | PASS (exit 0) |

All named signals clear. No LINT_FAIL / BUILD_FAIL / TEST_FAIL emitted (S3 has no ruff/pytest gates per plan.md — exit criteria are grep-only).

## Follow-ups

- S4 (version bump + CHANGELOG) still pending in scope for next developer pass.
- `REQUIREMENTS.md` still contains v1 tool names with `cpp_` prefix — it is a historical v1 spec doc and out of S3 scope per plan.md. Flag for doc-writer if desired.
- pyproject.toml test marker `SC_USM7_3` contains `cpp_get_ast` string — this is a pytest marker label (not a tool call site) and is excluded from ADR-21 grep gate. Flag for S4 cleanup if desired.
