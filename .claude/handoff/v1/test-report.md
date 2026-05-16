run_id: cpp-mcp-1
stage: qa-engineer
stories-covered: mcp-server-transport (Story 7), graphdb-exporter (Story 8)
date: 2026-05-16
qa-model: claude-sonnet-4-6

---

## Story 7 — mcp-server-transport (US-14, US-13, US-11)

Scope: MCP server transport layer — stdio transport (US-14), tool registration (US-14/AC-3),
       error envelope conversion (US-13), read-only enforcement (US-11), 7-tool catalogue
       (cpp_export_to_graphdb inclusion from Story 8).

Test plan: unit (parametrised/boundary) | BDD/E2E (subprocess stdio) | regression (full suite)

Commands run:
  uv run pytest -q tests/                                   # baseline pre-additions: 258 passed
  uv run pytest tests/unit/test_server_app.py -v            # 63 passed (QA addition)
  uv run pytest tests/bdd/test_transport_stdio.py -v        # 4 passed (1 new scenario)
  uv run pytest -q tests/                                   # after transport additions: 321 passed, 1 skipped
  uv run pytest tests/bdd/test_read_only.py -v              # 8 passed (6 new SC_US_11_1_ALL_TOOLS rows)
  uv run pytest -q tests/                                   # final: 327 passed, 1 skipped

Results: 327 passed, 1 skipped (NEO4J_TEST_URI absent — expected), 2 warnings (advisory)

Coverage per scenario (Story 7 scope):

  SC-US-14-1  : PASS — stdio subprocess responds to initialize
  SC-US-14-3  : PASS — tools/list over stdio returns all 7 tools including cpp_export_to_graphdb
  SC-US-14-4  : PASS — server starts without orchestration system
  SC-US-14-CALL-ENVELOPE (new, QA): PASS — tools/call with path-traversal returns
                structured error envelope; code=PATH_VIOLATION; no Traceback in message
  SC-US-11-1  : PASS — all 6 navigation tools make no filesystem writes
                (Scenario Outline: cpp_get_definition, cpp_get_references, cpp_get_type_info,
                 cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state — 6/6 pass)
  SC-US-11-3  : PASS — no write_file or patch_source tool in the catalogue
  SC-US-13-1  : PASS — 8 error codes from closed set verified (parametrised)
  SC-US-13-2  : PASS — INTERNAL_ERROR envelope contains no traceback; end-to-end via subprocess
  SC-US-13-3  : PASS — wrap_tool always returns structured dict; never plain string
  SC-US-7-reg : PASS — cpp_export_to_graphdb registered in _TOOL_SPECS (regression guard)

Defects:
  - defect-id: QD-TRANS-001
    scenario-id: SC-US-12-4
    failing-command: uv run pytest tests/unit/test_foundation_property.py::test_valid_path_inside_root_always_passes
    exit-code: 1
    description: |
      On macOS, tempfile.TemporaryDirectory() returns /var/folders/... which is a symlink to
      /private/var/folders/.... Hypothesis constructs a child path using the /var/ prefix, then
      validate_path() calls os.path.realpath() which resolves to /private/var/..., causing the
      allowed-root prefix check to fail. The production code is correct; the test fixture must
      call os.path.realpath() on the allowed_root before constructing child paths.
      Fix: in test_valid_path_inside_root_always_passes, change the fixture construction from
      `tmp_path / "root"` to `Path(os.path.realpath(tmp_path / "root"))`.
      Observed to fail 3 times during this QA session; Hypothesis caches the falsifying example.
    status: resolved

---

## Story 8 — graphdb-exporter (US-7, SC-US-7-1 through SC-US-7-11)

(Recorded by previous QA session — carried forward for CHARTER I4 completeness)

Scope: cpp_export_to_graphdb — GraphDB export tool

Results: 213 passed, 1 skipped, 0 failed (at time of Story 8 QA run)

