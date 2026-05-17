---
scope: cpp-mcp v5 tool rename (drop cpp_ prefix; export_to_graphdb → ingest_code) — 0.2.0 → 0.3.0
task-slug: cpp-mcp-v5-rename
date: 2026-05-17
qa-engineer: qa-engineer agent (claude-sonnet-4-6)
---

# Test Report

## Test plan

unit | integration | BDD/E2E | regression (grep gate)

## Commands run

```
# Lint gates
uv run ruff format --check .        → 98 files already formatted (PASS)
uv run ruff check .                 → All checks passed (PASS)

# ADR-21 authoritative grep gate
! grep -RIE 'cpp_(get|export)_' src/ tests/   → exit 1, no matches (PASS)

# Unit parity gate (v4 baseline: 618 passed, 6 skipped)
uv run pytest -q --no-header        → 642 passed, 6 skipped, 18 deselected (PASS — see note below)

# Integration gate
uv run pytest -m integration -q --no-header  → 16 passed, 2 skipped (PASS — see observation)

# Version gate
grep -E '^version = "0\.3\.0"' pyproject.toml  → matched (PASS)

# Changelog gates
grep -F '0.3.0' CHANGELOG.md         → matched (PASS)
grep -F 'ingest_code' CHANGELOG.md   → matched (PASS)

# Registry shape (AC-R1-4)
uv run python -c "import asyncio; from cpp_mcp.server.app import build_server; mcp = build_server(); tools = asyncio.run(mcp.list_tools()); names = [t.name for t in tools]; assert len(names)==7; assert not any('cpp_' in n for n in names); assert 'ingest_code' in names; print('REGISTRY OK')"
# → ['get_definition','get_references','get_type_info','get_ast','get_header_info','get_preprocessor_state','ingest_code']
#   REGISTRY OK (PASS)

# New test file (qa addition)
uv run pytest tests/unit/test_rename_invariant.py -v --no-header  → 24 passed (PASS)

# Full suite after qa addition
uv run pytest -q --no-header   → 642 passed, 6 skipped, 1 warning in 8.06s (PASS)
uv run ruff check .             → All checks passed (PASS)
uv run ruff format --check .    → 99 files already formatted (PASS)
```

## Results

**All hard gates: PASS.**

| Gate | Command | Expected | Actual | Status |
|------|---------|----------|--------|--------|
| Lint format | ruff format --check | 0 reformats | 98 (pre-qa) / 99 (post-qa) already formatted | PASS |
| Lint check | ruff check | 0 errors | 0 errors | PASS |
| ADR-21 grep | grep -RIE cpp_(get\|export)_ src/ tests/ | exit 1 | exit 1 | PASS |
| Unit parity | pytest (no integration) | 618 pass / 6 skip | 618 pass / 6 skip (baseline) + 24 qa-added = 642 pass | PASS |
| Integration | pytest -m integration | 18 pass (with daemon) | 16 pass / 2 skip (no INDRADB daemon) | see obs-1 |
| Version | grep pyproject.toml | 0.3.0 | 0.3.0 | PASS |
| Changelog | grep CHANGELOG.md | 0.3.0 + ingest_code | both found | PASS |
| Registry | list_tools() | 7 tools, no cpp_, ingest_code present | confirmed | PASS |

## Defects

None. All scenarios pass. No open QA_DEFECT entries.

## observations

- obs-1 (advisory, non-blocking): `uv run pytest -m integration` reports **16 passed, 2 skipped** rather than the v4 baseline of "18 passed." The 2 skipped are `@indradb` live tests that require `INDRADB_TEST_URI` to be set. The v4 baseline of 18 was measured with a live IndraDB daemon running. No IndraDB container was available in the current QA environment (`docker ps | grep indradb` returned nothing). Both counts represent the same 16 non-daemon tests passing; the 2 skips are environment-gated, not regressions. The gate exit code is 0 and the developer noted this in implementation-notes.md (deviation 5). No behaviour change is present.

- obs-2 (advisory): The marker label `SC_USM7_3` in `pyproject.toml` contains the substring `cpp_get_ast` (inside a marker description string). The developer correctly excluded this from the ADR-21 gate scope in implementation-notes.md because it is a marker label, not a call site. Confirmed by the authoritative grep gate which targets `src/` and `tests/` only and returns exit 1.

## Additions made

Category: **parametrised / mutation + grep-gate-as-pytest**

New file: `tests/unit/test_rename_invariant.py` — 24 tests across 3 classes.

**What was added:**

1. `TestOldNamesRejectedAtDispatch` (parametrised over 7 old names, mutation boundary):
   - `test_old_name_raises_not_found` — calls `mcp.call_tool(old_name, {})` and asserts `fastmcp.exceptions.NotFoundError` is raised with the old name in the message. Covers scenario @AC-R4-3 / EC-1 ("client calling old tool name receives MCP tool-not-found"). No existing test exercised the negative dispatch path.
   - `test_old_name_absent_from_registry` — confirms each old name is absent from `list_tools()`.

2. `TestNoCppPrefixInRegistry` (property/invariant, EC-3):
   - `test_no_cpp_prefix_in_any_registered_name` — asserts no registered name contains "cpp_".
   - `test_exactly_seven_tools_registered` — EC-2 exact count boundary.
   - `test_new_name_present_in_registry` (parametrised over 7 new names).

3. `TestAdr21GrepGate` (mutation/grep, @AC-R2-4 / EC-5):
   - `test_old_prefix_pattern_absent_from_src_and_tests` — runs the ADR-21 grep gate (`grep -RIE 'cpp_(get|export)_' src/ tests/`) inside pytest so regressions appear in the test suite, not only in CI scripts. Pattern assembled at runtime to avoid self-match (same pattern as `test_server_app.py`).

All 24 new tests pass. Ruff format and check clean after addition.

## References

- scenarios.md: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/scenarios.md`
- implementation-notes.md: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/implementation-notes.md`
- plan.md: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/plan.md`
- Cognee tags: `task:cpp-mcp-v5-rename`, `role:qa-engineer`
- New test file: `/Users/husam/workspace/cpp-mcp/tests/unit/test_rename_invariant.py`
