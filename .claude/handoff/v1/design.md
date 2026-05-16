# Design: C++ Semantic Analysis MCP Server

run_id: cpp-mcp-1
stage: architect
date: 2026-05-16
inputs:
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/requirements.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/CHARTER.md

---

## 1. Overview

Local Python MCP server (`mcp` SDK, official Anthropic Python implementation) wrapping `clang.cindex` (`libclang`) to expose 7 read-only C++ semantic analysis tools plus 1 export tool to LLM agents. Stateless build context — every tool accepts an optional `build_path` and resolves flags via `clang.cindex.CompilationDatabase.fromDirectory`, falling back to `default_flags` when absent. Two transports: stdio (P0) and HTTP (P1). All cross-cutting policy (path-guard, error envelope, TU cache, read-only) is enforced in shared modules consumed by every tool.

Tool count: **7** (OQ-1 resolved — see ADR-1). The dispatch brief's "9" was an error; only 7 tool signatures appear in `requirements-raw.md` §3.

---

## 2. Module breakdown

```
cpp_mcp/
├── server/
│   ├── __init__.py
│   ├── app.py              # MCP Server instance, tool registration
│   ├── stdio_transport.py  # stdio entry point
│   ├── http_transport.py   # FastAPI/Starlette HTTP entry, /mcp endpoint
│   └── config.py           # env-var parsing: ALLOWED_ROOTS, CACHE_CAPACITY, DEFAULT_FLAGS, LOG_LEVEL
├── core/
│   ├── path_guard.py       # validate_path(p, kind) -> AbsPath | raises PathViolation
│   ├── error_envelope.py   # ErrorCode enum, build_error(code, message, tool, request_id), wrap_tool()
│   ├── compile_db.py       # resolve_flags(file_path, build_path) -> (flags, source)
│   ├── tu_cache.py         # LRUCache keyed (abs_file, abs_build|"", flags_hash); mtime check
│   ├── clang_session.py    # Index singleton, parse_tu(), thread-pool dispatcher (libclang lock)
│   └── ast_walker.py       # cursor traversal, depth/range filter, node-count budget
├── tools/
│   ├── get_definition.py
│   ├── get_references.py
│   ├── get_type_info.py
│   ├── get_ast.py
│   ├── get_header_info.py
│   ├── get_preprocessor_state.py
│   └── export_to_graphdb.py
├── graphdb/
│   ├── exporter.py         # orchestrates per-file extraction -> driver.write_batch()
│   ├── schema.py           # node/edge type constants
│   ├── driver.py           # GraphDriver Protocol
│   └── neo4j_driver.py     # MVP implementation (Bolt)
└── tests/
    ├── unit/               # pytest, libclang fixtures
    ├── bdd/                # pytest-bdd; features map to scenarios.md @SC-* tags
    └── fixtures/           # tiny C++ files + compile_commands.json
```

### Module responsibilities

