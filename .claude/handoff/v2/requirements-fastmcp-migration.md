# Requirements: Migrate cpp-mcp Transport Layer to FastMCP

run_id: cpp-mcp-2
stage: product-manager (migration)
date: 2026-05-16
supersedes: v1/adr-10.md (Official MCP Python SDK)

---

## 1. Motivation

The v1 transport was built directly on `mcp.server.Server` + `mcp.server.stdio.stdio_server` (the low-level official SDK), with hand-written JSON Schema dicts (`server/schemas.py`), hand-rolled `_TOOL_SPECS` / `_HANDLERS` registries (`server/app.py`), and an HTTP transport (`server/http_transport.py`) that was scoped P1 in v1 and never implemented. **FastMCP v3.1.1** (March 2026, stable) is now the de-facto standard Python framework for MCP servers — per `[[pages/manuals/fastmcp/getting-started]]` it powers ~70% of MCP servers across all languages. Migrating to FastMCP gives us:

| Capability | Today (low-level SDK) | After FastMCP migration |
|---|---|---|
| Tool registration | Hand-written `_TOOL_SPECS` list + `_HANDLERS` dict + two decorators (`@server.list_tools`, `@server.call_tool`) | `@mcp.tool` on the function — one decorator per tool |
| Input schema | Hand-written JSON Schema dicts in `schemas.py` (143 lines) | Auto-generated from Python type annotations + docstrings |
| HTTP transport | Planned, never implemented (`http_transport.py` is a stub) | `mcp.run(transport="http", host="127.0.0.1", port=...)` — built in |
| Startup/teardown | Ad-hoc in `stdio_transport._run_stdio` | `lifespan=...` async context manager; values reachable as `ctx.lifespan_context` |
| Blocking-call thread affinity | Manual `ThreadPoolExecutor(max_workers=1)` in `clang_session.py` (ADR-2) | **FastMCP supports sync `def` handlers** — register tools as plain sync functions and FastMCP runs them off the event loop. The handler body still funnels libclang work through `ClangSession.executor` to keep ADR-2's single-worker invariant. See §5 risks. |
| Error masking | Custom regex sanitizer in `error_envelope._sanitize_message` | Built-in `mask_error_details=True` (but envelope shape ≠ FastMCP default — see §3) |
| Custom HTTP routes (health, etc.) | Would have needed bespoke Starlette plumbing | `@mcp.custom_route("/health", methods=["GET"])` |
| In-process testing | Spawn subprocess + stdio plumbing | `async with Client(transport=mcp)` — same process |

Sources (Cognee, all already-ingested wiki pages): `[[pages/manuals/fastmcp/getting-started]]`, `[[pages/manuals/fastmcp/servers]]`, `[[pages/manuals/fastmcp/cli]]`. Primary source: **Cognee** (`agent-memory` dataset). No context7 fetch needed for this scoping pass — the wiki already has the canonical FastMCP 3.1.x reference for `fastmcp.server`, `fastmcp.tools`, `fastmcp.server.middleware`, and `fastmcp.server.lifespan`.

---

## 2. Scope

**In scope (v2 migration):**

- Replace `cpp_mcp/server/app.py` tool registration (`_TOOL_SPECS` + `_HANDLERS` + `@server.list_tools` + `@server.call_tool`) with FastMCP `@mcp.tool` decorators on the 7 existing handler functions.
- Replace `cpp_mcp/server/schemas.py` (hand-written JSON Schema dicts) with FastMCP's type-hint + docstring schema generation. Keep the file only if a verification fixture is needed (see US-4/AC-3).
- Replace `cpp_mcp/server/stdio_transport.py` body (`stdio_server()` + `server.run`) with `mcp.run()` / `mcp.run_stdio_async()`.
- Implement `cpp_mcp/server/http_transport.py` for real, using `mcp.run(transport="http", host=..., port=...)` — closes the v1 gap on US-14/AC-2.
- Move libclang `Index` warmup and TU cache hydration from `build_app` body to a FastMCP `@lifespan` async context manager so that startup ordering is explicit and teardown closes the cache cleanly.
- Update `__main__.py` + `pyproject.toml [project.scripts]` if the entry-point signature changes.
- Pin `fastmcp==3.1.1` (or `>=3.1.1,<3.2`) in `pyproject.toml`. The FastMCP wiki page warns that minor versions may carry protocol-driven breaking changes, so an exact pin or `~=3.1.0` is required.
- Write an ADR (provisionally ADR-11) superseding ADR-10.

