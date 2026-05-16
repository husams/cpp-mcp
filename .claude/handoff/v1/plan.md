# Plan: C++ Semantic Analysis MCP Server

run_id: cpp-mcp-1
stage: senior-developer
date: 2026-05-16
inputs:
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/requirements.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/design.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-1.md … adr-10.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/CHARTER.md

Conventions: Python 3.11+, src-layout package `cpp_mcp` under `src/`, tooling = `ruff format`, `ruff check`, `mypy --strict`, `pytest` + `pytest-bdd`. All commands are run from project root `/Users/husam/workspace/cpp-mcp`.

Per CHARTER invariant I3, every story below carries an `exit-criteria` block with exact commands that MUST exit 0 before the developer marks the story done. Test commands cite the `@SC-*` scenario tags (or `tests/unit/` selectors) defined in scenarios.md.

Tooling commands referenced (assumed installed via `uv sync` / `pip install -e .[dev]` from Story 1):
- `uv run ruff format --check src tests`
- `uv run ruff check src tests`
- `uv run mypy --strict src`
- `uv run pytest -q tests/unit -k <expr>`
- `uv run pytest -q tests/bdd -k <expr>` (pytest-bdd; `-k` matches scenario tag names because pytest-bdd encodes the `@SC-*` tag as a marker AND as part of the generated test-id)

---

## Story 1 — project-bootstrap

- title: project-bootstrap
- ac-ids: (foundational; no functional AC; enables all stories)
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/pyproject.toml (new)
  - /Users/husam/workspace/cpp-mcp/README.md (skeleton — install, run, env vars)
  - /Users/husam/workspace/cpp-mcp/.gitignore (new)
  - /Users/husam/workspace/cpp-mcp/.python-version (`3.11`)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/__init__.py (new; exports `__version__`)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/py.typed (new; empty marker)
  - /Users/husam/workspace/cpp-mcp/tests/__init__.py
  - /Users/husam/workspace/cpp-mcp/tests/unit/__init__.py
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_bootstrap.py (asserts `import cpp_mcp` succeeds and `__version__` is non-empty)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/__init__.py
  - /Users/husam/workspace/cpp-mcp/tests/bdd/conftest.py (placeholder)
- pyproject.toml requirements:
  - `[project]` requires-python = `>=3.11`; declares deps `mcp>=1.0`, `clang>=17,<20` (libclang Python bindings), `neo4j>=5.0` (optional extra `graphdb`), runtime extra empty otherwise.
  - `[project.optional-dependencies]` `dev` = `ruff`, `mypy`, `pytest`, `pytest-bdd`, `pytest-asyncio`, `pytest-cov`.
  - `[project.scripts]` `cpp-mcp = "cpp_mcp.server.stdio_transport:main"`.
  - `[tool.ruff]` line-length=100, target-version=`py311`, select includes `E,F,I,UP,B,SIM,RUF`.
  - `[tool.mypy]` strict=true, packages=`cpp_mcp`, plugins=[]; allow third-party untyped (`clang.cindex`) via `[[tool.mypy.overrides]] module="clang.*" ignore_missing_imports=true`.
  - `[tool.pytest.ini_options]` testpaths=`tests`, addopts=`-ra`, markers include `libclang: requires system libclang`, `neo4j: requires NEO4J_TEST_URI`.
- tests: tests/unit/test_bootstrap.py (smoke import + version).
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv sync --extra dev`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/unit/test_bootstrap.py`
- parallel-safe: false
- depends-on: []

---

## Story 2 — error-envelope-and-path-guard

