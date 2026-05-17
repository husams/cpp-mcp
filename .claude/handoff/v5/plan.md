# Plan — cpp-mcp v5 pure-rename release (0.2.0 → 0.3.0)

**Status:** ready-for-developer
**Date:** 2026-05-17
**run_id:** cpp-mcp-v5-rename
**Single-PR mandate:** all four stories land in one PR titled `v5: tool rename (drop cpp_ prefix; export_to_graphdb → ingest_code)`.
**Toolchain:** Python + `uv` + `pytest` + `ruff` (per `python-conventions`).
**Parallel-safe:** **false.** Stories R1→R2→R3→R4 are tightly sequential; R2 cannot pass until R1 lands, R3/R4 documentation only stabilizes after R1.

## Goal

Rename the seven MCP tools (drop `cpp_` prefix; `cpp_export_to_graphdb` → `ingest_code`), regenerate fixtures, retarget all tests/docs, bump to `0.3.0`. Zero behavior change. Test parity is the hard gate: **618 pass + 6 skip unit; 18 pass integration** (v4 baseline).

---

## Story S1 — US-V5-R1: Rename tool wire names in the server registry

**AC covered:** AC-R1-1, AC-R1-2, AC-R1-3, AC-R1-4, AC-R1-5.
**ADR refs:** ADR-19, ADR-20.
**Depends on:** none.
**Parallel-safe:** no.

### Files to change
- `src/cpp_mcp/tools/get_ast.py` — update `name=` to `"get_ast"`.
- `src/cpp_mcp/tools/get_definition.py` — `name="get_definition"`.
- `src/cpp_mcp/tools/get_references.py` — `name="get_references"`.
- `src/cpp_mcp/tools/get_type_info.py` — `name="get_type_info"`.
- `src/cpp_mcp/tools/get_header_info.py` — `name="get_header_info"`.
- `src/cpp_mcp/tools/get_preprocessor_state.py` — `name="get_preprocessor_state"`.
- `src/cpp_mcp/tools/__init__.py` — update import path from `export_to_graphdb` to `ingest_code` (and any re-exports).
- `src/cpp_mcp/core/error_envelope.py` — replace `cpp_*` strings in `DEPENDENCY_MISSING` (and any other tool-name wording) with new names.
- `src/cpp_mcp/server.py` (or wherever tools are registered/imported) — repoint import to `cpp_mcp.tools.ingest_code`.
- `tests/fixtures/expected_tool_descriptions.py` — regenerate to new names.
- `tests/fixtures/expected_schemas/*.json` (or `.py`) — regenerate; diff must show only `name`-field changes.

### File renames (git mv)
- `git mv src/cpp_mcp/tools/export_to_graphdb.py src/cpp_mcp/tools/ingest_code.py` and inside the file set `name="ingest_code"`; rename the registered function/module symbol where it would otherwise drift.

### Cache invariant (ADR-19)
- Do NOT add tool-name to any cache key in `src/cpp_mcp/core/tu_cache.py`.

### Exit criteria (must all exit 0)
```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/unit/test_tool_registration.py -q --no-header
uv run python -c "from cpp_mcp.tools import ingest_code; assert ingest_code is not None"
! grep -RIn "tool.\\?name\\|\"cpp_\\|'cpp_" src/cpp_mcp/core/tu_cache.py
```

---

## Story S2 — US-V5-R2: Update all tests to call tools by their new names

**AC covered:** AC-R2-1, AC-R2-2, AC-R2-3, AC-R2-4.
**ADR refs:** ADR-20 (BDD file renames), ADR-21 (grep gate).
**Depends on:** S1.
**Parallel-safe:** no.

### Files to change
- All `tests/**/*.py` containing `client.call_tool("cpp_...")` — replace with new names.
- All BDD step modules under `tests/bdd/steps/` referencing old tool names — replace.
- BDD `.feature` files under `tests/bdd/features/` if they encode tool names — replace.
- Any test helper that hard-codes old names (search `tests/conftest.py`, `tests/integration/`, `tests/bdd/conftest.py`).