**Out of scope (explicitly preserved unchanged):**

- Tool semantics: the 7 tool *names* (`cpp_get_definition`, `cpp_get_references`, `cpp_get_type_info`, `cpp_get_ast`, `cpp_get_header_info`, `cpp_get_preprocessor_state`, `cpp_export_to_graphdb`), their argument names/types, and their response field names.
- Error codes and the error envelope shape `{code, message, tool, request_id}` (ADR-8).
- The 8+ `CPP_MCP_*` environment variables (`CPP_MCP_ALLOWED_ROOTS`, `CPP_MCP_DEFAULT_FLAGS`, `CPP_MCP_CACHE_CAPACITY`, `CPP_MCP_AST_MAX_NODES`, `CPP_MCP_AST_MAX_BYTES`, `CPP_MCP_LIBCLANG_PATH`, `CPP_MCP_TRANSPORT`, `CPP_MCP_HTTP_PORT`, `CPP_MCP_HTTP_BIND`, `CPP_MCP_LOG_LEVEL`) — names, defaults, and semantics unchanged.
- `CPP_MCP_ALLOWED_ROOTS` path-guard semantics: realpath resolution, `..`-component rejection, allowed-roots inclusion check (ADR-3, ADR-4).
- `ClangSession`, `tu_cache`, `path_guard`, `compile_db`, `error_envelope` modules — no changes to their public APIs.
- The `core/error_envelope.wrap_tool` decorator stays as-is; FastMCP does not replace it (see Compatibility §3, error envelope row).
- The graphdb backend (Neo4j via Bolt, ADR-7).
- BDD `.feature` files (`tests/bdd/features/`) — scenarios untouched.
- `tools/*.py` business logic.
- ADR-1, ADR-2, ADR-3, ADR-4, ADR-5, ADR-6, ADR-7, ADR-8, ADR-9 remain authoritative.

---

## 3. Compatibility Constraints (HARD — must not regress)

These are gate conditions, not aspirations. Any AC below that cannot be met blocks the migration.

| # | Constraint | Verification |
|---|---|---|
| C-1 | All 7 tool names unchanged: `cpp_get_definition`, `cpp_get_references`, `cpp_get_type_info`, `cpp_get_ast`, `cpp_get_header_info`, `cpp_get_preprocessor_state`, `cpp_export_to_graphdb`. | `tools/list` MCP call returns exactly these 7 names. BDD scenarios `@SC-US-1-*` through `@SC-US-7-*` pass unchanged. |
| C-2 | Every tool's argument name, type, and required/optional status unchanged versus `server/schemas.py` today. | Snapshot the FastMCP-generated `inputSchema` for each tool; diff against the current `CPP_*_SCHEMA` dict; differences must be limited to whitespace, `$defs` additions, or `description` text from docstrings — **no rename, no type narrowing, no new required field**. |
| C-3 | Every tool's success-response fields unchanged, including the three metadata fields present on every successful call: `flags_source` (`"compilation_db"` / `"default"`), `cache_hit` (bool), `request_id` (uuid4 hex). | Existing 327 pytest cases assert on these fields and must continue to pass. |
| C-4 | Error envelope wire shape unchanged: `{code, message, tool, request_id}` with `code` ∈ `{FILE_NOT_FOUND, INVALID_POSITION, INVALID_RANGE, INVALID_ARGUMENT, PATH_VIOLATION, DB_UNREACHABLE, PARSE_ERROR, INTERNAL_ERROR}`. | This is **incompatible** with FastMCP's default error handling (which uses `ToolError` → string in `content`). Solution: keep `core/error_envelope.wrap_tool` and have FastMCP tools return the envelope as `structured_content` / `result.data`. **Architect to decide exact mapping** — see OQ-2. |
| C-5 | All 10 `CPP_MCP_*` env vars honored with current defaults. `CPP_MCP_TRANSPORT=stdio\|http`, `CPP_MCP_HTTP_PORT=8765`, `CPP_MCP_HTTP_BIND=127.0.0.1` route to the correct FastMCP `mcp.run()` invocation. | `tests/unit/test_config.py` must pass unchanged. New BDD scenario for `CPP_MCP_TRANSPORT=http`. |
| C-6 | `CPP_MCP_ALLOWED_ROOTS` path-guard semantics unchanged (ADR-3, ADR-4): symlinks resolved via `os.path.realpath`, `..`-components rejected, single colon-separated list. | `core/path_guard.py` not modified. Existing path-violation tests pass. |
| C-7 | 327 pytest cases pass; 1 skipped (Neo4j) remains skipped unless `NEO4J_TEST_URI` is set. No new skips. | `uv run pytest -q` reports `327 passed, 1 skipped`. |
| C-8 | `ThreadPoolExecutor(max_workers=1)` + `threading.Lock` for libclang access (ADR-2) preserved — libclang `Index` is not reentrant. | `core/clang_session.py` unchanged. FastMCP's per-tool `run_in_thread=True` MUST funnel into the same executor; do not let FastMCP spin per-call threads that bypass the lock. |
| C-9 | Logs go to **stderr**, stdout is reserved for MCP protocol bytes on stdio transport. | `logging.basicConfig(..., stream=sys.stderr)` preserved. FastMCP's own logger configured to stderr at server construction. |
| C-10 | The `cpp-mcp` console-script entry point and `python -m cpp_mcp` continue to work with no caller-side changes (i.e., existing `~/.claude/mcp.json` configs keep working). | Manual smoke test + BDD scenario `@SC-US-14-1`. |