- title: error-envelope-and-path-guard
- ac-ids: US-12/AC-1, US-12/AC-2, US-12/AC-3, US-12/AC-4, US-12/AC-5, US-13/AC-1, US-13/AC-2, US-13/AC-3
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/__init__.py (new)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/error_envelope.py (new — `ErrorCode` `StrEnum` with the 8 codes in §4 of design; `build_error(code, message, tool, request_id)`; `wrap_tool(tool_name)` decorator; message sanitizer per ADR-8 string-allowlist)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/path_guard.py (new — `validate_path(raw, allowed_roots, kind="file"|"dir")` returning `pathlib.Path`; raises `PathViolationError`; rejects literal `..`, runs `abspath`+`realpath`, requires resolved path under one of `allowed_roots`)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/config.py (new — parses `CPP_MCP_ALLOWED_ROOTS` (colon-separated, required), `CPP_MCP_DEFAULT_FLAGS` via `shlex.split`, `CPP_MCP_CACHE_CAPACITY`, `CPP_MCP_AST_MAX_NODES`, `CPP_MCP_AST_MAX_BYTES`; raises `ConfigError` if `ALLOWED_ROOTS` unset — satisfies US-12/AC-5)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/__init__.py (new, empty)
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_error_envelope.py (covers all 8 `ErrorCode` values; envelope shape; INTERNAL_ERROR has no traceback per US-13/AC-2; sanitizer scrubs internal paths)
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_path_guard.py (covers `..` literal, symlink escape via `tmp_path` symlink fixture, allowed-root pass, outside-allowed-root, missing `ALLOWED_ROOTS` env)
- tests: above unit files. No BDD yet — BDD scenarios for US-12/US-13 are exercised in Stories 5–7 once tools are wired.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/unit/test_error_envelope.py tests/unit/test_path_guard.py`
- parallel-safe: false
- depends-on: [project-bootstrap]

---

## Story 3 — compile-db-and-default-flags

- title: compile-db-and-default-flags
- ac-ids: US-1/AC-3, US-1/AC-4, US-1/AC-7, US-9/AC-1, US-9/AC-2, US-9/AC-3, US-9/AC-4
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/compile_db.py (new — `resolve_flags(file_path: Path, build_path: Path | None, default_flags: tuple[str,...]) -> tuple[tuple[str,...], Literal["compilation_db","default"]]`; wraps `clang.cindex.CompilationDatabase.fromDirectory`; catches `CompilationDatabaseError` (malformed JSON) and falls back to default per ADR-9; raises `InvalidArgumentError` if `build_path` is an existing file per ADR-9 / OQ-NEW-1)
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_compile_db.py (compilation_db hit, file-not-listed→default, no-json→default, malformed-json→default, build_path-is-file→INVALID_ARGUMENT, custom default_flags via config)
  - /Users/husam/workspace/cpp-mcp/tests/fixtures/compile_dbs/ok/compile_commands.json (new — fixture)
  - /Users/husam/workspace/cpp-mcp/tests/fixtures/compile_dbs/malformed/compile_commands.json (new — invalid JSON)
  - /Users/husam/workspace/cpp-mcp/tests/fixtures/compile_dbs/empty/.keep (new — directory without compile_commands.json)
- tests: tests/unit/test_compile_db.py.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/unit/test_compile_db.py`
- parallel-safe: false
- depends-on: [error-envelope-and-path-guard]

---

## Story 4 — clang-session-and-tu-cache

- title: clang-session-and-tu-cache
- ac-ids: US-8/AC-1, US-8/AC-2, US-8/AC-3, US-8/AC-4, US-10/AC-1, US-10/AC-2, US-10/AC-3, US-10/AC-4, US-10/AC-5, US-10/AC-6
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/clang_session.py (new — module-level `clang.cindex.Index`; `threading.Lock`; `ThreadPoolExecutor(max_workers=1)`; async `await parse(file, flags)` shim that submits to the executor per ADR-2)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/tu_cache.py (new — `OrderedDict`-backed LRU keyed `(realpath(file), realpath(build) or "", sha1(flags_tuple))`; value `(TU, source_mtime_ns)`; capacity from config; `get_or_parse(file, build, flags, parser)`; mtime re-stat per lookup per ADR-6; exposes `stats() -> {cache_size, cache_capacity, cache_hit_rate}` per US-10/AC-3)
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_tu_cache.py (hit, miss, LRU eviction, two build_paths separate entries, mtime invalidation, stats, capacity-configurable — uses injected fake parser callable; libclang NOT required)
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_clang_session.py (marked `@pytest.mark.libclang`; smoke parse of a 5-line cpp fixture; verifies single-worker serialization of two concurrent parses)
  - /Users/husam/workspace/cpp-mcp/tests/fixtures/cpp/tiny.cpp (new — trivial parseable C++ file)