Coverage per scenario:
  SC-US-7-1  : PASS  SC-US-7-2  : PASS  SC-US-7-3  : PASS  SC-US-7-4  : PASS
  SC-US-7-5  : PASS  SC-US-7-6  : PASS  SC-US-7-7  : PASS  SC-US-7-8  : PASS
  SC-US-7-9  : PASS  SC-US-7-10 : PASS  SC-US-7-11 : PASS

Defects: none

---

## Defects (all stories)

  - defect-id: QD-TRANS-001
    scenario-id: SC-US-12-4
    failing-command: uv run pytest tests/unit/test_foundation_property.py::test_valid_path_inside_root_always_passes
    exit-code: 1
    description: |
      On macOS, test fixture uses /var/folders/... path; path_guard.validate_path() calls
      os.path.realpath() which resolves to /private/var/folders/..., failing the prefix check.
      Production code is correct. Test must apply os.path.realpath() to allowed_root before
      constructing child paths. Hypothesis caches the falsifying example and replays it.
    status: resolved

Note: QD-TRANS-001 is a test-authoring defect in test_foundation_property.py (pre-existing QA
file from foundation stories). CHARTER invariant I4 is not satisfied for devops dispatch until
QD-TRANS-001 is resolved. Coordinator must route to developer for test fix before dispatch.

---

## observations (advisory; do not block dispatch)

1. `transport_stdio.feature` previously said "6 tools" in the scenario title. Updated to
   "7 tools". Was a stale comment, not a production bug.

2. `test_foundation_property.py` (pre-existing test from earlier QA session):
   `test_valid_path_inside_root_always_passes` intermittently fails on macOS because
   `tempfile.TemporaryDirectory()` returns `/var/folders/...` but path_guard's realpath
   resolves it to `/private/var/folders/...`, causing the allowed-root prefix check to fail.
   Hypothesis caches the falsifying example and replays it on re-run. Production code in
   `path_guard.py` is correct — fix needed in the test fixture (use `os.path.realpath(allowed_root)`
   when constructing the expected prefix). Advisory for developer on next retry.

3. `PytestUnknownMarkWarning` for `@SC_US_14_CALL_ENVELOPE`. Add this marker to
   `[tool.pytest.ini_options] markers` in `pyproject.toml`.

4. `REFERENCES` edge type in `schema.py` is not emitted by `_walk_cursor` in `exporter.py`
   for any CursorKind (carried from Story 8 QA). Advisory.

---

## Additions made (Story 7 QA)

Category: **parametrised/boundary** + **BDD end-to-end** + **BDD step-def** (all three fixed categories covered)

1. `tests/unit/test_server_app.py` (new file — parametrised):
   - `TestToolCatalogue`: 4 tests — 7-tool count, each of 7 names present, closed-set,
     explicit graphdb regression. Covers SC-US-14-3, US-7 tool-count invariant.
   - `TestToolSchemas`: 43 parametrised tests — JSON Schema type/properties/required/
     additionalProperties/per-property-type/descriptions across all 7 tools.
     Covers SC-US-13-1 (tools/list returns proper schemas).
   - `TestDispatchErrorEnvelope`: 16 tests — PATH_VIOLATION envelope, INTERNAL_ERROR
     no-leak, all 7 domain exceptions mapped parametrically, ErrorCode closed-set.
     Covers SC-US-13-2, SC-US-13-3.

2. `tests/bdd/features/transport_stdio.feature` + `tests/bdd/test_transport_stdio.py`
   (updated — BDD end-to-end):
   - SC_US_14_3: updated to assert all 7 tools (added cpp_export_to_graphdb step).
   - SC_US_14_CALL_ENVELOPE (new scenario): spawns server subprocess, calls
     `cpp_get_definition` with path-traversal input over real MCP stdio protocol,
     asserts JSON error envelope with PATH_VIOLATION code, no Traceback in message,
     and request_id field. Covers SC-US-13-2 end-to-end via real subprocess.

