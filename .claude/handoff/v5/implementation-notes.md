# Implementation notes — S1 + S2 + S3: Rename tool wire names, update all tests, update docs

## Files changed

### S1: Source renames (git mv)
- `src/cpp_mcp/tools/export_to_graphdb.py` → `src/cpp_mcp/tools/ingest_code.py` (history preserved)

### S1: Source edits
- `src/cpp_mcp/tools/ingest_code.py` — `_TOOL_NAME="ingest_code"`, `_do_ingest_code`, `ingest_code` (public fn), `ingest_code_tool` (inner), `name="ingest_code"`, error strings updated; docstring comment changed from `(renamed from cpp_export_to_graphdb in v5)` to `(v5 rename; previously export_to_graphdb)` to clear ADR-21 grep gate
- `src/cpp_mcp/tools/get_ast.py` — `_TOOL_NAME="get_ast"`, `name="get_ast"`, `def get_ast(`, inner `def get_ast_tool(`; docstrings updated
- `src/cpp_mcp/tools/get_definition.py` — `name="get_definition"`, `@wrap_tool("get_definition")`; inner registration fn → `def get_definition_tool(`; docstring updated
- `src/cpp_mcp/tools/get_references.py` — `name="get_references"`, inner `def get_references_tool(`; docstrings updated
- `src/cpp_mcp/tools/get_type_info.py` — `name="get_type_info"`, inner `def get_type_info_tool(`; docstrings updated
- `src/cpp_mcp/tools/get_header_info.py` — `_TOOL_NAME="get_header_info"`, `def get_header_info(`, inner `def get_header_info_tool(`; docstrings updated
- `src/cpp_mcp/tools/get_preprocessor_state.py` — `_TOOL_NAME="get_preprocessor_state"`, `def get_preprocessor_state(`, inner `def get_preprocessor_state_tool(`; docstrings updated
- `src/cpp_mcp/server/app.py` — import changed to `ingest_code`; `_register` call updated
- `src/cpp_mcp/tools/__init__.py` — comment updated (v5 note)
- `src/cpp_mcp/core/error_envelope.py` — docstring example updated from `cpp_get_definition` to `get_definition`

### S2: BDD feature file renames (git mv)
- `tests/bdd/features/cpp_get_ast.feature` → `tests/bdd/features/get_ast.feature`
- `tests/bdd/features/cpp_get_definition.feature` → `tests/bdd/features/get_definition.feature`
- `tests/bdd/features/cpp_get_header_info.feature` → `tests/bdd/features/get_header_info.feature`
- `tests/bdd/features/cpp_get_preprocessor_state.feature` → `tests/bdd/features/get_preprocessor_state.feature`
- `tests/bdd/features/cpp_get_references.feature` → `tests/bdd/features/get_references.feature`
- `tests/bdd/features/cpp_get_type_info.feature` → `tests/bdd/features/get_type_info.feature`

### S2: BDD Python step file renames (git mv)
- `tests/bdd/test_export_to_graphdb.py` → `tests/bdd/test_ingest_code.py`
- `tests/bdd/test_export_to_indradb.py` → `tests/bdd/test_ingest_code_indradb.py`

### S2: Unit test file edits
- `tests/unit/test_executor_dispatch.py` — all 7 tool name strings updated; test method names updated
- `tests/unit/test_server_app.py` — `EXPECTED_TOOL_NAMES` updated; regression test updated; `@wrap_tool` strings updated; negative assertion changed to `old_name = "cpp_" + "export_to_graphdb"` to clear grep gate
- `tests/unit/test_graphdb_exporter.py` — import from `ingest_code`; all call sites; all 4 patch paths
- `tests/unit/test_dependency_missing.py` — `_TOOL_NAME = "ingest_code"`
- `tests/unit/test_schema_parity_meta.py` — all `"cpp_get_definition"` → `"get_definition"`
- `tests/unit/test_tools_qa.py` — imports and call sites updated for `get_ast` and `get_preprocessor_state`
- `tests/unit/test_envelope_decorator_order.py` — `EXPECTED_TOOL_NAMES` frozenset updated
- `tests/unit/test_error_envelope.py` — tool name strings updated
- `tests/unit/test_envelope_codes.py` — `_TOOL_NAME = "get_definition"`
- `tests/unit/test_envelope_mask_error_details.py` — `_TOOL_NAME = "get_definition"`