### File renames (git mv, preserves history)
- `git mv tests/bdd/test_export_to_graphdb.py tests/bdd/test_ingest_code.py`
- `git mv tests/bdd/test_export_to_indradb.py tests/bdd/test_ingest_code_indradb.py`
- Other `tests/bdd/test_get_*.py` filenames stay; only in-file tool names change.

### Exit criteria (must all exit 0; hard test-parity gate)
```bash
uv run ruff format --check .
uv run ruff check .

# Authoritative grep gate (ADR-21)
! grep -RIE 'cpp_(get|export)_' src/ tests/

# BDD collection sanity (no dropped files post-rename)
uv run pytest --collect-only -q tests/bdd/

# Unit parity gate (v4 baseline: 618 passed, 6 skipped)
uv run pytest -q --no-header
# Verify: line matches "618 passed, 6 skipped" exactly.

# Integration parity gate (v4 baseline: 18 passed)
uv run pytest -m integration -q --no-header
# Verify: line matches "18 passed" exactly.

# Registry shape (AC-R1-4)
uv run python -c "from cpp_mcp.server import mcp; names = [t.name for t in mcp._tool_manager.list_tools()]; assert len(names) == 7, names; assert not any('cpp_' in n for n in names), names; assert 'ingest_code' in names; print(names)"
```
> Note: if the FastMCP introspection accessor differs in the v4 server, developer adjusts to the equivalent (`mcp.list_tools()` async or `_tool_manager._tools` keys) — the contract is "7 tools, none contain `cpp_`, `ingest_code` present."

---

## Story S3 — US-V5-R3: Update documentation and wiki

**AC covered:** AC-R3-1, AC-R3-2, AC-R3-3, AC-R3-4.
**ADR refs:** ADR-21 (informational grep covers docs).
**Depends on:** S1 (names must be stable in code first).
**Parallel-safe:** no (must precede R4 merge marker).

### Files to change
- `README.md` — replace tool-name references with new names; add a `## Migration from 0.2.x` section with the seven-row old→new table.
- `.claude/handoff/v5/adr-16.md`, `adr-17.md`, `adr-18.md` (or wherever ADR-16/17/18 live — likely `.claude/handoff/v3/` or `v4/`) — body-text references get an inline `(renamed to \`new_name\` in v5)` annotation. Do NOT rewrite historical claims.
  - Developer: locate via `find .claude/handoff -name 'adr-1[678].md'`.
- `~/workspace/wiki/pages/code/cpp-mcp.md` — update tool names; bump version line to 0.3.0.
- `~/workspace/wiki/pages/code/cpp-mcp-v4.md` — append a note: "Tools renamed in v5 — see [[pages/code/cpp-mcp]] and `.claude/handoff/v5/`."
- `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md` — reaffirm `query_graphdb` / `translate_query` (unprefixed) for S1/S2.
- `~/workspace/wiki/index.md` — description lines for cpp-mcp pages mention v0.3.0 + new names.

### Exit criteria (must all exit 0)
```bash
# Informational grep — review hits manually; this is non-gating per ADR-21 but
# any hit in README.md/docs/ outside the migration table or "(renamed to …)"
# annotations is a defect.
grep -RIE 'cpp_(get|export)_' --exclude-dir=.git --exclude-dir=.claude --exclude=CHANGELOG.md --exclude=README.md . || true

# README must contain the migration table (sentinel grep)
grep -F 'cpp_export_to_graphdb' README.md && grep -F 'ingest_code' README.md

# Wiki index updated
grep -F '0.3.0' ~/workspace/wiki/index.md
```

---

## Story S4 — US-V5-R4: Version bump and changelog

**AC covered:** AC-R4-1, AC-R4-2, AC-R4-3.
**ADR refs:** ADR-21 (no shim → no grep exception).
**Depends on:** S1, S2, S3.
**Parallel-safe:** no.