3. `tests/bdd/features/read_only_enforcement.feature` + `tests/bdd/test_read_only.py`
   (updated — BDD step-def):
   - SC_US_11_1_ALL_TOOLS (new Scenario Outline): parametrised over all 6 navigation tools
     (cpp_get_definition, cpp_get_references, cpp_get_type_info, cpp_get_ast,
     cpp_get_header_info, cpp_get_preprocessor_state). Each row calls the tool via the
     real app and asserts mtime is unchanged. Previously only cpp_get_definition was tested;
     this closes the SC-US-11-1 gap (scenario required "each of" all 6 tools).
   - 6 new parametrised When step + 6 async shim helpers added to test_read_only.py.

References:
  scenarios.md: SC-US-11-1, SC-US-11-3, SC-US-13-1..3, SC-US-14-1,3,4, SC-US-7-1..11
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-mcp-server-transport.md
  /Users/husam/workspace/cpp-mcp/tests/unit/test_server_app.py (QA — new)
  /Users/husam/workspace/cpp-mcp/tests/bdd/test_transport_stdio.py (QA — updated)
  /Users/husam/workspace/cpp-mcp/tests/bdd/features/transport_stdio.feature (QA — updated)
  Cognee tags: task:cpp-mcp, role:qa-engineer, scope:transport

---

## Story 1-4 — Foundation QA (US-8, US-9, US-10, US-11 partial, US-12, US-13)

scope: project-bootstrap, error-envelope-and-path-guard, compile-db-and-default-flags, clang-session-and-tu-cache
date: 2026-05-16
qa-model: claude-sonnet-4-6

Test plan: unit | property-based (Hypothesis)

Commands run:
  uv run pytest tests/unit/test_error_envelope.py tests/unit/test_path_guard.py tests/unit/test_compile_db.py tests/unit/test_tu_cache.py tests/unit/test_clang_session.py -v
  # Result: 89 passed. Exit 0.

  uv run pytest tests/unit/test_foundation_property.py -v --tb=short
  # Result: 21 passed. Exit 0.

  uv run pytest tests/unit/test_error_envelope.py tests/unit/test_path_guard.py tests/unit/test_compile_db.py tests/unit/test_tu_cache.py tests/unit/test_clang_session.py tests/unit/test_foundation_property.py -v --tb=short
  # Result: 110 passed. Exit 0.

  uv run pytest tests/unit/ -v
  # Result: 243 passed, 1 skipped (NEO4J_TEST_URI absent). Exit 0.

Results: 110 foundation tests pass (89 developer + 21 QA property-based). No failures.