---

## 4. User Stories

AC IDs are story-scoped: `US-N/AC-M`.

---

### US-M1 — Replace stdio transport with FastMCP, preserving parity

**Story:** As an MCP client (Claude Code, Claude Desktop), I want the cpp-mcp server's stdio transport to be served by FastMCP, so that I keep all current behavior with less hand-rolled code in the server.

**AC:**
- AC-1: `python -m cpp_mcp` with `CPP_MCP_ALLOWED_ROOTS` set starts a FastMCP server on stdio; `initialize` + `tools/list` + a `tools/call` for each of the 7 tools return successfully.
- AC-2: The server's reported protocol version, name (`"cpp-mcp"`), and `instructions` field (currently absent — may be added) match v1 or add `instructions` only as additive metadata.
- AC-3: All 327 existing pytest cases pass; the BDD step files that spawn `python -m cpp_mcp` as a subprocess still work without modification.
- AC-4: Stdout contains only MCP JSON-RPC frames; all log output is on stderr (verify with `python -m cpp_mcp 2>/dev/null | head -c 1` returns a JSON frame byte after one `initialize` request).
- AC-5: Process exits 0 on EOF on stdin; exits 1 with a sanitized message on `ConfigError`.

**Priority:** P0
**Dependencies:** US-M3, US-M4, US-M6.

---

### US-M2 — Implement HTTP transport for real (closes v1 US-14/AC-2)

**Story:** As an operator running cpp-mcp behind a remote agent, I want `CPP_MCP_TRANSPORT=http` to actually serve `/mcp` over HTTP on a configurable port and bind address, so that the v1 P1 gap (`http_transport.py` was a stub) is closed using FastMCP's built-in Streamable HTTP support.

**AC:**
- AC-1: With `CPP_MCP_TRANSPORT=http CPP_MCP_HTTP_PORT=8765 CPP_MCP_HTTP_BIND=127.0.0.1`, the server starts and accepts MCP requests at `http://127.0.0.1:8765/mcp` (path may differ per FastMCP default — architect to confirm).
- AC-2: All 7 tool calls return identical responses (modulo `request_id`) when invoked over HTTP vs. stdio. Verified by a new BDD scenario that runs each tool through both transports against the same fixture and asserts equal output.
- AC-3: A non-loopback bind value emits a WARNING log line (existing v1 behavior — `runbook.md §3`).
- AC-4: A `GET /health` endpoint returns `200 OK` plain text — implemented via `@mcp.custom_route("/health", methods=["GET"])`.
- AC-5: HTTP transport requires no authentication in v2 (matches v1 ADR-10 deferral). An ADR or design note explicitly defers auth to a future story; if added, would use `JWTVerifier` / `MultiAuth` from `fastmcp.server.auth`.

**Priority:** P1 (was unimplemented in v1; now reachable for free via FastMCP).
**Dependencies:** US-M1.

---

### US-M3 — Register tools via `@mcp.tool` decorators

