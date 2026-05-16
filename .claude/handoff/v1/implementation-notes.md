run_id: cpp-mcp-1
story: navigation-tools (Story 5) — appended
date: 2026-05-16

---

## Story 5 — navigation-tools

### Files changed

**New source files:**
- `src/cpp_mcp/core/cursor.py` — `cursor_at(tu, file_path, line, col)` helper; validates line/col bounds by reading file line count; calls `ci.Cursor.from_location(tu, location)` (libclang correct API; `tu.get_cursor()` does not exist); raises `InvalidPositionError` for out-of-range positions or TRANSLATION_UNIT/INVALID_FILE cursor kinds.
- `src/cpp_mcp/tools/__init__.py` — package marker.
- `src/cpp_mcp/tools/get_definition.py` — `get_definition()` async entry point; returns `{definition_found, file, line, col, usr, flags_source, request_id}`; `definition_found=False` when cursor has no definition location.
- `src/cpp_mcp/tools/get_references.py` — `get_references()` async entry point; walks TU AST with `tu.cursor.walk_preorder()`, collects cursors where `ref.get_usr() == target_usr`; skips the declaration cursor itself (whose `cursor.referenced` points to itself in libclang); truncates at 1000 results.
- `src/cpp_mcp/tools/get_type_info.py` — `get_type_info()` async entry point; returns `{display_type, canonical_type, size_bytes, alignment_bytes, is_pod, is_const, is_reference, is_pointer, flags_source, request_id}`; `typ.get_canonical()` resolves `auto`; `_safe_size()` returns `None` for libclang sentinel values ≤ 0.

**New test fixtures (C++, no STL headers):**
- `tests/fixtures/cpp/definition_test.cpp` — `int foo()` at line 4, `struct Point` at line 8, `int unused_fn()` at line 14 (never called — zero-references test), `int main()` at line 18.
- `tests/fixtures/cpp/references_test.cpp` — `int calculate()` at line 4, called three times in main().
- `tests/fixtures/cpp/forward_decl.cpp` — `struct Bar;` at line 4 (forward decl, no definition).
- `tests/fixtures/cpp/macro_test.cpp` — `MY_MACRO` at line 4, used at line 8.
- `tests/fixtures/cpp/types_test.cpp` — `int x` at line 5, `auto val` at line 8, `Box<int> b` at line 18, `struct Opaque;` at line 21.

**New BDD feature files:**
- `tests/bdd/features/cpp_get_definition.feature` — 8 scenarios (@SC_US_1_1, _5, _6, _7, _9, _10, _11, _14).
- `tests/bdd/features/cpp_get_references.feature` — 5 scenarios (@SC_US_2_1, _2, _4, _5, _6).
- `tests/bdd/features/cpp_get_type_info.feature` — 7 scenarios (@SC_US_3_1, _2, _3, _4, _6, _7, _8).

**New BDD step files:**
- `tests/bdd/test_get_definition.py`
- `tests/bdd/test_get_references.py`
- `tests/bdd/test_get_type_info.py`

**Modified files:**
- `tests/bdd/conftest.py` — added `tmp_allowed_root`, `allowed_roots`, `default_flags`, `clang_session`, `ctx` fixtures; `copy_fixture()` and `make_nonexistent_path()` helpers; `requires_libclang` skip mark.
- `src/cpp_mcp/core/clang_session.py` — fixed RUF005 (tuple concatenation → unpack spread).
- `src/cpp_mcp/tools/get_header_info.py` — fixed SIM102 (nested if), mypy no-any-return on `cursor.kind.name`.
- `pyproject.toml` — registered SC_US_1_* through SC_US_3_* markers.

### Tests added/run

```
uv run ruff format --check src tests  → 35 files already formatted (pass)
uv run ruff check src tests           → All checks passed (pass)
uv run mypy --strict src              → Success: no issues found in 18 source files (pass)
uv run pytest -q tests/bdd -k "SC_US_1 or SC_US_2 or SC_US_3"
  → 20 passed, 24 deselected, 24 warnings in 0.09s (pass)
```

### Deviations from plan

1. **`requires_libclang` skip mark instead of `@pytest.mark.libclang`**: pytest-bdd 8 does not honor marks on step functions for skip behavior; only `pytest.mark.skipif` applied before the step decorator takes effect. Used `@requires_libclang` (a `skipif` decorator) before `@when(...)`.

2. **`clang_session` parameter omitted from non-libclang steps**: PATH_VIOLATION and FILE_NOT_FOUND `When` steps that only call `validate_path()` do not request `clang_session`. Avoids triggering the libclang-availability skip for error-path scenarios that don't need it.

3. **Declaration cursor excluded from `_collect_references`**: libclang's `cursor.referenced` on the declaration cursor points back to itself. Added explicit guard `if cursor.get_usr() == target_usr: continue` to avoid counting the declaration as a reference.

