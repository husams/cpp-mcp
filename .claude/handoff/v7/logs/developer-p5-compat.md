run_id: cpp-mcp-v7-s1
story: P5 — v1 backward-compat tests + describe_v2 shape + round-trip + tool-signature snapshot
role: developer
date: 2026-05-17

---

## Skills loaded

- python-conventions (loaded first — pyproject.toml + uv.lock present)

## Skills considered but not loaded

- cpp-conventions: no CMakeLists.txt changes in P5 (test-only story, no C++ compilation)
- implement-story: not loaded; task dispatch used direct plan.md reference
- simplify: not loaded; P5 is additive test code, no refactoring scope

## Pre-work orientation

Read: CHARTER.md, plan.md (Story P5), design.md §8 §9, implementation-notes.md (P1-P4), adr-25.md.
Grep-verified: test_schema_introspector.py skew tests use SCHEMA_VERSION constant (not hardcoded "v1"); test_mismatch_note_when_old_schema_version uses "v0" as the old version → no breakage from v1→v2 bump.
Verified: integration test lines 129 and 277 hard-coded "v1" (P1 follow-up, this story's scope).

## FastMCP API probe

Command: `uv run python -c "from cpp_mcp.server.app import build_server; mcp=build_server(); import asyncio,json; tools=asyncio.run(mcp.list_tools()); ..."`

Finding: `FunctionTool.inputSchema` does NOT exist on this fastmcp version. Use `tool.to_mcp_tool().inputSchema` instead. Verified for all three graph tools. Committed snapshot captured.

## Commands run

1. `uv run ruff format tests/unit/graphdb/test_describe_v1_compat.py ...` → 4 files reformatted
2. `uv run ruff check tests/unit/graphdb/` → found F401 (unused pytest import in 3 files), E501 (docstring line > 100), RUF002 (en-dash in docstring)
3. `uv run ruff check tests/unit/graphdb/ --fix` → 4 errors fixed (2 F401 auto-fixed)
4. Manual edits: removed pytest import from test_describe_v1_compat.py (ruff couldn't fix it because it had no other pytest usage), shortened docstring line in test_describe_v1_compat.py, replaced en-dash with hyphen in test_describe_v2_shape.py docstring
5. `uv run ruff check tests/unit/graphdb/` → clean (0 errors)
6. `uv run pytest tests/unit/graphdb/test_describe_v1_compat.py tests/unit/graphdb/test_describe_v2_shape.py tests/unit/graphdb/test_mcp_tool_signatures.py tests/unit/graphdb/test_round_trip.py -x -q` → 27 passed
7. `uv run pytest tests/unit -x -q` → 847 passed, 4 skipped (baseline 820 + 27 new)

## Deviations from plan.md

1. Round-trip test (test_round_trip.py): plan says "small C++ source → export to fake driver → re-read". libclang.dylib is not loadable on this macOS host (confirmed P2). Used NodeRecord/EdgeRecord construction directly — same semantic coverage (export output shape → introspector read), no libclang dependency.
2. test_describe_v1_compat.py — test_describe_v1_graph_echoes_v1_schema_version: plan implies the response schema_version would be "v1". The introspector always returns SCHEMA_VERSION (code constant = "v2") regardless of the stored graph value; "v1" surfaces only as a skew note. Test asserts skew note presence (correct behavior per design §8) rather than asserting response=="v1".
3. pytest import removed from 3 test files — ruff F401; none of the P5 files use pytest.mark.parametrize or pytest.raises directly (parametrize in tool signatures test uses sorted() not @parametrize). Wait — test_mcp_tool_signatures.py DOES use @pytest.mark.parametrize; that import was kept. Only test_describe_v1_compat, test_describe_v2_shape, test_round_trip had unused pytest imports.

## Tool failures / retries

Pass 1: ruff check failed (F401 × 2 auto-fixable, E501 × 1, RUF002 × 1). Fixed all. Pass 2: clean.
Pass 1 pytest: 27/27 passed immediately. Full suite 847/847.

## Integration test update (P1 follow-up)

tests/integration/test_describe_graph_schema_e2e.py:
  - Line 129: `assert data["schema_version"] == "v1"` → `"v2"`
  - Line 277 (assert body): `"v1"` → `"v2"`
  - Line 272 (docstring): updated to reference "v2"
These integration tests run only under `pytest tests/integration` (marked @pytest.mark.integration @pytest.mark.indradb); they do not affect the unit gate.

## Artifacts written

- tests/unit/graphdb/test_describe_v1_compat.py (NEW)
- tests/unit/graphdb/test_describe_v2_shape.py (NEW)
- tests/unit/graphdb/test_mcp_tool_signatures.py (NEW)
- tests/unit/graphdb/test_round_trip.py (NEW)
- tests/unit/graphdb/fixtures/tool_signatures.json (NEW)
- tests/integration/test_describe_graph_schema_e2e.py (UPDATED — lines 129, 272, 277)
- .claude/handoff/v7/implementation-notes.md (UPDATED — P5 section appended)
- .claude/handoff/v7/logs/developer-p5-compat.md (THIS FILE)

## Exit gate results

| Gate | Command | Result |
|------|---------|--------|
| Formatter | ruff format (4 files) | PASS — reformatted, no errors |
| Linter | ruff check tests/unit/graphdb/ | PASS — 0 errors after fixes |
| P5 tests | pytest test_describe_v1_compat ... test_round_trip -x -q | PASS — 27/27 |
| Full unit suite | pytest tests/unit -x -q | PASS — 847 passed, 4 skipped, 0 fail |

All named signals: CLEAR.