**Story:** As a developer maintaining cpp-mcp, I want each of the 7 tool handlers exposed via a single `@mcp.tool` decorator on the tool's implementation function, so that the parallel `_TOOL_SPECS` list and `_HANDLERS` dict in `app.py` (~150 lines of glue) can be deleted.

**AC:**
- AC-1: Each of the 7 tools is registered by exactly one `@mcp.tool` decorator. The `_TOOL_SPECS` list and `_HANDLERS` dict in `app.py` are removed.
- AC-2: The tool name in MCP `tools/list` matches the existing name exactly (e.g., `cpp_get_definition`, not `get_definition`). Where the Python function name differs (e.g., `get_definition` vs. tool name `cpp_get_definition`), `@mcp.tool(name="cpp_get_definition")` is used.
- AC-3: The tool description string in `tools/list` matches the existing one (currently held in `_TOOL_SPECS`). Descriptions move to docstrings or `@mcp.tool(description=...)`.
- AC-4: Tool dependencies (`allowed_roots`, `default_flags`, `session`, `ast_max_nodes`, `ast_max_bytes`) are injected via FastMCP `Depends(...)` or via closure capture inside the lifespan (architect to choose — see OQ-3). These parameters MUST NOT appear in the published MCP `inputSchema`.
- AC-5: The `mypy --strict` pass continues to succeed on `src/`.

**Priority:** P0
**Dependencies:** US-M4 (schema generation), US-M5 (error envelope), US-M6 (lifespan).

---

### US-M4 — Auto-generate tool input schemas from type hints, verified against current schemas

**Story:** As a developer, I want FastMCP to derive each tool's JSON Schema from the Python type hints and docstrings, so that `server/schemas.py` (143 lines of hand-maintained dicts) can be removed without surprising any existing MCP client.

**AC:**
- AC-1: After migration, `server/schemas.py` is deleted (or retained only as a frozen fixture under `tests/fixtures/expected_schemas/`).
- AC-2: For each of the 7 tools, the FastMCP-generated `inputSchema` is semantically equivalent to the v1 schema in `server/schemas.py`:
  - same `required` field set,
  - same property names,
  - same property types (allowing the JSON Schema `["string","null"]` ↔ Pydantic `Optional[str]` representation),
  - same enum values (`format` enum for `cpp_get_ast`),
  - same defaults (`depth=3`, `format="json"`, `recursive=False`),
  - `additionalProperties: false` preserved.
- AC-3: A unit test under `tests/unit/test_schema_parity.py` loads each generated schema from a live `FastMCP` instance and asserts the above equivalence against frozen v1 schema dicts checked in under `tests/fixtures/expected_schemas/`. The test must fail loudly if any property is renamed, dropped, or its type widened/narrowed.
- AC-4: Argument descriptions in the generated schema are taken from `Annotated[str, "..."]` or Google-style docstrings; missing descriptions cause a test failure (no silent loss of documentation).

**Priority:** P0
**Dependencies:** US-M3.

---

### US-M5 — Preserve error envelope shape on every failure path

**Story:** As an LLM agent consuming cpp-mcp responses, I want all error responses to keep the exact envelope `{code, message, tool, request_id}` with the existing 8 error codes, so that no agent-side error-handling code breaks.

**AC:**
- AC-1: The `core/error_envelope.wrap_tool` decorator is applied to every FastMCP-registered tool function. It runs *before* FastMCP serializes the return value, so the envelope shape ends up on the wire.
- AC-2: For each error code (`FILE_NOT_FOUND`, `INVALID_POSITION`, `INVALID_RANGE`, `INVALID_ARGUMENT`, `PATH_VIOLATION`, `DB_UNREACHABLE`, `PARSE_ERROR`, `INTERNAL_ERROR`), an existing pytest case exercises the failure path and asserts the envelope shape; all such tests continue to pass.
- AC-3: The `_sanitize_message` regex that redacts non-echoed absolute paths to `<redacted>` continues to run (no path leak in messages).
- AC-4: FastMCP's `mask_error_details=True` is set on the FastMCP constructor as defense-in-depth, but the primary error path remains `wrap_tool` → structured envelope dict (so an unexpected raise still produces our envelope, not FastMCP's generic message).
- AC-5: The envelope is returned such that the MCP client sees it as the tool result payload — architect decides between (a) returning the dict as a structured result (`structured_content`), (b) wrapping it in `ToolResult(structured_content={...})`, or (c) raising a custom exception that FastMCP serializes through middleware. The chosen approach is captured in an ADR.