- **server/app.py** — registers each `tools/*` callable with the MCP SDK; each tool is wrapped by `error_envelope.wrap_tool()` which catches everything and emits the envelope.
- **core/path_guard.py** — single source of truth for path validation. Steps: (1) reject if `..` literal present in input, (2) `os.path.abspath` + `os.path.realpath` (symlink resolved), (3) require resolved path is under one of the configured allowed roots via `os.path.commonpath`. See ADR-3, ADR-4.
- **core/compile_db.py** — wraps `clang.cindex.CompilationDatabase.fromDirectory(build_path)`. Returns `(flags, "compilation_db")` if found, else `(default_flags, "default")`. Catches `CompilationDatabaseError` for malformed JSON and falls back silently to default flags (see ADR-9).
- **core/tu_cache.py** — `collections.OrderedDict` LRU. Key = `(realpath(file), realpath(build_path) or "", sha1(flags_tuple))`. Value = `(TranslationUnit, source_mtime_ns)`. On lookup, re-stat the source file; if mtime differs, evict and re-parse. Capacity from env `CACHE_CAPACITY` (default 128). See ADR-6.
- **core/clang_session.py** — owns the single `clang.cindex.Index` (libclang's Index is not safe for concurrent parses from multiple threads — see ADR-2). Exposes `parse(file, flags) -> TranslationUnit` guarded by a `threading.Lock`. All blocking libclang work runs in a `ThreadPoolExecutor(max_workers=1)` (sequential parses) so asyncio event loop in the HTTP transport stays responsive.
- **core/ast_walker.py** — single traversal implementation reused by `get_ast`, `get_references`, `get_header_info`, and the graphdb exporter. Enforces node-count budget (see ADR-5).
- **graphdb/driver.py** — `GraphDriver` Protocol with `connect()`, `upsert_nodes(batch)`, `upsert_edges(batch)`, `close()`. MVP implementation: `neo4j_driver.py` (see ADR-7).

---

## 3. Data flow (per tool call)

```
MCP request -> server.app (tool dispatch)
  -> error_envelope.wrap_tool decorator (generates request_id, catches exceptions)
    -> path_guard.validate_path(file_path)            [ADR-3, ADR-4]
    -> path_guard.validate_path(build_path) if given
    -> compile_db.resolve_flags(file, build) -> (flags, source)
    -> tu_cache.get_or_parse(file, build, flags)
         -> clang_session.parse(...) under lock if miss/stale
    -> tool-specific logic on TranslationUnit cursor
    -> assemble response { ...result, flags_source, cache_hit, request_id }
  -> MCP response
```

`flags_source` (OQ-2) lives **inside each tool's normal result payload** as a top-level field (not in a separate metadata envelope) — keeps the wire format simple and matches scenario assertions in `SC-US-1-3`, `SC-US-9-1` etc.

---

## 4. Error handling

Single error envelope shape (US-13, ADR-8):

```json
{
  "code": "<ERROR_CODE>",
  "message": "<human-readable>",
  "tool": "<tool_name>",
  "request_id": "<uuid4>"
}
```

`ErrorCode` enum: `FILE_NOT_FOUND, INVALID_POSITION, INVALID_RANGE, INVALID_ARGUMENT, PATH_VIOLATION, DB_UNREACHABLE, PARSE_ERROR, INTERNAL_ERROR`.

### Error decision rules

| Condition | Code | Resolves |
|---|---|---|
| `file_path` or `build_path` contains `..` literal | `PATH_VIOLATION` | US-12/AC-1,2 |
| `realpath(file_path)` outside allowed roots | `PATH_VIOLATION` | US-12/AC-3,6, ADR-4 |
| Symlink resolves outside allowed roots | `PATH_VIOLATION` | US-12/AC-3, ADR-4 |
| `file_path` does not exist (after path-guard) | `FILE_NOT_FOUND` | US-1/AC-5 etc. |
| `build_path` exists but is a regular file | `INVALID_ARGUMENT` | **OQ-NEW-1, ADR-9** |
| `build_path` directory has no/ malformed `compile_commands.json` | silent fallback to `default_flags`, response `flags_source="default"` | US-1/AC-7, **OQ-NEW-2 part B, ADR-9** |
| `line`/`col` out of file range | `INVALID_POSITION` | US-1/AC-6 |
| `start_line > end_line` (get_ast) | `INVALID_RANGE` | US-4/AC-9 |
| libclang produces partial AST + diagnostics | success with `parse_errors: [...]` | US-4/AC-7 |
| libclang produces **zero AST nodes** with fatal diagnostics | `PARSE_ERROR` | **OQ-NEW-2 part A, ADR-9** |
| graphdb missing/empty `db_uri` or `build_path` | `INVALID_ARGUMENT` | US-7/AC-9 |
| graphdb connect/write failure | `DB_UNREACHABLE` | US-7/AC-3 |
| Any other unhandled exception | `INTERNAL_ERROR` (no stack trace, no internal paths) | US-13/AC-2 |

**Partial success (OQ-16):** does NOT use the error envelope. Successful payloads carry `parse_errors: [...]` (US-4/AC-7) or `errors: [...]` (US-7/AC-5) as inline fields. The error envelope is reserved for the call as a whole failing.

### Allowed paths inside `message`

Only paths the caller already sent (echoed back) or `<redacted>`. Never include server-internal absolute paths, Python tracebacks, or libclang library paths. Achieved by a string-allowlist filter in `error_envelope.build_error`.

---

## 5. Transport

**Stdio (P0):** MCP SDK's `stdio_server()` context manager. Synchronous JSON-RPC over stdin/stdout. Serial by construction (one in-flight request at a time) — matches libclang serial-parse constraint trivially.

**HTTP (P1):** FastAPI app exposing `POST /mcp` and `GET /healthz` (also returns `{cache_size, cache_capacity, cache_hit_rate}` per US-10/AC-3). Requests dispatched on asyncio; CPU-bound libclang parses are offloaded to the shared `ThreadPoolExecutor(max_workers=1)` (ADR-2). No authentication in v1 (OQ-17, ADR-10) — server binds `127.0.0.1` only and prints a startup warning if a non-loopback bind is requested.

Both transports share the same `tools/*` callables; transport is a thin shell.

---

## 6. Configuration (startup, environment variables)

| Var | Required | Default | Notes |
|---|---|---|---|
| `CPP_MCP_ALLOWED_ROOTS` | yes | — | Colon-separated absolute paths; server refuses to start if unset (US-12/AC-5). ADR-3. |
| `CPP_MCP_DEFAULT_FLAGS` | no | `-std=c++20 -I. -x c++` | Space-separated; tokenized via `shlex.split`. US-9/AC-4. |
| `CPP_MCP_CACHE_CAPACITY` | no | `128` | Positive int. US-10/AC-5. |
| `CPP_MCP_TRANSPORT` | no | `stdio` | `stdio` or `http`. |
| `CPP_MCP_HTTP_PORT` | no | `8765` | Used only when transport=http. |
| `CPP_MCP_HTTP_BIND` | no | `127.0.0.1` | Warn-on-non-loopback. |
| `CPP_MCP_AST_MAX_NODES` | no | `5000` | ADR-5. |
| `CPP_MCP_AST_MAX_BYTES` | no | `1048576` | 1 MiB serialized cap. ADR-5. |

Per-call `default_flags` override (OQ-12): **out of scope for v1** — keeps the contract small. Future work; not blocking.

---

## 7. Resolved Open Questions (index)

| OQ | Decision | Where |
|---|---|---|
| OQ-1  | 7 tools (dispatch brief mistake) | §1, ADR-1 |
| OQ-2  | `flags_source` inline in result | §3 |
| OQ-3  | References = current TU only (v1) | ADR-1 |
| OQ-4  | AST cap: 5000 nodes OR 1 MiB serialized, `truncated:true` | ADR-5 |
| OQ-5  | Graph edge types fixed: `CHILD`, `TYPE_REF`, `CALL` | ADR-1 |
| OQ-6  | Orphaned include = TU-scope (no symbol of include used in current TU) | ADR-1 |
| OQ-7  | `cpp_get_preprocessor_state`: include transitive macros, tag each with `defined_at.file` | ADR-1 |
| OQ-8  | GraphDB MVP = **Neo4j** via Bolt; behind `GraphDriver` Protocol | ADR-7 |
| OQ-9  | Idempotent upsert keyed on USR (nodes) + (source_usr,target_usr,edge_type) (edges) | ADR-7 |
| OQ-10 | `recursive=false` default; `recursive=true` supported v1 | ADR-1 |
| OQ-11 | Single libclang lock + `ThreadPoolExecutor(max_workers=1)`; asyncio event loop free | ADR-2 |
| OQ-12 | Per-call `default_flags` override deferred | §6 |
| OQ-13 | mtime polled on every cache lookup (no watcher) | ADR-6 |
| OQ-14 | List of allowed roots via `CPP_MCP_ALLOWED_ROOTS` (colon-separated) | ADR-3 |
| OQ-15 | Resolve symlinks then check; reject if resolved path leaves allowed roots | ADR-4 |
| OQ-16 | Partial success uses inline `parse_errors[]` / `errors[]`, not envelope | §4 |
| OQ-17 | No HTTP auth v1; loopback bind only | ADR-10 |
| OQ-NEW-1 | `build_path` is a file → `INVALID_ARGUMENT` | ADR-9 |
| OQ-NEW-2 | `PARSE_ERROR` only when zero-node TU + fatal diagnostics; malformed `compile_commands.json` → silent default-flags fallback | ADR-9 |

---

## 8. Test seams

- **path_guard** is a pure function over (input_path, allowed_roots) → result. Unit-testable without libclang.
- **compile_db.resolve_flags** is a pure function over (file, build_path, default_flags) → (flags, source). Fixture: tiny `compile_commands.json` files.
- **tu_cache** can be tested with a mock parser callable injected via constructor (no libclang needed for LRU/mtime tests).
- **clang_session** is the only module that imports `clang.cindex` directly. Tests can be tagged `@pytest.mark.libclang` and skipped in environments without libclang.
- **error_envelope.wrap_tool** decorator tested with synthetic exceptions.
- **tools/*** integration-tested via BDD against scenarios.md `@SC-*` tags using `pytest-bdd`; fixtures provide small real `.cpp` files under a temp allowed-root.
- **graphdb/neo4j_driver** behind a `GraphDriver` Protocol; tests use a fake in-memory driver. Real Neo4j only required for one smoke test gated by `NEO4J_TEST_URI` env.

---

## 9. Traceability

Every US has a module owner:

| US | Primary module | Verified by scenario tags |
|---|---|---|
| US-1 get_definition  | tools/get_definition.py        | SC-US-1-* |
| US-2 get_references  | tools/get_references.py        | SC-US-2-* |
| US-3 get_type_info   | tools/get_type_info.py         | SC-US-3-* |
| US-4 get_ast         | tools/get_ast.py + ast_walker  | SC-US-4-* |
| US-5 get_header_info | tools/get_header_info.py       | SC-US-5-* |
| US-6 preprocessor    | tools/get_preprocessor_state.py| SC-US-6-* |
| US-7 graphdb export  | tools/export_to_graphdb.py + graphdb/* | SC-US-7-* |
| US-8 stateless       | core/* (absence-of-globals)    | SC-US-8-* |
| US-9 default flags   | core/compile_db.py + config.py | SC-US-9-* |
| US-10 TU cache       | core/tu_cache.py               | SC-US-10-* |
| US-11 read-only      | architectural (no write APIs)  | SC-US-11-* |
| US-12 path traversal | core/path_guard.py             | SC-US-12-* |
| US-13 error envelope | core/error_envelope.py         | SC-US-13-* |
| US-14 transport      | server/{stdio,http}_transport.py | SC-US-14-* |

---

## 10. Pre-flight resource note

libclang is memory-heavy. A cache of 128 TUs on a moderately-sized C++ codebase can use 1–4 GiB RSS. Operators on memory-constrained hosts (<4 GiB free) should set `CPP_MCP_CACHE_CAPACITY=16`. Server logs RSS once per 100 cache inserts at INFO.

---

## 11. Out-of-scope for design.md (defer to senior-developer plan.md)

- Exact pytest-bdd file layout per feature
- Pinning of `clang` Python package version + system libclang ABI compatibility matrix
- packaging (pyproject.toml content, entry-points)
- CI configuration

References:
- ADRs: adr-1 through adr-10 in this directory.
- Charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/CHARTER.md