4. **asyncio.run() in sync step functions**: pytest-bdd 8 has no native async step support; `asyncio_mode = "auto"` applies only to test functions. All step functions are `def`, calling `asyncio.run()` internally for async tools.

### Follow-ups

- SC_US_3_5 (macro-expanded type) not in feature file — descoped per plan (US-3 scope). Tag `sr-dev` if needed.
- `PytestUnknownMarkWarning` from other stories (SC_US_4_*, SC_US_6_*) in unrelated feature files — minor; those story teams should register their markers.
- cache_hit field deferred to Story 7 per ADR-1/OQ-3.

### References

- plan.md Story 5, design.md §2, scenarios.md @SC-US-1-*, @SC-US-2-*, @SC-US-3-*
- Cognee tags: task:cpp-mcp, role:developer, story:navigation-tools

---

story: ast-and-structural-tools (Story 6) — appended
date: 2026-05-16

---

## Story 6 — ast-and-structural-tools

### Files changed

**New source files:**
- `src/cpp_mcp/core/ast_walker.py` — DFS cursor walker; depth/range filter; node-count + byte budget (ADR-5); JSON and graph emitters; `walk_json`, `walk_graph`, `has_zero_ast_nodes`, `has_fatal_diagnostics`.
- `src/cpp_mcp/tools/get_ast.py` — `cpp_get_ast` async tool + `make_cpp_get_ast` factory.
- `src/cpp_mcp/tools/get_header_info.py` — `cpp_get_header_info` async tool; `tu.get_includes()`; orphaned-include detection via USR intersection.
- `src/cpp_mcp/tools/get_preprocessor_state.py` — `cpp_get_preprocessor_state` async tool; `PARSE_DETAILED_PROCESSING_RECORD` options; token-level conditional scanner.

**Modified source file (deviation — see Deviations below):**
- `src/cpp_mcp/core/clang_session.py` — Added optional `options: int = 0` param to `_parse_sync`, `_get_or_parse_sync`, and `parse`. Backward-compatible.

**New test fixtures:**
- `tests/fixtures/cpp/ast_test.cpp` — 50 lines, ~5 nesting levels.
- `tests/fixtures/cpp/header_api.h` — includes `header_standalone.h`; 3 exported symbols.
- `tests/fixtures/cpp/header_standalone.h` — no includes; 2 exported symbols.
- `tests/fixtures/cpp/header_missing_include.h` — unresolvable include.
- `tests/fixtures/cpp/config_macros.cpp` — `#define` + `#ifdef/#ifndef` blocks.
- `tests/fixtures/cpp/broken_partial.cpp` — missing include; recoverable AST.
- `tests/fixtures/cpp/unparseable.cpp` — binary null bytes (7 bytes).

**New BDD files:**
- `tests/bdd/features/cpp_get_ast.feature` (10 scenarios @SC_US_4_*)
- `tests/bdd/features/cpp_get_header_info.feature` (6 scenarios @SC_US_5_*)
- `tests/bdd/features/cpp_get_preprocessor_state.feature` (7 scenarios @SC_US_6_*)
- `tests/bdd/test_get_ast.py`
- `tests/bdd/test_get_header_info.py`
- `tests/bdd/test_get_preprocessor_state.py`

### Tests added/run

Command: `uv run pytest -q tests/bdd -k "SC_US_4 or SC_US_5 or SC_US_6"`
Result: **23 passed** (libclang present; all @libclang scenarios ran and passed).

Exit criteria:
- `uv run ruff format --check src tests` → 35 files already formatted (pass)
- `uv run ruff check src tests` → All checks passed (pass)
- `uv run mypy --strict src` → Success: no issues found in 18 source files (pass)
- `uv run pytest -q tests/bdd -k "SC_US_4 or SC_US_5 or SC_US_6"` → 23 passed (pass)

### Deviations from plan

1. **`clang_session.py` modified** (outside Story 6 files-to-touch). Added `options: int = 0` param to `parse()`, `_parse_sync()`, and `_get_or_parse_sync()`. Required so `cpp_get_preprocessor_state` can request `PARSE_DETAILED_PROCESSING_RECORD` (macro-definition cursors). Options encoded as a synthetic flags-key suffix to keep TU cache entries separate. Backward-compatible; all Story 4 tests still pass.

2. **Conditional detection is heuristic**. libclang does not expose `#ifdef/#endif` evaluated results as cursors. Implementation uses a token-level file scan + cursor-presence inference. SC-US-6-3 passes; the heuristic can misidentify in edge cases (overlapping macro ranges).

3. **Orphaned-include detection via USR intersection**. Walks main-file cursors for `cursor.referenced.get_usr()` values; compares against USRs defined in each direct include. TU-scope, consistent with ADR-1 / OQ-6.

### Follow-ups