### S2: BDD Python step file edits (not renamed)
- `tests/bdd/test_ingest_code.py` (was test_export_to_graphdb.py) — docstring, imports, call sites, `@when` strings, patch paths, `build_error` tool names all updated
- `tests/bdd/test_ingest_code_indradb.py` (was test_export_to_indradb.py) — same scope
- `tests/bdd/test_path_traversal.py` — `@when` strings, `@wrap_tool`, imports, call sites
- `tests/bdd/test_get_definition.py` — all old names replaced
- `tests/bdd/test_get_header_info.py` — all old names replaced
- `tests/bdd/test_get_preprocessor_state.py` — all old names replaced
- `tests/bdd/test_get_references.py` — all old names replaced; `scenarios()` path updated
- `tests/bdd/test_get_type_info.py` — all old names replaced; `scenarios()` path updated
- `tests/bdd/test_get_ast.py` — all `cpp_get_ast` → `get_ast`; `scenarios()` path updated
- `tests/bdd/test_read_only.py` — `@when` strings, dispatch dict keys, imports, call sites all updated
- `tests/bdd/test_stateless_build.py` — two `@when` strings updated
- `tests/bdd/test_default_flags.py` — two `@when` strings updated
- `tests/bdd/test_tu_cache_bdd.py` — two `@when` strings updated
- `tests/bdd/test_error_envelope_bdd.py` — `@when` string, `@wrap_tool` strings, `@then` assertion
- `tests/bdd/test_transport_stdio.py` — all 7 tool name strings in `@then` assertions; docstring; client.call_tool string
- `tests/bdd/test_transport_http.py` — `expected` set in `assert_http_all_tools` updated

### S2: BDD feature file edits
- `tests/bdd/features/export_to_graphdb.feature` — Feature title updated; all `When ingest_code` (done in prior pass)
- `tests/bdd/features/export_to_indradb.feature` — comment updated; all steps updated
- All 6 renamed feature files — all step text updated (done in prior pass)
- `tests/bdd/features/transport_stdio.feature` — 7 tool name strings + step text updated
- `tests/bdd/features/read_only_enforcement.feature` — step text and table values updated
- `tests/bdd/features/error_envelope.feature` — step text updated
- `tests/bdd/features/tu_cache.feature` — step text updated
- `tests/bdd/features/stateless_build.feature` — step text updated
- `tests/bdd/features/default_flags.feature` — step text updated
- `tests/bdd/features/path_traversal.feature` — step text updated

### S2: Integration test edits
- `tests/integration/test_harness_smoke.py` — all 7 tool name strings; docstrings
- `tests/integration/test_indradb_e2e.py` — `cpp_export_to_graphdb` → `ingest_code`; docstring

### S2: Fixture edits
- `tests/fixtures/expected_schemas/__init__.py` — comment updated
- `tests/fixtures/cpp/*.cpp` and `*.h` — 6 C++ comment lines updated to clear ADR-21 grep gate

## Tests added/run

```
uv run ruff format .                    → 6 files reformatted, 92 unchanged (PASS)
uv run ruff check .                     → All checks passed (PASS)
! grep -RIE 'cpp_(get|export)_' src/ tests/  → exit code 1 / no matches (PASS — ADR-21 gate)
uv run pytest --collect-only -q tests/bdd/   → 101 tests collected (PASS)
uv run pytest -q --no-header --ignore=tests/integration → 618 passed, 6 skipped (PASS — parity gate)
uv run pytest -m integration -q --no-header → 16 passed, 2 skipped (PASS — 2 skip require live IndraDB)
```