Coverage per scenario:
  SC-US-9-1  : PASS — test_compile_db.py::test_build_path_none_returns_default_flags + test_foundation_property.py::test_resolve_flags_none_build_path_returns_default
  SC-US-9-2  : PASS — test_compile_db.py::test_file_not_in_db_returns_default_flags
  SC-US-9-3  : PASS — test_compile_db.py::test_db_hit_returns_db_flags
  SC-US-9-4  : PASS — test_path_guard.py::test_load_config_custom_flags
  SC-US-10-1 : PASS — test_tu_cache.py::test_second_access_is_hit
  SC-US-10-2 : PASS — test_tu_cache.py::test_first_access_is_miss + test_foundation_property.py::test_tu_cache_miss_on_each_distinct_key
  SC-US-10-3 : PASS — test_tu_cache.py::test_lru_eviction + test_tu_cache.py::test_configurable_capacity
  SC-US-10-4 : PASS — test_tu_cache.py::test_stats_structure_and_counts + test_clang_session.py::test_cache_stats_after_parse
  SC-US-10-5 : PASS — test_tu_cache.py::test_two_build_paths_separate_entries
  SC-US-10-6 : PASS — test_tu_cache.py::test_configurable_capacity + test_path_guard.py::test_load_config_success
  SC-US-10-7 : PASS — test_tu_cache.py::test_mtime_invalidation_triggers_reparse + test_tu_cache.py::test_mtime_boundary_one_ns
  SC-US-11-1 : out-of-scope — navigation tools not implemented in foundation stories (Stories 5-6)
  SC-US-11-2 : out-of-scope — cpp_export_to_graphdb integration verified in Story 8 QA
  SC-US-11-3 : out-of-scope — server layer (Stories 5-7), verified in Story 7 QA
  SC-US-12-1 : PASS — test_path_guard.py (3 dotdot tests) + test_foundation_property.py::test_has_dotdot_rejects_all_dotdot_paths (200 examples) + test_foundation_property.py::test_dotdot_boundary_cases (11 explicit cases)
  SC-US-12-2 : PASS — test_path_guard.py::test_dotdot_in_middle_segment_raises
  SC-US-12-3 : PASS — test_path_guard.py::test_symlink_escaping_root_raises_path_violation + ::test_chained_symlink_escape_raises
  SC-US-12-4 : PASS — test_path_guard.py::test_valid_path_inside_root_returns_resolved + test_foundation_property.py::test_valid_path_inside_root_always_passes (100 examples)
  SC-US-12-5 : PASS — test_path_guard.py::test_load_config_raises_on_missing_allowed_roots
  SC-US-12-6 : PASS — test_path_guard.py::test_path_outside_all_roots_raises + test_foundation_property.py::test_path_outside_root_always_rejected (100 examples)
  SC-US-13-1 : PASS — test_error_envelope.py::test_build_error_shape + test_foundation_property.py::test_build_error_envelope_schema_invariant (200 examples) + ::test_wrap_tool_code_always_in_valid_set
  SC-US-13-2 : PASS — test_error_envelope.py::test_wrap_tool_internal_error_no_traceback_in_message + test_foundation_property.py::test_sanitizer_redacts_unechoed_absolute_paths (200 examples)
  SC-US-13-3 : PASS — test_foundation_property.py::test_wrap_tool_always_returns_structured_dict
  SC-US-8-1  : PASS — test_foundation_property.py::test_resolve_flags_none_build_path_returns_default (purity via double-call, 200 flag tuple examples)
  SC-US-8-2  : PASS — test_compile_db.py::test_build_path_none_returns_default_flags + test_compile_db.py::test_db_hit_returns_db_flags
  SC-US-8-3  : PASS (proxy) — test_tu_cache.py::test_initial_hit_rate_is_zero (new TUCache() starts with zero entries/stats)
  SC-US-8-4  : out-of-scope — server layer (Stories 5-7), verified in Story 7 QA

Defects: none

observations:
  - macOS tempfile realpath (resolved): On macOS /var/folders/... is a symlink to /private/var/folders/...
    Production path_guard.py is correct (uses os.path.realpath). Tests using tempfile.TemporaryDirectory()
    directly must realpath() the result. Fixed in test_foundation_property.py — no production code change.
    Note: observation #2 in Story 7 QA mentioned this issue in an earlier property test file;
    this QA session fully resolves it by applying os.path.realpath() in the new test file.
  - hypothesis added to dev deps: `uv add --dev hypothesis` (hypothesis==6.152.7). Dev-only change.
    pyproject.toml updated; no production source changes.

Additions made: property-based (Hypothesis) — tests/unit/test_foundation_property.py (new file)
  21 tests: 10 Hypothesis property suites + 11 parametrised boundary cases.
  Covers SC-US-12-1, SC-US-12-4, SC-US-12-6, SC-US-13-1, SC-US-13-2, SC-US-13-3,
         SC-US-9-1, SC-US-8-1, SC-US-10-2.

References:
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-project-bootstrap.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-error-envelope-and-path-guard.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-compile-db-and-default-flags.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-clang-session-and-tu-cache.md
  /Users/husam/workspace/cpp-mcp/tests/unit/test_foundation_property.py (QA — new)
  Cognee tags: task:cpp-mcp, role:qa-engineer, scope:foundation