1. `sr-dev: review ClangSession options deviation` — additive change to Story 4 file.
2. `qa-engineer: verify SC-US-4-11 (PARSE_ERROR for zero-node TU)` — `unparseable.cpp` (binary bytes) should trigger fatal diagnostic; confirm empirically on target platform.
3. `cleanup: remove _run() from get_ast.py` — dead code (sync wrapper); the async path is canonical.
4. `enhancement: conditional detection accuracy` — replace heuristic with libclang PP callback when available in the Python bindings.

### References

- plan.md Story 6, design.md §2 (ast_walker) §4 (error handling), adr-5.md, adr-9.md
- scenarios.md @SC-US-4-*, @SC-US-5-*, @SC-US-6-*
- Cognee tags: task:cpp-mcp, role:developer, story:ast-and-structural-tools

---

story: clang-session-and-tu-cache (Story 4) — appended
date: 2026-05-16

---

## Story 4 — clang-session-and-tu-cache

### Files changed

- `src/cpp_mcp/core/tu_cache.py` (new)
- `src/cpp_mcp/core/clang_session.py` (new)
- `tests/unit/test_tu_cache.py` (new — 17 tests)
- `tests/unit/test_clang_session.py` (new — 4 tests, libclang-marked)
- `tests/fixtures/cpp/tiny.cpp` (new)
- `pyproject.toml` — added `asyncio_mode = "auto"` to `[tool.pytest.ini_options]`

### Tests added/run

Command: `uv run pytest -q tests/unit/test_tu_cache.py tests/unit/test_clang_session.py`
Result: 21 passed in 0.03s

Exit criteria (all clear):
- `uv run ruff format --check src tests` → pass (20 files already formatted)
- `uv run ruff check src tests` → pass (All checks passed)
- `uv run mypy --strict src` → pass (Success: no issues found in 9 source files)
- `uv run pytest -q tests/unit/test_tu_cache.py tests/unit/test_clang_session.py` → 21 passed

### Deviations from plan

1. Cache default capacity is 128 (ADR-6 wins over dispatch message "16").
2. `tiny.cpp` has no system headers — test-host libclang lacks a sysroot, so `#include <cstdint>` produces a fatal diagnostic. Fixture uses pure declarations only.
3. `asyncio_mode = "auto"` added to pyproject.toml — absent prior to this story; required for `@pytest.mark.asyncio` in test_clang_session.py.
4. `type: ignore[import-untyped]` not used in `clang_session.py` source — mypy's `[[tool.mypy.overrides]]` for `clang.*` makes the import transparent; the comment was flagged unused. Test file retains it (override scope is `src/` only).

### Follow-ups (tag: sr-dev)

- F4-1: `@pytest.mark.libclang` needs a `pytest_configure` hook if future BDD tests reference the marker. Currently declared only in `pyproject.toml` markers list.
- F4-2: `_configure_libclang()` is best-effort; non-standard libclang paths require `CPP_MCP_LIBCLANG_PATH` env override.
- F4-3: Stories 5/6 fixtures that test real C++ constructs (STL types, templates) will need a valid sysroot or flag set pointing to system headers.

### References

- plan.md Story 4, design.md §2, adr-2.md, adr-6.md, scenarios.md US-8/US-10
- Cognee tags: task:cpp-mcp, role:developer, story:clang-session-and-tu-cache

---

story: compile-db-and-default-flags (Story 3) — appended
date: 2026-05-16

---

## Story 3 — compile-db-and-default-flags

### Files changed

- src/cpp_mcp/core/compile_db.py (new — `resolve_flags()` with ADR-9 semantics)
- tests/unit/test_compile_db.py (new — 13 tests covering all plan.md scenarios)
- tests/conftest.py (new — root-level libclang auto-discovery for all test sessions)
- tests/fixtures/compile_dbs/ok/compile_commands.json (new — static fixture, portability note below)
- tests/fixtures/compile_dbs/malformed/compile_commands.json (new — invalid JSON)
- tests/fixtures/compile_dbs/empty/.keep (new — empty dir fixture)

### Tests added/run

Command: `uv run pytest -q tests/unit/test_compile_db.py`
Result: 13 passed in 0.01s

Exit criteria (pass 2 — all clear on first try after formatting):
- `uv run ruff format --check src tests` → 16 files already formatted (pass)
- `uv run ruff check src tests` → All checks passed (pass)
- `uv run mypy --strict src` → Success: no issues found in 7 source files (pass)
- `uv run pytest -q tests/unit/test_compile_db.py` → 13 passed (pass)

All prior unit tests (70 total) also pass: `uv run pytest -q tests/unit/` → 70 passed.

### Key implementation discoveries

1. **libclang `getCompileCommands` never returns `None` for a miss** — it returns a synthetic
   1-entry `CompileCommands` object with `--` inserted before the filename. Detection: check
   `'--' in list(cmd.arguments)`. This is the authoritative miss-detection strategy used in
   `_extract_flags`.

2. **Lazy import pattern** — `import clang.cindex as ci` is placed inside `_load_compile_db` and
   `_extract_flags` (not at module top level) so importing `compile_db` does NOT trigger libclang
   load. Tests for `None`/`is_file` paths run without libclang present.