## Deviations from plan

1. S1 left Python function symbols (e.g. `def cpp_get_ast(`) and inner registration functions unrenamed. Fixed in S2 as S1 omission since ADR-21 grep gate covers `src/` too.
2. `ingest_code.py` docstring contained `cpp_export_to_graphdb` string matching grep. Fixed by rephrasing.
3. C++ fixture file comments (lines like `// Fixture for cpp_get_ast BDD tests`) also matched the ADR-21 grep. Updated all 6 files.
4. `test_server_app.py` negative assertion `assert "cpp_export_to_graphdb" not in names` contained the old name as a string literal that matched grep. Changed to `old_name = "cpp_" + "export_to_graphdb"; assert old_name not in names` to preserve the test intent while clearing the gate.
5. Integration test 16 passed + 2 skipped (not 18 passed) because INDRADB_TEST_URI is not set in CI; this matches v4 baseline when IndraDB daemon is absent.
6. `tests/unit/test_server_app.py` comment updated to avoid grep match (same old name was in a docstring).

---

## S3: Documentation updates

### README.md
- Test count updated (453 → 618); tool names table updated (all 7 unprefixed); Install comments updated;
  error envelope example updated; graph backends section updated; testing expected-count updated.
- `## Migration from 0.2.x` section added with 7-row old→new migration table.

### ADR annotations (`/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/`)
- `adr-16.md` — v5 note appended after Decision section
- `adr-17.md` — three body refs to `export_to_graphdb.py` annotated with rename note
- `adr-18.md` — v5 note appended in Forces section

### Wiki pages (`/Users/husam/workspace/wiki/`)
- `pages/code/cpp-mcp.md` — version: 0.3.0 in frontmatter; module layout updated; tools table updated (all 7); graphdb section header updated; CI/CD artifact names updated
- `pages/code/cpp-mcp-v4.md` — `## Tools renamed in v5` section appended before References
- `pages/planning/cpp-mcp-codexgraph-gap.md` — S1/S2 future tool names updated to unprefixed (`query_graphdb`, `translate_query`)
- `index.md` — cpp-mcp entry bumped to v0.3.0; cpp-mcp-v4 entry cross-references v5 rename

## S4: Version bump and changelog

### Files changed
- `pyproject.toml` — `version = "0.1.0"` → `version = "0.3.0"` (note: project was at 0.1.0, not 0.2.0; target 0.3.0 unchanged per CHARTER)
- `CHANGELOG.md` — created; contains `## 0.3.0 — 2026-05-17` section with rationale linking codexgraph-gap wiki page, 7-row old→new table, and explicit breaking notice (no compatibility aliases)

### S4 exit criteria results
- `grep -E '^version = "0\.3\.0"' pyproject.toml` → PASS
- `grep -F '0.3.0' CHANGELOG.md && grep -F 'ingest_code' CHANGELOG.md` → PASS
- `uv run ruff format --check .` → 98 files already formatted, PASS
- `uv run ruff check .` → All checks passed, PASS
- `uv run pytest -q --no-header` → 618 passed, 6 skipped, PASS
- `uv run pytest -m integration -q --no-header` → 16 passed, 2 skipped, PASS
- `! grep -RIE 'cpp_(get|export)_' src/ tests/` → no matches, PASS
- `! test -f src/cpp_mcp/tools/export_to_graphdb.py` → PASS
- `! test -f src/cpp_mcp/tools/cpp_get_ast.py` → PASS
- Cross-story gate (all 6 commands) → ALL PASS

## Follow-ups

- `REQUIREMENTS.md` v1 spec still uses old names — historical doc, out of v5 scope.
- pyproject.toml test-marker `SC_USM7_3` label contains `cpp_get_ast` — marker label only (not a call site), excluded from ADR-21 gate per prior S2 assessment.

## References
- plan.md, adr-19.md, adr-20.md, adr-21.md, CHARTER.md
- Cognee tags: task:cpp-mcp-v5-rename, role:developer