**Priority:** P0 (the v1 ADR-8 invariant is the single biggest agent-side contract).
**Dependencies:** US-M3.

---

### US-M6 — Lifespan: libclang index + TU cache lifecycle

**Story:** As an operator, I want libclang's `Index` and the TU LRU cache to be created in a FastMCP `lifespan` async context manager, so that startup ordering is explicit and shutdown closes resources cleanly.

**AC:**
- AC-1: A `@asynccontextmanager`-decorated `app_lifespan(server)` constructs `ClangSession(capacity=config.cache_capacity)` and yields it (or yields a dict `{"session": session}`) for tools to consume.
- AC-2: On server shutdown, the lifespan exit path calls `session.close()` (new method if not present) which drains the `ThreadPoolExecutor` and clears the cache.
- AC-3: Tool handlers access the session via `ctx.lifespan_context["session"]` or via a `Depends(get_session)` resolver — not via module-level globals.
- AC-4: The lifespan composes cleanly with the HTTP transport when used: starting `mcp.run(transport="http")` invokes the lifespan exactly once at process start.
- AC-5: If `CPP_MCP_ALLOWED_ROOTS` is unset or `libclang` cannot be loaded, the lifespan raises `ConfigError`, which is caught at the `main()` boundary and exits 1 with a sanitized stderr message — current behavior preserved.

**Priority:** P0
**Dependencies:** US-M1.

---

### US-M7 — Preserve libclang thread-affinity (ADR-2)

**Story:** As an operator, I want libclang access to remain serialized through a single worker thread, so that the non-reentrant `Index` cannot be hit concurrently by FastMCP's runtime.

**Note:** FastMCP supports **sync `def` handlers** in addition to `async def`. Sync handlers are the recommended pattern for this project — they read more naturally for libclang's blocking C API and avoid `loop.run_in_executor` boilerplate inside every tool. The handler body still submits libclang work to `ClangSession.executor.submit(...).result()` to enforce the single-worker invariant.

**AC:**
- AC-1: All libclang work (parse, cursor walks) runs inside the existing `ThreadPoolExecutor(max_workers=1)` owned by `ClangSession`. No FastMCP code path bypasses this executor.
- AC-2: Tool handlers registered as sync `def` MUST still dispatch libclang calls through `ClangSession.executor` rather than calling `clang.cindex` directly on FastMCP's worker thread — sync registration alone does not guarantee serialization across concurrent requests.
- AC-3: A regression test launches N concurrent `tools/call` requests against the HTTP transport for `cpp_get_ast` on the same file and asserts (a) all return correct results, (b) no `clang.cindex` exception, (c) parse count == 1 (cache hit on all but the first) — proves serialization holds end-to-end.
- AC-4: The handler signature convention (sync `def` for all 7 tools, dispatching to `ClangSession.executor`) is documented in the ADR with rationale, replacing the existing `async def` handlers in `src/cpp_mcp/tools/*.py`.

**Priority:** P0 (correctness risk — libclang segfaults on concurrent use).
**Dependencies:** US-M3, US-M6.

---

### US-M8 — Pin `fastmcp` version

**Story:** As a release manager, I want the `fastmcp` dependency exact-pinned (or tilde-pinned to a minor), so that a routine `uv sync` cannot pull in a minor version that introduces a protocol-driven breaking change (FastMCP semver explicitly allows this in minors — per `[[pages/manuals/fastmcp/getting-started]]`).

**AC:**
- AC-1: `pyproject.toml` declares `fastmcp~=3.1.0` (or stricter `fastmcp==3.1.1`).
- AC-2: `uv lock` is committed so CI runs against a deterministic version.
- AC-3: A dependabot-style or manual upgrade check is documented in `runbook.md` for the next FastMCP release.

**Priority:** P1
**Dependencies:** none.

---

### US-M9 — Supersede ADR-10

**Story:** As a future reader of the design history, I want an ADR explicitly marking ADR-10 (Official MCP Python SDK) as superseded by the FastMCP decision, so that the design lineage is unambiguous.