- tests: above two unit files.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/unit/test_tu_cache.py tests/unit/test_clang_session.py`
- parallel-safe: false
- depends-on: [compile-db-and-default-flags]

---

## Story 5 — navigation-tools

- title: navigation-tools
- ac-ids: US-1/AC-1, US-1/AC-2, US-1/AC-3, US-1/AC-4, US-1/AC-5, US-1/AC-6, US-1/AC-7, US-1/AC-8, US-1/AC-9, US-2/AC-1, US-2/AC-2, US-2/AC-3, US-2/AC-4, US-2/AC-5, US-2/AC-6, US-2/AC-7, US-3/AC-1, US-3/AC-2, US-3/AC-3, US-3/AC-4, US-3/AC-5, US-3/AC-6, US-3/AC-7
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/__init__.py (new)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/get_definition.py
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/get_references.py
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/get_type_info.py
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/cursor.py (new — `cursor_at(tu, file, line, col)` helper raising `InvalidPositionError` on out-of-range)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/cpp_get_definition.feature (copied from scenarios.md, retaining `@SC-US-1-*` tags)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/cpp_get_references.feature
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/cpp_get_type_info.feature
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_get_definition.py (pytest-bdd `scenarios(...)`)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_get_references.py
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_get_type_info.py
  - /Users/husam/workspace/cpp-mcp/tests/bdd/conftest.py (extend — temp allowed-root, libclang fixtures, request-id capture)
  - /Users/husam/workspace/cpp-mcp/tests/fixtures/cpp/* (additional cpp fixtures: cross-file, auto-typed, template, forward-decl)
- tests: BDD features above tagged `@SC-US-1-*`, `@SC-US-2-*`, `@SC-US-3-*`.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/bdd -k "SC_US_1 or SC_US_2 or SC_US_3"`
- parallel-safe: true
- depends-on: [clang-session-and-tu-cache]

---

## Story 6 — ast-and-structural-tools

- title: ast-and-structural-tools
- ac-ids: US-4/AC-1, US-4/AC-2, US-4/AC-3, US-4/AC-4, US-4/AC-5, US-4/AC-6, US-4/AC-7, US-4/AC-8, US-4/AC-9, US-4/AC-10, US-5/AC-1, US-5/AC-2, US-5/AC-3, US-5/AC-4, US-5/AC-5, US-5/AC-6, US-5/AC-7, US-6/AC-1, US-6/AC-2, US-6/AC-3, US-6/AC-4, US-6/AC-5, US-6/AC-6, US-6/AC-7
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/ast_walker.py (new — depth/range filter, node-count + byte budget per ADR-5, `truncated` flag, JSON and graph emitters; edge types fixed to `CHILD`, `TYPE_REF`, `CALL`)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/get_ast.py
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/get_header_info.py
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/get_preprocessor_state.py
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/cpp_get_ast.feature
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/cpp_get_header_info.feature
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/cpp_get_preprocessor_state.feature
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_get_ast.py
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_get_header_info.py
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_get_preprocessor_state.py
  - /Users/husam/workspace/cpp-mcp/tests/fixtures/cpp/header_api.h, header_standalone.h, header_missing_include.h, config_macros.cpp, ast_test.cpp, broken_partial.cpp, unparseable.cpp
- tests: BDD features above tagged `@SC-US-4-*`, `@SC-US-5-*`, `@SC-US-6-*`.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/bdd -k "SC_US_4 or SC_US_5 or SC_US_6"`
- parallel-safe: true
- depends-on: [clang-session-and-tu-cache]

---

## Story 7 — mcp-server-transport

- title: mcp-server-transport
- ac-ids: US-11/AC-1, US-11/AC-2, US-11/AC-3, US-13/AC-1, US-13/AC-2, US-13/AC-3, US-14/AC-1, US-14/AC-3, US-14/AC-4, US-10/AC-3 (stats endpoint via healthz when HTTP enabled — HTTP itself is P1; stdio is the gate)
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/app.py (new — builds MCP `Server`, registers all 7 tools (graphdb tool delegates to Story 8 placeholder if not yet wired — Story 8 fills in); attaches `wrap_tool` decorator; JSON schemas per tool input)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/stdio_transport.py (new — `async def main()` driving `mcp.server.stdio.stdio_server()`; CLI entry point)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/schemas.py (new — typed input dataclasses / JSON-schema dicts for each tool)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/transport_stdio.feature (SC-US-14-1, SC-US-14-3, SC-US-14-4)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/read_only_enforcement.feature (SC-US-11-1, SC-US-11-2, SC-US-11-3)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/error_envelope.feature (SC-US-13-1, SC-US-13-2, SC-US-13-3 — exercises envelope via real tool calls)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/stateless_build.feature (SC-US-8-1, SC-US-8-2, SC-US-8-3, SC-US-8-4)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/path_traversal.feature (SC-US-12-1..6)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/default_flags.feature (SC-US-9-1..4)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/tu_cache.feature (SC-US-10-1..7)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_transport_stdio.py, test_read_only.py, test_error_envelope_bdd.py, test_stateless_build.py, test_path_traversal.py, test_default_flags.py, test_tu_cache_bdd.py
- HTTP transport (`http_transport.py`, SC-US-14-2) is split out into Story 7b note: implement only if time remains in v1; not a gate for downstream stories. Story exit-criteria below excludes SC-US-14-2.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/bdd -k "SC_US_8 or SC_US_9 or SC_US_10 or SC_US_11 or SC_US_12 or SC_US_13 or SC_US_14_1 or SC_US_14_3 or SC_US_14_4"`
- parallel-safe: false
- depends-on: [navigation-tools, ast-and-structural-tools]