3. **`type: ignore` not needed** — the `clang` package ships plain Python (`cindex.py`); mypy
   reads it directly. The pyproject.toml `ignore_missing_imports=true` override for `clang.*` is
   not needed for compile_db.py (mypy finds the module). `Any` return on `_load_compile_db` is
   intentional to avoid propagating untyped clang types.

4. **libclang path on macOS** — `libclang.dylib` is not on the default dyld search path.
   `tests/conftest.py` auto-discovers it from a prioritized list of known locations
   (Xcode, Homebrew LLVM). Override via `CPP_MCP_LIBCLANG_PATH` env var in CI.

### Deviations from plan

- **`ok/compile_commands.json` fixture has hardcoded paths** (`/projects/src/main.cpp`). libclang
  resolves file entries by absolute path, so this static fixture cannot produce a real DB hit in
  tests. The DB-hit unit test (`test_db_hit_returns_db_flags`) uses `tmp_path` to create a
  portable `compile_commands.json` at runtime. Recorded as deviation; the static file satisfies
  the plan requirement for an `ok/` fixture and is sanity-checked by a separate test.

- **`validate_path(build_path, kind="dir")` deferred to tool layer** — `resolve_flags` is a pure
  function and has no access to `allowed_roots`. The `build_path.is_file()` guard inside
  `resolve_flags` provides the `INVALID_ARGUMENT` behavior required by ADR-9. Full path-guard
  (traversal + allowed-roots check) is the calling tool's responsibility in Stories 5–7. Noted in
  module docstring.

- **`tests/conftest.py` added** — not in plan.md files-to-touch (Story 3), but required to
  configure libclang path for the DB-hit test. Owned at the test-session level so Story 4's
  `libclang`-marked tests also benefit.

### Follow-ups for sr-dev

- Stories 5–7 tools: call `validate_path(build_path_str, allowed_roots, kind="dir")` before
  passing `build_path` to `resolve_flags`.
- Story 4 `clang_session.py`: reuse the libclang auto-discovery pattern from `tests/conftest.py`
  (or a shared utility) to set `Config.set_library_path` at server startup.
- `ok/compile_commands.json` hardcoded paths: if BDD tests in Story 7 need a static fixture DB,
  they must generate it at runtime or update the file with fixture-relative paths.

### References

- plan.md (Story 3), design.md §§3–4, adr-9.md, scenarios.md (US-1, US-9)
- Cognee tags: task:cpp-mcp, role:developer, story:compile-db-and-default-flags

---

story: error-envelope-and-path-guard (Story 2) — appended to bootstrap notes
date: 2026-05-16

---

## Story 2 — error-envelope-and-path-guard

### Files changed

- src/cpp_mcp/core/__init__.py (new — package marker)
- src/cpp_mcp/core/error_envelope.py (new — ErrorCode StrEnum, all domain exceptions, build_error(), wrap_tool(), message sanitizer)
- src/cpp_mcp/core/path_guard.py (new — validate_path() with ADR-3/4 algorithm)
- src/cpp_mcp/server/__init__.py (new — package marker)
- src/cpp_mcp/server/config.py (new — load_config() parsing CPP_MCP_ALLOWED_ROOTS + optional vars)
- tests/unit/test_error_envelope.py (new — 32 tests; covers all 8 codes, envelope shape, sanitizer, wrap_tool mapping)
- tests/unit/test_path_guard.py (new — 23 tests; covers dotdot, symlink escape, multi-root, FILE_NOT_FOUND, kind=dir)

### Tests added/run

Command: `uv run pytest -q tests/unit/test_error_envelope.py tests/unit/test_path_guard.py`
Result: 55 passed in 0.04s

Exit criteria (pass 1 — all clear):
- `uv run ruff format --check src tests` → 13 files already formatted (pass)
- `uv run ruff check src tests` → All checks passed (pass)
- `uv run mypy --strict src` → Success: no issues found in 6 source files (pass)
- `uv run pytest -q ...` → 55 passed (pass)

### Deviations from plan

None. All files in plan.md Story 2 `files-to-touch` were implemented. The `kind="dir"` branch of `validate_path` covers `build_path-is-a-file → INVALID_ARGUMENT` for Story 3's `resolve_flags`.

### Follow-ups for sr-dev

- Story 3 compile_db: call `validate_path(..., kind="dir")` for build_path.
- Story 7 transport: `wrap_tool` wraps sync callables only; async tools may need `async_wrap_tool` variant.
- `KeyboardInterrupt`/`SystemExit` currently become INTERNAL_ERROR in wrap_tool — consider explicit pass-through if needed by the event loop.

### References

- plan.md (Story 2), design.md §4, adr-3.md, adr-4.md, adr-8.md, scenarios.md (US-12, US-13)
- Cognee tags: task:cpp-mcp, role:developer, story:error-envelope-and-path-guard