**AC:**
- AC-1: A new `adr-11.md` in `v2/` (or appended-numbered in `v1/`, architect to decide where it lives) is created with `Status: accepted` and `Supersedes: ADR-10`.
- AC-2: ADR-10's `Status:` line is updated to `superseded by ADR-11` (in the v1 file).
- AC-3: The wiki page `[[pages/code/cpp-mcp]]` ADR table is updated to reflect the supersession.
- AC-4: The ADR cites the FastMCP wiki pages used as evidence (`[[pages/manuals/fastmcp/getting-started]]`, `[[pages/manuals/fastmcp/servers]]`).

**Priority:** P0 (CHARTER hygiene).
**Dependencies:** none.

---

## 5. Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-1 | **FastMCP minor-version breakage.** FastMCP explicitly reserves the right to break in minor versions when the MCP protocol changes. A loose constraint could break a working install on next `uv sync`. | US-M8: pin `~=3.1.0` or `==3.1.1`; commit `uv.lock`; gate upgrades behind a manual checklist. |
| R-2 | **Schema drift.** FastMCP-generated `inputSchema` may differ from the hand-written `schemas.py` dicts in subtle ways (e.g., `["string","null"]` vs. `anyOf: [string, null]`; ordering; `$defs`). Existing MCP clients may reject. | US-M4/AC-3: parity test against frozen v1 schemas. Where representations differ but are semantically equivalent, normalize before comparison and document the equivalences. |
| R-3 | **libclang concurrency** (ADR-2). FastMCP's async runtime may concurrently invoke tool handlers; if a handler calls `clang.cindex` directly off-thread, libclang's non-reentrant `Index` can segfault. | US-M7: keep `ClangSession`'s single-worker executor; mandate all libclang access funnels through it; add the concurrent-request regression test in AC-3. |
| R-4 | **Error envelope ≠ FastMCP default.** FastMCP's `ToolError` produces a different wire shape from our `{code, message, tool, request_id}` dict. If the migration leans on `ToolError`, every agent-side error handler breaks. | US-M5: keep `wrap_tool` decorator outermost; return envelope as the tool's return value (structured); do **not** raise `ToolError` from inside `wrap_tool`-decorated functions. |
| R-5 | **Async vs. sync handler signatures.** All 7 current handlers are `async def`. FastMCP supports both `async def` and plain `def`. Recommended convention: convert to sync `def` (simpler for libclang's blocking C API) with libclang dispatch via `ClangSession.executor.submit(...).result()`. Risk is bypassing the single-worker executor on any code path. | Apply sync `def` uniformly per US-M7/AC-4; concurrent-request regression test (AC-3) guards against accidental parallel libclang access. |
| R-6 | **Console-script regression.** `pyproject.toml [project.scripts] cpp-mcp = "cpp_mcp.server.stdio_transport:main"` — if the new entry-point signature changes, existing `~/.claude/mcp.json` configs break for users. | Keep `main()` callable in the same module path; smoke-test the installed `cpp-mcp` binary in CI before tagging. |
| R-7 | **Schema descriptions lost.** Current `schemas.py` has hand-tuned descriptions like "1-based line number of the symbol." If the migration relies on bare type hints, those descriptions disappear. | US-M4/AC-4: require docstrings or `Annotated[..., "..."]` for every parameter; test fails if any description is empty. |
| R-8 | **`fastmcp` runtime dependencies bloat.** `fastmcp` pulls Starlette, anyio, httpx, etc. Some are already transitively present, but the dep tree grows. | Audit `uv tree` after migration; document the new minimum install footprint in `runbook.md`. |

---

## 6. Open Questions (architect to resolve in design phase)

| OQ | Question |
|---|---|
| OQ-1 | Where does ADR-11 live — `v1/adr-11.md` (continuing the series) or `v2/adr-1.md` (resetting per task)? |
| OQ-2 | Error envelope delivery: return the envelope dict as the tool's return value (relying on FastMCP's structured-output handling), or wrap in `ToolResult(structured_content={...})`, or define a custom middleware that catches a `WrappedToolError` exception? Pick one and justify. |
| OQ-3 | Dependency injection mechanism for `allowed_roots`, `default_flags`, `session`, `ast_max_nodes`, `ast_max_bytes`: FastMCP `Depends(...)` resolver, lifespan-context lookup via `ctx.lifespan_context`, or closure capture inside a factory function? |
| OQ-4 | Stdio transport entrypoint: continue calling `asyncio.run(_run_stdio())` in `main()`, or switch to FastMCP's synchronous `mcp.run()` which manages the event loop internally? Affects how `KeyboardInterrupt` and `ConfigError` are caught. |
| OQ-5 | HTTP transport endpoint path: FastMCP's default vs. preserving `/mcp` literal from v1 ADR-10. |
| OQ-6 | Keep `server/schemas.py` as a frozen-fixture file for the parity test (US-M4/AC-3), or move it under `tests/fixtures/expected_schemas/`? |
| OQ-7 | Should we introduce FastMCP `middleware` (`LoggingMiddleware`, `TimingMiddleware`) for observability now, or defer to a v3 story? |
| OQ-8 | `instructions=` field on `FastMCP(...)` constructor — populate with v1's `runbook.md §1` summary, leave empty, or defer? |
| OQ-9 | Per US-M7/AC-4 (resolved direction): sync `def` handlers + `ClangSession.executor.submit(...).result()` dispatch. Architect to confirm against R-3's regression suite and capture in ADR. |