### Files to change
- `pyproject.toml` — `version = "0.2.0"` → `version = "0.3.0"`.
- `CHANGELOG.md` — create if missing; add a `## 0.3.0 — 2026-05-17` section with:
  - One-line rationale linking `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md`.
  - The seven-row old→new table.
  - Explicit "**Breaking:** no compatibility aliases; 0.2.x clients receive MCP `tool not found`."
- Do NOT add any alias module, re-export, or shim (AC-R4-3, ADR-20, ADR-21).

### Exit criteria (must all exit 0)
```bash
# Version bump landed
grep -E '^version = "0\.3\.0"' pyproject.toml

# Changelog exists with new version
grep -F '0.3.0' CHANGELOG.md
grep -F 'ingest_code' CHANGELOG.md

# Full lint + test suite green
uv run ruff format --check .
uv run ruff check .
uv run pytest -q --no-header               # 618 passed, 6 skipped
uv run pytest -m integration -q --no-header # 18 passed

# Final authoritative grep gate (ADR-21)
! grep -RIE 'cpp_(get|export)_' src/ tests/

# No alias modules sneaked in
! test -f src/cpp_mcp/tools/export_to_graphdb.py
! test -f src/cpp_mcp/tools/cpp_get_ast.py
```

---

## Cross-story exit gate (run before opening the PR)

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q --no-header
uv run pytest -m integration -q --no-header
! grep -RIE 'cpp_(get|export)_' src/ tests/
grep -E '^version = "0\.3\.0"' pyproject.toml
```
All six must exit 0. Test-count parity is enforced by visual diff against v4 baseline (`618 passed, 6 skipped` unit; `18 passed` integration). Any deviation blocks merge.

---

## Tests

No new tests are authored in v5 (pure rename). Existing tests are retargeted only:
- `tests/unit/test_tool_registration.py` — exercises AC-R1-4 (seven tools, no `cpp_` prefix).
- `tests/fixtures/expected_schemas/`, `tests/fixtures/expected_tool_descriptions.py` — regenerated.
- `tests/bdd/test_ingest_code.py`, `tests/bdd/test_ingest_code_indradb.py` — renamed from `test_export_to_*.py`.
- All other unit + integration + BDD modules — call-site updates only.

If any test must be added/removed to maintain parity, that change requires explicit justification in `logs/developer-<story-slug>.md` and surfaces as a `QA_DEFECT` candidate.

---

## Risks / Out of scope

**Risks** (mitigations from design.md retained):
- FastMCP introspection path in the registry-shape exit check may differ; developer adapts to actual API (contract preserved).
- BDD pytest collection drop post-`git mv` — mitigated by `--collect-only` sanity check in S2 exit criteria.
- Schema fixture diff containing non-name changes — developer must visually diff and reject any non-name delta.
- Hidden `cpp_*` in docs outside the gate scope — covered by S3 informational grep and AC-R3-* manual review.

**Out of scope** (from requirements.md):
- New tools (`query_graphdb`, `translate_query`) — separate handoff.
- Schema changes (`access_kind`, FIELD/GLOBAL_VARIABLE split) — separate handoffs.
- Compatibility aliases — explicitly forbidden (AC-R4-3, ADR-20, ADR-21).
- Any behavior change to argument shapes, return shapes, error codes, cache semantics, or graph wire format.

---

## References

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/requirements.md` (stories US-V5-R1..R4, AC IDs)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/design.md` (dependency order, exit-criteria contract, risks)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-19.md` (cache invariant)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-20.md` (single file rename via `git mv`; no shims)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-21.md` (authoritative grep gate)
- `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md` (v5 roadmap rationale)
- Memory: `project_v4_e2e_tests_shipped.md`, `project_v4_live_verification.md` (baseline test counts)
- Cognee tag: `task:cpp-mcp-v5-rename`
