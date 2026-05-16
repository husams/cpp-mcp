run_id: cpp-mcp-1
story: mcp-server-transport (Story 7)
date: 2026-05-16
role: developer
model: claude-sonnet-4-6

## Skills loaded

- python-conventions (loaded — pyproject.toml present)
- cpp-conventions (considered; not loaded — no C++ edits in this story)

## Skills considered but not loaded

- cpp-conventions: No CMakeLists.txt or *.cpp edits; all work is Python.
- typescript-conventions: No TypeScript.
- claude-api: Considered briefly for MCP SDK context; used context7/direct inspection instead.
- implement-story: Considered; direct implementation done per dispatch instructions.
- simplify: Considered at end; no duplication found warranting refactor pass.

## Commands run

### Orientation
- find src tests -name "*.py" (survey existing files)
- Read CHARTER.md, plan.md (Story 7), design.md, adr-10.md, scenarios.md
- Read config.py, error_envelope.py, get_definition.py, get_references.py, get_type_info.py,
  get_ast.py, get_header_info.py, get_preprocessor_state.py, tu_cache.py, clang_session.py
- Read tests/bdd/conftest.py, pyproject.toml
- uv run python -c "import mcp; ..." (inspect MCP SDK version=1.27.1 and API surface)
- inspect mcp.server.Server.list_tools, call_tool, run (read source)
- inspect mcp.client.stdio.stdio_client (read source)
- inspect mcp.types.Tool (read source)

### Implementation
- Called advisor() pre-implementation — received critical advice:
  1. wrap_tool async-awareness fix needed
  2. make_get_definition_tool asyncio.run_until_complete bug inside event loop
  3. __main__.py needed for python -m cpp_mcp

### Fix: wrap_tool async-awareness
- Edit error_envelope.py: add inspect.iscoroutinefunction branch with async wrapper
- uv run python test (manual inline test) — verified PATH_VIOLATION and FILE_NOT_FOUND caught

### New files written
- src/cpp_mcp/server/schemas.py
- src/cpp_mcp/server/app.py
- src/cpp_mcp/server/stdio_transport.py
- src/cpp_mcp/__main__.py
- 7 BDD feature files in tests/bdd/features/
- 7 BDD test files in tests/bdd/

### TUCache return type change
- Modified tu_cache.get_or_parse to return (TU, bool)
- Modified ClangSession._get_or_parse_sync and parse to propagate (tu, cache_hit)
- Updated all 6 tools to unpack (tu, cache_hit)
- Updated test_tu_cache.py (17 tests), test_clang_session.py (1 test)

## Gate results (Pass 1 — all clear)

- ruff format --check: PASS (46 files)
- ruff check: PASS
- mypy --strict src: PASS (22 source files)
- pytest -q tests/bdd -k "SC_US_8 or SC_US_9 or SC_US_10 or SC_US_11 or SC_US_12 or SC_US_13 or SC_US_14_1 or SC_US_14_3 or SC_US_14_4": 22 passed
- Full regression (tests/unit tests/bdd): 157 passed

## Deviations from plan.md

1. wrap_tool async fix — not in plan, but necessary to avoid silent exception swallowing in MCP handler dispatch context.
2. TUCache return type (TU, bool) — not in plan; needed to expose cache_hit per SC-US-10-1/-2.
3. 6 tools (no graphdb stub) — plan says "registers all 7 tools (graphdb placeholder if not yet wired)". Decision: do not add a stub that would need to be removed; Story 8 adds it cleanly.
4. _TOOL_SPECS exported for test introspection — pragmatic; avoids needing to invoke MCP SDK handler dispatch machinery in tests.

## Tool failures / retries

- asyncio.coroutine not available in Python 3.11 (removed in 3.11) — immediate fix on first attempt.
- type: ignore comment stacking for mypy — required 3 iterations to find the exact error code mypy needed (unused-ignore is strict about which codes are actually exercised).
- SIM117 nested-with in test_transport_stdio.py — fixed by combining to single `async with ... , ...` expression.
- Two BDD test failures on first run (list_tools awaitable issue) — fixed by using _TOOL_SPECS instead of server.list_tools().

## Open items

- HTTP transport (SC-US-14-2): deferred per plan.md §7b.
- Story 8 must add cpp_export_to_graphdb to _HANDLERS and _TOOL_SPECS in server/app.py.