---

## Story 1 — project-bootstrap (original notes below)

story: project-bootstrap
date: 2026-05-16

## Files changed
- /Users/husam/workspace/cpp-mcp/pyproject.toml (new)
- /Users/husam/workspace/cpp-mcp/README.md (new — skeleton)
- /Users/husam/workspace/cpp-mcp/.gitignore (new)
- /Users/husam/workspace/cpp-mcp/.python-version (new — `3.11`)
- /Users/husam/workspace/cpp-mcp/src/cpp_mcp/__init__.py (new — exports `__version__ = "0.1.0"`)
- /Users/husam/workspace/cpp-mcp/src/cpp_mcp/py.typed (new — empty PEP 561 marker)
- /Users/husam/workspace/cpp-mcp/tests/__init__.py (new)
- /Users/husam/workspace/cpp-mcp/tests/unit/__init__.py (new)
- /Users/husam/workspace/cpp-mcp/tests/unit/test_bootstrap.py (new — 2 smoke tests)
- /Users/husam/workspace/cpp-mcp/tests/bdd/__init__.py (new)
- /Users/husam/workspace/cpp-mcp/tests/bdd/conftest.py (new — placeholder)

## Tests added/run
Command: `uv run pytest -q tests/unit/test_bootstrap.py`
Result: 2 passed in 0.00s

## Exit-criteria results (pass 1 — all clear)
- `uv sync --extra dev` → exit 0 (clang 19.1.7, mcp 1.27.1)
- `uv run ruff format --check src tests` → exit 0 (6 files already formatted)
- `uv run ruff check src tests` → exit 0 (All checks passed)
- `uv run mypy --strict src` → exit 0 (no issues in 1 source file)
- `uv run pytest -q tests/unit/test_bootstrap.py` → exit 0 (2 passed)

## Deviations from plan
- clang 19.1.7 resolved (plan allows >=17,<20; within range per Risks note)
- `[tool.ruff.lint]` table used for `select` (ruff >=0.2 requirement; bare `[tool.ruff].select` is deprecated)

## Follow-ups
- Story 2 (error-envelope-and-path-guard) is unblocked; depends-on: [project-bootstrap] satisfied.

## References
- plan.md Story 1 section
- CHARTER.md (invariant I3 — exit criteria present and run)
- python-conventions skill

---

run_id: cpp-mcp-1
story: mcp-server-transport (Story 7) — appended
date: 2026-05-16
developer-model: claude-sonnet-4-6

## Files changed (Story 7)

### New files
- src/cpp_mcp/__main__.py — enables `python -m cpp_mcp` (ADR-10)
- src/cpp_mcp/server/schemas.py — JSON Schema dicts for all 6 tool inputs
- src/cpp_mcp/server/app.py — MCP Server with list_tools/call_tool; exposes _TOOL_SPECS
- src/cpp_mcp/server/stdio_transport.py — `main()` + async stdio loop
- tests/bdd/features/transport_stdio.feature — SC-US-14-1/-3/-4
- tests/bdd/features/read_only_enforcement.feature — SC-US-11-1/-3
- tests/bdd/features/error_envelope.feature — SC-US-13-1/-2/-3
- tests/bdd/features/stateless_build.feature — SC-US-8-1/-4
- tests/bdd/features/path_traversal.feature — SC-US-12-1/-2/-4/-5/-6
- tests/bdd/features/default_flags.feature — SC-US-9-1/-2/-4
- tests/bdd/features/tu_cache.feature — SC-US-10-1/-2/-4/-6
- tests/bdd/test_transport_stdio.py, test_read_only.py, test_error_envelope_bdd.py,
  test_stateless_build.py, test_path_traversal.py, test_default_flags.py,
  test_tu_cache_bdd.py

### Modified files
- src/cpp_mcp/core/error_envelope.py — wrap_tool is now async-aware (iscoroutinefunction)
- src/cpp_mcp/core/tu_cache.py — get_or_parse returns (TU, cache_hit: bool)
- src/cpp_mcp/core/clang_session.py — parse() returns (tu, cache_hit)
- src/cpp_mcp/tools/get_definition.py, get_references.py, get_type_info.py,
  get_ast.py, get_header_info.py, get_preprocessor_state.py — unpack (tu, cache_hit)