---

## 7. References

**Primary source: Cognee (`agent-memory` dataset)** — queries run during this scoping pass:

1. `cognee search "FastMCP Python library tool registration decorators"` — returned full `[[pages/manuals/fastmcp/getting-started]]` page (4 raw sources) + `[[pages/manuals/fastmcp/python-sdk-reference]]` navigation index (241 raw files under `~/workspace/wiki/raw/mcp/docs/python-sdk__*.md`).
2. `cognee search "FastMCP stdio HTTP transport server lifecycle"` — returned full `[[pages/manuals/fastmcp/servers]]` page (15 raw sources including `servers__server.md`, `servers__lifespan.md`, `servers__transforms__transforms.md`).
3. `cognee search "FastMCP context injection error handling schema generation"` — confirmed `Context` API (`fastmcp.server.context`), `mask_error_details` constructor flag, `ToolError`, `Annotated[..., description]` schema derivation.
4. `cognee recall "FastMCP vs official mcp python sdk"` — confirmed FastMCP 1.0 was folded into the official `mcp` SDK in 2024; standalone v3.1.1 (March 2026) is the de-facto Python framework.

**Wiki pages cited:**
- `[[pages/code/cpp-mcp]]` — current architecture, ADR table, env-var list (10 vars), tool inventory, 327/1 test baseline.
- `[[pages/manuals/fastmcp/getting-started]]` — installation, version-pin warning, minimal server, three pillars, v3 architecture, code-mode.
- `[[pages/manuals/fastmcp/servers]]` — `FastMCP` constructor parameters, tools decorator API, `ToolError`, `mask_error_details`, lifespan, middleware, custom HTTP routes, providers, transforms.
- `[[pages/manuals/fastmcp/python-sdk-reference]]` — 241-file navigation index for SDK details if the design phase needs deeper API specifics.

**v1 handoff files (preserved as authoritative for everything not migrated):**
- `~/workspace/cpp-mcp/.claude/handoff/v1/requirements.md` (US-1..US-14)
- `~/workspace/cpp-mcp/.claude/handoff/v1/design.md`
- `~/workspace/cpp-mcp/.claude/handoff/v1/adr-{1..9}.md` (ADR-10 to be superseded by US-M9)

**Source files inspected during scoping:**
- `src/cpp_mcp/server/app.py` (275 lines — `_TOOL_SPECS` + `_HANDLERS` + handler factories)
- `src/cpp_mcp/server/stdio_transport.py` (53 lines — current `stdio_server` + `server.run` invocation)
- `src/cpp_mcp/server/schemas.py` (143 lines — to be deleted or moved to fixtures)
- `src/cpp_mcp/core/error_envelope.py` (226 lines — `wrap_tool`, `_sanitize_message`, `ErrorCode`; kept as-is)

**Context7 / external docs:** not fetched during scoping. The Cognee-ingested wiki pages already cover everything the requirements document needs. The architect should fetch `https://gofastmcp.com/python-sdk/fastmcp-server-server` and `https://gofastmcp.com/python-sdk/fastmcp-tools-tool` via `mcp__claude_ai_context7__resolve-library-id` + `query-docs` if the design phase needs exact constructor signatures or transform internals not captured on the wiki pages.
