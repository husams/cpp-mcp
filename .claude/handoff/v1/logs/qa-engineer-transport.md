run_id: cpp-mcp-1
story: mcp-server-transport (Story 7)
date: 2026-05-16
role: qa-engineer
model: claude-sonnet-4-6

## Skills loaded

- python-conventions (loaded — pyproject.toml + uv.lock present)
- bdd-e2e-testing (loaded — writing new BDD step-def scenarios)
- cpp-conventions: not loaded (no C++ files touched)

## Orientation steps

- Read CHARTER.md, scenarios.md, plan.md (Story 7 section), developer-mcp-server-transport.md
- Surveyed src/ and tests/ directory trees
- Read: server/app.py, server/schemas.py, core/error_envelope.py, server/config.py
- Read: tests/bdd/test_transport_stdio.py, test_read_only.py, conftest.py
- Read: tests/bdd/features/transport_stdio.feature, read_only_enforcement.feature
- Called advisor() before writing (twice — once before implementation, once to validate gaps)
- Ran baseline: `uv run pytest -q tests/` → 258 passed (pre-existing)

## Gaps identified

1. transport_stdio.feature said "6 tools" but app.py had 7 (_TOOL_SPECS includes
   cpp_export_to_graphdb). No step for the 7th tool. Fixed.

2. No test asserting that tools/call over the real subprocess returns an error envelope
   (not a raw traceback). Developer's transport tests covered initialize and tools/list only.
   Fixed (SC_US_14_CALL_ENVELOPE scenario).

3. No unit-level parametrised schema validation for any of the 7 tool inputSchemas. Fixed.

4. All 7 domain exceptions were untested as a parametrised set. Fixed.

5. SC-US-11-1 required "each of" all 6 navigation tools to be tested for read-only
   enforcement, but test_read_only.py only exercised cpp_get_definition. Fixed with
   Scenario Outline SC_US_11_1_ALL_TOOLS covering all 6 tools.

6. test_foundation_property.py::test_valid_path_inside_root_always_passes intermittently
   fails on macOS (Hypothesis replays cached example where /var → /private/var breaks
   prefix check). Test-authoring defect. Filed as QD-TRANS-001.

## Files written / modified

### New
- /Users/husam/workspace/cpp-mcp/tests/unit/test_server_app.py
  63 parametrised tests covering: 7-tool count, per-tool schema shape, closed error-code set,
  all 7 domain exceptions → correct error code, INTERNAL_ERROR no-leak.

### Updated
- /Users/husam/workspace/cpp-mcp/tests/bdd/features/transport_stdio.feature
  Added: cpp_export_to_graphdb tool assertion to SC_US_14_3 (corrected "6" → "7").
  Added: SC_US_14_CALL_ENVELOPE scenario (tools/call error-envelope end-to-end).

- /Users/husam/workspace/cpp-mcp/tests/bdd/test_transport_stdio.py
  Added: assert_has_export_to_graphdb step.
  Added: client_call_tool_path_violation When step.
  Added: assert_call_result_is_envelope, assert_envelope_code_path_violation,
         assert_no_traceback_in_message, assert_envelope_has_request_id Then steps.

- /Users/husam/workspace/cpp-mcp/tests/bdd/features/read_only_enforcement.feature
  Added: SC_US_11_1_ALL_TOOLS Scenario Outline — 6 rows covering all navigation tools.

- /Users/husam/workspace/cpp-mcp/tests/bdd/test_read_only.py
  Added: call_any_nav_tool parametrised When step (parsers.parse("{tool_name} is called...")).
  Added: 6 async tool-dispatch shim helpers (_run_get_definition, _run_get_references,
         _run_get_type_info, _run_get_ast, _run_get_header_info, _run_get_preprocessor_state).
  Updated: module docstring to document QA additions.
  Updated: imports to include parsers from pytest_bdd.

## Commands run

```
uv run pytest -q tests/                                          # baseline 258 passed
uv run pytest tests/unit/test_server_app.py -v                  # 63 passed
uv run pytest tests/bdd/test_transport_stdio.py -v              # 4 passed
uv run ruff format tests/unit/test_server_app.py tests/bdd/test_transport_stdio.py
uv run ruff check --fix tests/unit/test_server_app.py
uv run ruff check tests/unit/test_server_app.py tests/bdd/test_transport_stdio.py   # clean
uv run pytest -q tests/                                          # 321 passed, 1 skipped
uv run pytest tests/bdd/test_read_only.py -v                    # 8 passed (6 new rows)
uv run ruff format tests/bdd/test_read_only.py                  # reformatted
uv run ruff check tests/bdd/test_read_only.py                   # clean
uv run pytest -q tests/                                          # final: 327 passed, 1 skipped
```

## Gate results

- ruff format: PASS (auto-formatted, then clean)
- ruff check: PASS (all clean)
- pytest final: 327 passed, 1 skipped, 2 advisory warnings (unregistered markers)

## Defects

QD-TRANS-001:
  scenario-id: SC-US-12-4
  failing-command: uv run pytest tests/unit/test_foundation_property.py::test_valid_path_inside_root_always_passes
  exit-code: 1
  description: macOS /var/folders → /private/var/folders symlink causes allowed-root prefix
               check to fail when Hypothesis replays cached example. Fix: use os.path.realpath()
               on allowed_root in the test fixture. Production code is correct.
  status: open — routes to developer for test fix

## Observations (advisory)

- PytestUnknownMarkWarning for @SC_US_14_CALL_ENVELOPE and @SC_US_11_1_ALL_TOOLS.
  Register both in [tool.pytest.ini_options] markers in pyproject.toml.

## Closing protocol

Wrote: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/qa-engineer-transport.md
Wrote: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/test-report.md (updated)
Cognee ingest: run command below after file write.