---

## Story 8 — graphdb-exporter

- title: graphdb-exporter
- ac-ids: US-7/AC-1, US-7/AC-2, US-7/AC-3, US-7/AC-4, US-7/AC-5, US-7/AC-6, US-7/AC-7, US-7/AC-8, US-7/AC-9
- files-to-touch:
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/__init__.py (new)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/schema.py (new — node/edge type constants per ADR-7)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/driver.py (new — `GraphDriver` `Protocol`: `connect`, `upsert_nodes`, `upsert_edges`, `close`)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/neo4j_driver.py (new — Bolt impl; MERGE on USR for nodes; MERGE on `(source_usr,target_usr,edge_type)` for edges; per ADR-7)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/exporter.py (new — directory walk filtered to `.cpp .h .hpp .cc .cxx`; `recursive` flag; per-file extraction; partial-failure aggregation per US-7/AC-5)
  - /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/export_to_graphdb.py (new — INVALID_ARGUMENT for missing/empty `db_uri`/`build_path` per US-7/AC-9; DB_UNREACHABLE wrapping `neo4j.exceptions.ServiceUnavailable`)
  - /Users/husam/workspace/cpp-mcp/tests/unit/test_graphdb_exporter.py (uses in-memory fake `GraphDriver`; covers AC-1, AC-2, AC-4, AC-5, AC-8 mtime-unchanged, AC-9)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/features/export_to_graphdb.feature (SC-US-7-1..11)
  - /Users/husam/workspace/cpp-mcp/tests/bdd/test_export_to_graphdb.py (uses fake driver by default; one scenario tagged `@neo4j` requires `NEO4J_TEST_URI` env, otherwise auto-skipped)
- tests: above unit + BDD.
- exit-criteria:
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff format --check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run ruff check src tests`
  - `cd /Users/husam/workspace/cpp-mcp && uv run mypy --strict src`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/unit/test_graphdb_exporter.py`
  - `cd /Users/husam/workspace/cpp-mcp && uv run pytest -q tests/bdd -k "SC_US_7" -m "not neo4j"`
- parallel-safe: true
- depends-on: [mcp-server-transport]

---

## Risks / Out of scope

- HTTP transport (US-14/AC-2) intentionally deferred inside Story 7; mark as follow-up Story 7b if scope permits. Stdio path satisfies P0.
- Per-call `default_flags` override (OQ-12) out of scope for v1 per design §6.
- Real Neo4j integration test gated on `NEO4J_TEST_URI`; CI without Neo4j skips that scenario — explicitly fine per ADR-7.
- libclang ABI / `clang` Python package pin chosen in Story 1 (`clang>=17,<20`); developer may adjust within range if `cindex` import fails on target platform, but must record the chosen version in implementation-notes.md.

## Traceability (story → AC summary)

| Story | ACs covered |
|---|---|
| 1 project-bootstrap | (foundational) |
| 2 error-envelope-and-path-guard | US-12, US-13 (units) |
| 3 compile-db-and-default-flags | US-9 (full), US-1/AC-3,4,7 (unit-only; BDD in S5) |
| 4 clang-session-and-tu-cache | US-8, US-10 (units) |
| 5 navigation-tools | US-1, US-2, US-3 (BDD) |
| 6 ast-and-structural-tools | US-4, US-5, US-6 (BDD) |
| 7 mcp-server-transport | US-8, US-9, US-10, US-11, US-12, US-13, US-14 (AC-1,3,4) (BDD wire-level) |
| 8 graphdb-exporter | US-7 (full) |

References:
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/design.md (modules, error rules, config)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-1.md … adr-10.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md (`@SC-*` tags = pytest-bdd identifiers)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/CHARTER.md (invariant I3)
- Cognee tags: task:cpp-mcp, role:senior-developer