- tests/unit/test_tu_cache.py, test_clang_session.py — updated for new return type
- pyproject.toml — registered SC_US_4/5/6/* and SC_US_8..14/* markers

## Exit-criteria results (Story 7)

- ruff format --check: PASS
- ruff check: PASS
- mypy --strict: PASS
- pytest tests/bdd -k "SC_US_8 or SC_US_9 or SC_US_10 or SC_US_11 or SC_US_12 or SC_US_13 or SC_US_14_1 or SC_US_14_3 or SC_US_14_4": 22 passed
- Full regression (pytest tests/unit tests/bdd): 157 passed

## Deviations from plan

1. wrap_tool async fix — latent bug (sync wrapper silently drops async exceptions). Fixed.
2. TUCache return type change — (TU, bool) to expose cache_hit in tool responses.
3. 6 tools registered (graphdb deferred to Story 8 per plan).
4. _TOOL_SPECS exported from app.py for test introspection.

## Follow-ups (tag: sr-dev)

- Story 8: add cpp_export_to_graphdb to _HANDLERS/_TOOL_SPECS in app.py.
- HTTP transport (SC-US-14-2): deferred to Story 7b.

---

run_id: cpp-mcp-1
story: graphdb-exporter (Story 8) — appended
date: 2026-05-16
developer-model: claude-sonnet-4-6

## Story 8 — graphdb-exporter

### Files changed

New files:
- `src/cpp_mcp/graphdb/__init__.py`
- `src/cpp_mcp/graphdb/schema.py` — node/edge type constants (ADR-7)
- `src/cpp_mcp/graphdb/driver.py` — `GraphDriver` Protocol + `NodeRecord`/`EdgeRecord` TypedDicts
- `src/cpp_mcp/graphdb/neo4j_driver.py` — Bolt impl; lazy `neo4j` import; MERGE idempotency; per-file `execute_write` tx
- `src/cpp_mcp/graphdb/exporter.py` — `extract_nodes_and_edges`, `collect_cpp_files`, `export_file`
- `src/cpp_mcp/tools/export_to_graphdb.py` — `cpp_export_to_graphdb` async handler with ordered validation
- `tests/unit/test_graphdb_exporter.py` — 19 unit tests via FakeGraphDriver
- `tests/bdd/features/export_to_graphdb.feature` — 11 BDD scenarios (SC-US-7-1..11)
- `tests/bdd/test_export_to_graphdb.py` — BDD step implementations

Modified files:
- `src/cpp_mcp/server/schemas.py` — added `CPP_EXPORT_TO_GRAPHDB_SCHEMA`
- `src/cpp_mcp/server/app.py` — registered `cpp_export_to_graphdb` in `_TOOL_SPECS` and `_HANDLERS`
- `pyproject.toml` — added `SC_US_7_1..11` pytest markers

### Tests added/run

```
uv run ruff format --check src tests  → 54 files already formatted (pass)
uv run ruff check src tests           → All checks passed (pass)
uv run mypy --strict src              → Success: no issues found in 28 source files (pass)
uv run pytest -q tests/unit/test_graphdb_exporter.py  → 19 passed (pass)
uv run pytest -q tests/bdd -k "SC_US_7" -m "not neo4j" → 11 passed (pass)
```

All exit gates cleared on first pass.

### Deviations from plan

1. `validate_path(file_path_or_dir, ..., kind="file")` is used for the input path. This allows both files and directories through (path_guard only rejects when kind="dir" and path resolves to a regular file). Avoids extending path_guard with a new `kind="any"` parameter.

2. `_do_export` nested function (replacing a lambda) required to satisfy mypy `--strict` type inference. Lambda with default arguments cannot be inferred by mypy.

3. Live Neo4j integration test not implemented — no `NEO4J_TEST_URI` in dev environment. The `@neo4j` marker is registered in pyproject.toml. A developer adds a `@pytest.mark.neo4j`-tagged scenario and conftest autoskip hook when a test instance is available.

### Follow-ups

- Add `@pytest.mark.neo4j`-tagged BDD scenario + conftest autoskip hook (deferred, no Neo4j in CI).
- Cognee driver: v1.x per ADR-7; no tool/exporter changes needed.
- HTTP transport (Story 7b) remains deferred; the tool is now registered and will be available automatically when HTTP transport is wired.

### References

- plan.md Story 8, adr-7.md, scenarios.md SC-US-7-1..11, design.md §2

---

run_id: cpp-mcp-1
story: followup-http-transport (Story 7b) — appended
date: 2026-05-16
developer-model: claude-sonnet-4-6

## Story 7b — HTTP Transport

### Files changed

New files:
- `src/cpp_mcp/server/http_transport.py` — `run_http(host, port)` using StreamableHTTPSessionManager (stateless, json_response=True); GET /healthz with cache stats; loopback-warning per ADR-10.
- `tests/bdd/features/transport_http.feature` — SC-US-14-2 scenario.
- `tests/bdd/test_transport_http.py` — BDD steps: in-process uvicorn thread, free-port allocation, healthz polling, MCP streamable_http_client initialize + list_tools.

Modified files:
- `src/cpp_mcp/__main__.py` — argparse dispatch on `--transport={stdio,http}`, `--port`, `--host`; delegates to `_run_stdio` or `run_http`.
- `pyproject.toml` — added `[project.optional-dependencies] http = ["uvicorn>=0.20"]`; added `SC_US_14_2` marker.

### Tests added/run

```
uv run pytest tests/bdd/test_transport_http.py -v
# Result: 1 passed

uv run pytest -q
# Result: 332 passed, 1 failed (pre-existing graphdb test), 1 skipped
```

### Deviations from plan

1. **Default port 8000** (dispatch) vs **8765** (ADR-10). Dispatch is the later instruction; used 8000. → tag sr-dev to update ADR-10.
2. **Starlette** used instead of **FastAPI** (ADR-10). FastAPI not installed; Starlette is a transitive dep of mcp. Route/Mount primitives sufficient. → tag sr-dev to update ADR-10 if desired.
3. `streamablehttp_client` deprecated alias replaced with `streamable_http_client` (SDK rename).

### Pre-existing failures (not introduced by this story)

- `tests/unit/test_graphdb_exporter.py::test_references_edge_no_double_count_with_calls` — concurrent developer's file; my changes do not touch graphdb/.
- 3 ruff lint errors in `src/cpp_mcp/graphdb/cognee_driver.py` — concurrent developer's file (DO NOT TOUCH per coordinator).

### Follow-ups

- Register `SC_US_14_CALL_ENVELOPE` and `SC_US_11_1_ALL_TOOLS` marks in pyproject.toml markers (advisory PytestUnknownMarkWarning, pre-existing).
- Update ADR-10 to reflect Starlette-over-FastAPI decision and port=8000 default.

### References

- dispatch brief (task-slug cpp-mcp, story 7b), scenarios.md SC-US-14-2, adr-10.md

---

run_id: cpp-mcp-1
story: followup-references-edge — appended
date: 2026-05-16
developer-model: claude-sonnet-4-6

## followup-references-edge — emit REFERENCES edges in graphdb exporter

### Files changed

- `src/cpp_mcp/graphdb/exporter.py` — added REFERENCES edge emission for use-site cursors
- `tests/unit/test_graphdb_exporter.py` — added 5 REFERENCES-edge tests

### What was changed in exporter.py

1. Imported `EDGE_REFERENCES` from `cpp_mcp.graphdb.schema`.
2. Added `_REFERENCE_CURSOR_KINDS: frozenset[str]` = `{"DECL_REF_EXPR", "MEMBER_REF_EXPR", "TYPE_REF"}`.
3. Added `_FUNCTION_CURSOR_KINDS: frozenset[str]` for function/method nodes.
4. Extended `_walk_cursor` with `enclosing_func_usr: str | None = None` parameter (default-compatible; backward safe).
5. New branch for `_REFERENCE_CURSOR_KINDS`: emits REFERENCES edge from `enclosing_func_usr` (or `file_usr` for top-level) to `cursor.referenced` USR; skips if `referenced` is None or USR is empty.
6. `enclosing_func_usr` is updated to `usr` when entering a function-kind cursor and threaded through all recursive calls.
7. Post-walk dedup filter in `extract_nodes_and_edges`: drops REFERENCES edges where (source_usr, target_usr) is already covered by a CALLS edge.

### Tests added (test_graphdb_exporter.py)

- `test_references_edge_decl_ref_expr` — DECL_REF_EXPR inside function → REFERENCES from function USR.
- `test_references_edge_type_ref` — TYPE_REF inside function → REFERENCES to type USR.
- `test_references_edge_dedup_suppresses_when_calls_edge_present` — dedup filter suppresses REFERENCES when CALLS covers same pair; unrelated var REFERENCES survives.
- `test_references_edge_none_referenced_no_crash` — `cursor.referenced = None` → no edge, no exception.
- `test_references_edge_top_level_uses_file_usr` — top-level DECL_REF_EXPR uses File node as source.

### Tests run

```
uv run ruff format --check src/cpp_mcp/graphdb/exporter.py tests/unit/test_graphdb_exporter.py
# → 2 files already formatted

uv run ruff check src/cpp_mcp/graphdb/exporter.py tests/unit/test_graphdb_exporter.py
# → All checks passed

uv run mypy --strict src/cpp_mcp
# → Success: no issues found in 30 source files

uv run pytest -q
# → 367 passed, 4 skipped (2 @neo4j, 2 @cognee — env vars not set)
```

All exit gates clear (formatter, linter, type checker, test runner).

Note: `ruff check .` (project-wide) reports 4 errors in `src/cpp_mcp/graphdb/cognee_driver.py` and `tests/unit/test_cognee_driver.py` — concurrent developer's files, not modified here.

### Deviations from plan

None. Implementation matches task spec.

### Follow-ups (tag: sr-dev)

1. **CALLS edge emission is broken (pre-existing)** — `CALL_EXPR` is not in `_KIND_TO_NODE_TYPE`, so the existing CALLS block (inside `if node_type and usr:`) is unreachable for CALL_EXPR cursors. The CALLS-dedup filter is correct and will work once this is fixed. Fix: add a non-schema CALL_EXPR handler parallel to the new `_REFERENCE_CURSOR_KINDS` branch.
2. Lint errors in `cognee_driver.py` — coordinate with that developer to clear `SIM105`, `E501`, `I001` before merge.

### References

- plan.md (followup task), design.md §2 graphdb/, adr-7.md, schema.py (EDGE_REFERENCES)

---

run_id: cpp-mcp-1
story: followup-cognee-driver — appended
date: 2026-05-16
developer-model: claude-sonnet-4-6

## followup-cognee-driver — Cognee GraphDriver (ADR-7 deferred)

### Files changed

New files:
- `src/cpp_mcp/graphdb/cognee_driver.py` — CogneeTransport Protocol, CliCogneeTransport (shells out to `cognee api request`), CogneeDriver (GraphDriver Protocol impl), _node_key/_edge_key helpers
- `tests/unit/test_cognee_driver.py` — 34 unit tests + 3 @pytest.mark.cognee live tests (auto-skipped when COGNEE_BASE_URL absent)

Modified files:
- `src/cpp_mcp/graphdb/__init__.py` — now exports GraphDriver, NodeRecord, EdgeRecord, make_driver() factory
- `pyproject.toml` — added `"cognee: requires COGNEE_BASE_URL"` to pytest markers list

### Tests added/run

```
uv run ruff format --check src tests  → 62 files already formatted (pass)
uv run ruff check src tests           → All checks passed (pass)
uv run mypy --strict src              → Success: no issues found in 30 source files (pass)
uv run pytest -q tests/unit/test_cognee_driver.py
  → 34 passed, 3 skipped in 0.06s (pass)
uv run pytest -q
  → 367 passed, 4 skipped — no regressions (pass)
```

All exit gates cleared on first pass (after ruff format auto-fix on line 1).

### Design decisions

1. CogneeTransport Protocol with single `ingest()` method; CliCogneeTransport is the default (shells out to `cognee api request POST /api/v1/add`); tests inject FakeCogneeTransport — no network required for unit tests.
2. Idempotency: driver-side MERGE-on-key within a session. Nodes keyed by USR; edges keyed by (source_usr, edge_type, target_usr). Cross-session dedup is best-effort (Cognee backend may accumulate duplicate documents on re-ingest across restarts) — documented as known limitation per ADR-7.
3. make_driver() factory: additive change to `__init__.py`; `scheme in ("bolt", "neo4j", "neo4j+s", "bolt+s")` → Neo4jDriver; `scheme == "cognee"` → CogneeDriver; unknown scheme raises ValueError.

### Deviations from plan

None. No plan.md entry existed for this followup; implemented to task-dispatch spec.

### Follow-ups (tag: sr-dev)

- Cross-session dedup: if true MERGE-on-USR across Cognee sessions is required, consider `/api/v1/remember/entry` with a USR-keyed typed record per cognee-cli.md. Best-effort is accepted per ADR-7.
- Two pre-existing PytestUnknownMarkWarning for `SC_US_11_1_ALL_TOOLS` and `SC_US_14_CALL_ENVELOPE` BDD tags remain unregistered — pre-existing, not introduced here. Tag: qa-engineer.

### References

- adr-7.md, driver.py, neo4j_driver.py, schema.py, wiki/pages/manuals/cognee-cli.md

---

run_id: cpp-mcp-1
story: defect-fix QD-TRANS-001 — appended
date: 2026-05-16
developer-model: claude-sonnet-4-6

## QD-TRANS-001 — macOS symlink flakiness fix

### Files changed

- `tests/unit/test_foundation_property.py` — ruff format reformatted (import sort; removed unused `re` and `typing.Any` imports via `ruff check --fix`)
- `tests/unit/test_graphdb_additions.py` — ruff format reformatted; removed unused imports `socketserver`, `unittest.mock.patch`; removed unused variable assignments `n1`, `e1` (F841 — required to clear LINT_FAIL gate)

### Fix description

`test_valid_path_inside_root_always_passes` was intermittently failing on macOS because `tempfile.TemporaryDirectory()` returns `/var/folders/...` while `validate_path()` resolves via `os.path.realpath()` to `/private/var/folders/...`. The fix (`_os.path.realpath(tmp)`) was already present in the file; no additional logic edit was required. The hypothesis examples cache was cleared to ensure no stale failing replay existed.

### Exit-criteria results

- `uv run ruff format --check .` → PASS (58 files)
- `uv run ruff check .` → PASS
- `uv run mypy --strict src/cpp_mcp` → PASS (28 files)
- `uv run pytest -q` → 327 passed, 1 skipped (NEO4J_TEST_URI not set — expected)

### Follow-ups (tag: sr-dev)

- Register `SC_US_14_CALL_ENVELOPE` and `SC_US_11_1_ALL_TOOLS` marks in `[tool.pytest.ini_options].markers` in pyproject.toml to clear PytestUnknownMarkWarning (advisory, non-blocking).

### References

- logs/qa-engineer-transport.md (QD-TRANS-001), tests/unit/test_foundation_property.py, src/cpp_mcp/core/path_guard.py
