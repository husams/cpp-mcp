---
run_id: fastmcp-migration-v2
stage: product-manager
date: 2026-05-16
source: /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements-fastmcp-migration.md
supersedes: v1/requirements.md US-14 (HTTP transport — now closed by US-M2)
---

# Requirements: FastMCP Migration (v2)

## AC format note

Acceptance criteria are expressed as testable prose with story-scoped IDs (`US-N/AC-M`). Given/When/Then reformatting is deferred to the BA (downstream stage) to avoid precision loss on multi-bullet AC (e.g., US-M4/AC-2).

---

## Compatibility Constraints (HARD gate conditions)

These apply globally across all stories. Any AC below that cannot be met blocks the migration.

| ID  | Constraint                                                                                                               | Verification                                                                                              |
|-----|--------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| C-1 | All 7 tool names unchanged: `cpp_get_definition`, `cpp_get_references`, `cpp_get_type_info`, `cpp_get_ast`, `cpp_get_header_info`, `cpp_get_preprocessor_state`, `cpp_export_to_graphdb`. | `tools/list` MCP call returns exactly these 7 names. BDD scenarios `@SC-US-1-*` through `@SC-US-7-*` pass unchanged. |
| C-2 | Every tool's argument name, type, and required/optional status unchanged versus `server/schemas.py` today.              | Snapshot FastMCP-generated `inputSchema` per tool; diff against current `CPP_*_SCHEMA` dict; differences limited to whitespace, `$defs` additions, or `description` text — no rename, no type narrowing, no new required field. |
| C-3 | Every tool's success-response fields unchanged, including `flags_source`, `cache_hit`, and `request_id`.                | Existing 327 pytest cases assert on these fields and must continue to pass.                               |
| C-4 | Error envelope wire shape unchanged: `{code, message, tool, request_id}` with the 8 error codes (ADR-8).               | Incompatible with FastMCP's default `ToolError`; solution tracked in US-M5.                              |
| C-5 | All 10 `CPP_MCP_*` env vars honored with current defaults; `CPP_MCP_TRANSPORT=stdio|http` routes correctly.            | `tests/unit/test_config.py` passes unchanged. New BDD scenario for `CPP_MCP_TRANSPORT=http`.             |
| C-6 | `CPP_MCP_ALLOWED_ROOTS` path-guard semantics unchanged (ADR-3, ADR-4).                                                 | `core/path_guard.py` not modified; existing path-violation tests pass.                                    |
| C-7 | 327 pytest cases pass; 1 skipped (Neo4j) remains skipped unless `NEO4J_TEST_URI` set. No new skips.                   | `uv run pytest -q` reports `327 passed, 1 skipped`.                                                      |
| C-8 | `ThreadPoolExecutor(max_workers=1)` + `threading.Lock` for libclang (ADR-2) preserved.                                 | `core/clang_session.py` unchanged; FastMCP's per-tool execution funnels into same executor.              |
| C-9 | All log output on stderr; stdout reserved for MCP protocol bytes on stdio transport.                                    | `logging.basicConfig(..., stream=sys.stderr)` preserved; FastMCP's logger configured to stderr.          |
| C-10| `cpp-mcp` console-script entry point and `python -m cpp_mcp` continue to work with no caller-side changes.            | Manual smoke test + BDD scenario `@SC-US-14-1`.                                                          |

---

## Stories

---

### US-M1 — Replace stdio transport with FastMCP, preserving parity

Story: As an MCP client (Claude Code, Claude Desktop), I want the cpp-mcp server's stdio transport to be served by FastMCP, so that I keep all current behavior with less hand-rolled code in the server.

Acceptance criteria:
- US-M1/AC-1: `python -m cpp_mcp` with `CPP_MCP_ALLOWED_ROOTS` set starts a FastMCP server on stdio; `initialize` + `tools/list` + a `tools/call` for each of the 7 tools return successfully.
- US-M1/AC-2: The server's reported protocol version, name (`"cpp-mcp"`), and `instructions` field match v1 or add `instructions` only as additive metadata.
- US-M1/AC-3: All 327 existing pytest cases pass; BDD step files that spawn `python -m cpp_mcp` as a subprocess still work without modification.
- US-M1/AC-4: Stdout contains only MCP JSON-RPC frames; all log output is on stderr (verify with `python -m cpp_mcp 2>/dev/null | head -c 1` returns a JSON frame byte after one `initialize` request).
- US-M1/AC-5: Process exits 0 on EOF on stdin; exits 1 with a sanitized message on `ConfigError`.

Priority: P0 — entry point for all other migration work; blocks every downstream story.
Dependencies: US-M3, US-M4, US-M6.
Open questions:
- OQ-4: Stdio entrypoint — continue with `asyncio.run(_run_stdio())` in `main()`, or switch to FastMCP's synchronous `mcp.run()` which manages the event loop internally? Affects `KeyboardInterrupt` and `ConfigError` catch behavior.
- OQ-8: `instructions=` field on `FastMCP(...)` constructor — populate with v1 `runbook.md §1` summary, leave empty, or defer?
References: C-5, C-7, C-9, C-10; `[[pages/manuals/fastmcp/servers]]`; `[[pages/manuals/fastmcp/cli]]`.

---

### US-M2 — Implement HTTP transport for real (closes v1 US-14/AC-2)

Story: As an operator running cpp-mcp behind a remote agent, I want `CPP_MCP_TRANSPORT=http` to actually serve `/mcp` over HTTP on a configurable port and bind address, so that the v1 P1 gap (`http_transport.py` was a stub) is closed using FastMCP's built-in Streamable HTTP support.

Acceptance criteria:
- US-M2/AC-1: With `CPP_MCP_TRANSPORT=http CPP_MCP_HTTP_PORT=8765 CPP_MCP_HTTP_BIND=127.0.0.1`, the server starts and accepts MCP requests at the FastMCP-default HTTP path on port 8765 (architect to confirm path — see OQ-5).
- US-M2/AC-2: All 7 tool calls return identical responses (modulo `request_id`) when invoked over HTTP vs. stdio, verified by a new BDD scenario that runs each tool through both transports against the same fixture and asserts equal output.
- US-M2/AC-3: A non-loopback bind value emits a WARNING log line (existing v1 behavior per `runbook.md §3`).
- US-M2/AC-4: A `GET /health` endpoint returns `200 OK` plain text, implemented via `@mcp.custom_route("/health", methods=["GET"])`.
- US-M2/AC-5: HTTP transport requires no authentication in v2 (matches v1 ADR-10 deferral). An ADR or design note explicitly defers auth to a future story; if added, would use `JWTVerifier` / `MultiAuth` from `fastmcp.server.auth`.

Priority: P1 — was unimplemented in v1; now reachable via FastMCP with low incremental cost.
Dependencies: US-M1.
Open questions:
- OQ-5: HTTP transport endpoint path — FastMCP's default vs. preserving `/mcp` literal from v1 ADR-10.
References: C-5; `[[pages/manuals/fastmcp/servers]]`; v1/adr-10.md (US-14/AC-2).

---

### US-M3 — Register tools via `@mcp.tool` decorators

Story: As a developer maintaining cpp-mcp, I want each of the 7 tool handlers exposed via a single `@mcp.tool` decorator on the tool's implementation function, so that the parallel `_TOOL_SPECS` list and `_HANDLERS` dict in `app.py` (~150 lines of glue) can be deleted.

Acceptance criteria:
- US-M3/AC-1: Each of the 7 tools is registered by exactly one `@mcp.tool` decorator. The `_TOOL_SPECS` list and `_HANDLERS` dict in `app.py` are removed.
- US-M3/AC-2: The tool name in MCP `tools/list` matches the existing name exactly (e.g., `cpp_get_definition`). Where the Python function name differs, `@mcp.tool(name="cpp_get_definition")` is used.
- US-M3/AC-3: The tool description string in `tools/list` matches the existing one (currently held in `_TOOL_SPECS`). Descriptions move to docstrings or `@mcp.tool(description=...)`.
- US-M3/AC-4: Tool dependencies (`allowed_roots`, `default_flags`, `session`, `ast_max_nodes`, `ast_max_bytes`) are injected via FastMCP `Depends(...)` or via closure capture inside the lifespan (architect to choose — see OQ-3). These parameters MUST NOT appear in the published MCP `inputSchema`.
- US-M3/AC-5: The `mypy --strict` pass continues to succeed on `src/`.

Priority: P0 — prerequisite for schema generation (US-M4) and error envelope wiring (US-M5).
Dependencies: US-M4 (schema generation), US-M5 (error envelope), US-M6 (lifespan).
Open questions:
- OQ-3: Dependency injection mechanism for `allowed_roots`, `default_flags`, `session`, `ast_max_nodes`, `ast_max_bytes`: FastMCP `Depends(...)` resolver, lifespan-context lookup via `ctx.lifespan_context`, or closure capture inside a factory function?
References: C-1, C-2, C-3; `[[pages/manuals/fastmcp/servers]]`; `src/cpp_mcp/server/app.py`.

---

### US-M4 — Auto-generate tool input schemas from type hints, verified against current schemas

Story: As a developer, I want FastMCP to derive each tool's JSON Schema from Python type hints and docstrings, so that `server/schemas.py` (143 lines of hand-maintained dicts) can be removed without surprising any existing MCP client.

Acceptance criteria:
- US-M4/AC-1: After migration, `server/schemas.py` is deleted (or retained only as a frozen fixture under `tests/fixtures/expected_schemas/`).
- US-M4/AC-2: For each of the 7 tools, the FastMCP-generated `inputSchema` is semantically equivalent to the v1 schema in `server/schemas.py`: same `required` field set, same property names, same property types (allowing `["string","null"]` ↔ Pydantic `Optional[str]` equivalence), same enum values (`format` enum for `cpp_get_ast`), same defaults (`depth=3`, `format="json"`, `recursive=False`), `additionalProperties: false` preserved.
- US-M4/AC-3: A unit test under `tests/unit/test_schema_parity.py` loads each generated schema from a live `FastMCP` instance and asserts the equivalences above against frozen v1 schema dicts checked in under `tests/fixtures/expected_schemas/`. The test must fail loudly on any rename, drop, or type change.
- US-M4/AC-4: Argument descriptions in the generated schema are taken from `Annotated[str, "..."]` or Google-style docstrings; missing descriptions cause a test failure.

Priority: P0 — schema drift is a client-breaking regression (C-2).
Dependencies: US-M3.
Open questions:
- OQ-6: Keep `server/schemas.py` as a frozen-fixture file for the parity test (US-M4/AC-3), or move it under `tests/fixtures/expected_schemas/`?
References: C-2; `src/cpp_mcp/server/schemas.py`; `[[pages/manuals/fastmcp/servers]]`.

---

### US-M5 — Preserve error envelope shape on every failure path

Story: As an LLM agent consuming cpp-mcp responses, I want all error responses to keep the exact envelope `{code, message, tool, request_id}` with the existing 8 error codes, so that no agent-side error-handling code breaks.

Acceptance criteria:
- US-M5/AC-1: The `core/error_envelope.wrap_tool` decorator is applied to every FastMCP-registered tool function. It runs before FastMCP serializes the return value, so the envelope shape ends up on the wire.
- US-M5/AC-2: For each error code (`FILE_NOT_FOUND`, `INVALID_POSITION`, `INVALID_RANGE`, `INVALID_ARGUMENT`, `PATH_VIOLATION`, `DB_UNREACHABLE`, `PARSE_ERROR`, `INTERNAL_ERROR`), an existing pytest case exercises the failure path and asserts the envelope shape; all such tests continue to pass.
- US-M5/AC-3: The `_sanitize_message` regex that redacts non-echoed absolute paths to `<redacted>` continues to run (no path leak in messages).
- US-M5/AC-4: FastMCP's `mask_error_details=True` is set on the FastMCP constructor as defense-in-depth, but the primary error path remains `wrap_tool` → structured envelope dict.
- US-M5/AC-5: The envelope is returned such that the MCP client sees it as the tool result payload. The exact wire mechanism (return dict as structured result, wrap in `ToolResult(structured_content={...})`, or custom exception middleware) is captured in an ADR — see OQ-2.

Priority: P0 — ADR-8 error envelope is the single biggest agent-side contract.
Dependencies: US-M3.
Open questions:
- OQ-2: Error envelope delivery: return the envelope dict as the tool's return value, wrap in `ToolResult(structured_content={...})`, or define custom middleware catching a `WrappedToolError` exception? Pick one, justify in an ADR.
References: C-4; ADR-8; `src/cpp_mcp/core/error_envelope.py`; `[[pages/manuals/fastmcp/servers]]`.

---

### US-M6 — Lifespan: libclang index + TU cache lifecycle

Story: As an operator, I want libclang's `Index` and the TU LRU cache to be created in a FastMCP `lifespan` async context manager, so that startup ordering is explicit and shutdown closes resources cleanly.

Acceptance criteria:
- US-M6/AC-1: A `@asynccontextmanager`-decorated `app_lifespan(server)` constructs `ClangSession(capacity=config.cache_capacity)` and yields it (or yields a dict `{"session": session}`) for tools to consume.
- US-M6/AC-2: On server shutdown, the lifespan exit path calls `session.close()` (new method if not present), which drains the `ThreadPoolExecutor` and clears the cache.
- US-M6/AC-3: Tool handlers access the session via `ctx.lifespan_context["session"]` or a `Depends(get_session)` resolver — not via module-level globals.
- US-M6/AC-4: The lifespan composes cleanly with the HTTP transport: starting `mcp.run(transport="http")` invokes the lifespan exactly once at process start.
- US-M6/AC-5: If `CPP_MCP_ALLOWED_ROOTS` is unset or `libclang` cannot be loaded, the lifespan raises `ConfigError`, which is caught at the `main()` boundary and exits 1 with a sanitized stderr message — current behavior preserved.

Priority: P0 — startup ordering and clean teardown are operational requirements.
Dependencies: US-M1.
Open questions: none (AC are self-contained; architect resolves session access pattern in OQ-3 above).
References: `[[pages/manuals/fastmcp/servers]]` (lifespan section); `src/cpp_mcp/server/stdio_transport.py`.

---

### US-M7 — Preserve libclang thread-affinity (ADR-2)

Story: As an operator, I want libclang access to remain serialized through a single worker thread, so that the non-reentrant `Index` cannot be hit concurrently by FastMCP's runtime.

Note: FastMCP supports sync `def` handlers. Sync handlers are the recommended pattern for this project — they read more naturally for libclang's blocking C API. The handler body still submits libclang work to `ClangSession.executor.submit(...).result()` to enforce the single-worker invariant (source: requirements-fastmcp-migration.md §4 US-M7 note).

Acceptance criteria:
- US-M7/AC-1: All libclang work (parse, cursor walks) runs inside the existing `ThreadPoolExecutor(max_workers=1)` owned by `ClangSession`. No FastMCP code path bypasses this executor.
- US-M7/AC-2: Tool handlers registered as sync `def` still dispatch libclang calls through `ClangSession.executor` rather than calling `clang.cindex` directly on FastMCP's worker thread — sync registration alone does not guarantee serialization across concurrent requests.
- US-M7/AC-3: A regression test launches N concurrent `tools/call` requests against the HTTP transport for `cpp_get_ast` on the same file and asserts: (a) all return correct results, (b) no `clang.cindex` exception, (c) parse count == 1 (cache hit on all but the first).
- US-M7/AC-4: The handler signature convention (sync `def` for all 7 tools, dispatching to `ClangSession.executor`) is documented in the ADR with rationale, replacing the existing `async def` handlers in `src/cpp_mcp/tools/*.py`.

Priority: P0 — correctness risk; libclang segfaults on concurrent access.
Dependencies: US-M3, US-M6.
Open questions:
- OQ-9: Architect to confirm sync `def` + `ClangSession.executor.submit(...).result()` pattern against R-3's regression suite and capture in ADR.
References: ADR-2; C-8; `src/cpp_mcp/core/clang_session.py`.

---

### US-M8 — Pin `fastmcp` version

Story: As a release manager, I want the `fastmcp` dependency exact-pinned or tilde-pinned to a minor, so that a routine `uv sync` cannot pull in a minor version that introduces a protocol-driven breaking change.

Acceptance criteria:
- US-M8/AC-1: `pyproject.toml` declares `fastmcp~=3.1.0` (or stricter `fastmcp==3.1.1`).
- US-M8/AC-2: `uv lock` is committed so CI runs against a deterministic version.
- US-M8/AC-3: A dependabot-style or manual upgrade check is documented in `runbook.md` for the next FastMCP release.

Priority: P1 — FastMCP semver explicitly allows protocol-driven breaking changes in minor versions.
Dependencies: none.
Open questions: none.
References: `[[pages/manuals/fastmcp/getting-started]]` (version-pin warning); `pyproject.toml`.

---

### US-M9 — Supersede ADR-10

Story: As a future reader of the design history, I want an ADR explicitly marking ADR-10 (Official MCP Python SDK) as superseded by the FastMCP decision, so that the design lineage is unambiguous.

Acceptance criteria:
- US-M9/AC-1: A new `adr-11.md` is created with `Status: accepted` and `Supersedes: ADR-10` (location in v1/ or v2/ to be decided by architect — see OQ-1).
- US-M9/AC-2: ADR-10's `Status:` line is updated to `superseded by ADR-11` in the v1 file. (Note: this touches a v1 file outside the v2 handoff dir — architect to confirm whether this is in scope per CHARTER handoff-rule.)
- US-M9/AC-3: The wiki page `[[pages/code/cpp-mcp]]` ADR table is updated to reflect the supersession.
- US-M9/AC-4: The ADR cites the FastMCP wiki pages used as evidence (`[[pages/manuals/fastmcp/getting-started]]`, `[[pages/manuals/fastmcp/servers]]`).

Priority: P0 — CHARTER hygiene; invariant I2 gates on no ADR remaining "proposed" at dev dispatch.
Dependencies: none.
Open questions:
- OQ-1: Where does ADR-11 live — `v1/adr-11.md` (continuing the series) or `v2/adr-1.md` (resetting per task)?
References: v1/adr-10.md; `[[pages/code/cpp-mcp]]`; `[[pages/manuals/fastmcp/getting-started]]`.

---

## Cross-cutting open questions (document level)

| OQ  | Question                                                                                                                     | Owned by  |
|-----|------------------------------------------------------------------------------------------------------------------------------|-----------|
| OQ-7 | Introduce FastMCP middleware (`LoggingMiddleware`, `TimingMiddleware`) for observability now, or defer to a v3 story?        | Architect |

---

## Risks (for architect reference)

| ID  | Risk                                                                                                                              | Mitigation                                                                                                 |
|-----|-----------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| R-1 | FastMCP minor-version breakage (minor versions may carry protocol-driven breaking changes).                                       | US-M8: pin `~=3.1.0`; commit `uv.lock`; gate upgrades behind manual checklist.                           |
| R-2 | Schema drift between FastMCP-generated `inputSchema` and hand-written `schemas.py` dicts.                                        | US-M4/AC-3: parity test against frozen v1 schemas; normalize before comparison.                           |
| R-3 | libclang concurrency: async runtime may concurrently invoke tool handlers if libclang is not funneled through executor.           | US-M7: keep single-worker executor; concurrent-request regression test.                                    |
| R-4 | Error envelope vs. FastMCP default `ToolError` shape mismatch.                                                                   | US-M5: keep `wrap_tool` outermost; return envelope as structured result; do not raise `ToolError`.        |
| R-5 | Sync vs. async handler signatures: all 7 current handlers are `async def`; recommended convention is sync `def` in v2.           | US-M7/AC-4: convert uniformly; concurrent-request regression test guards against accidental parallelism.  |
| R-6 | Console-script regression if entry-point signature changes.                                                                       | Keep `main()` callable at same module path; smoke-test installed `cpp-mcp` binary in CI.                 |
| R-7 | Schema descriptions lost if migration relies on bare type hints without docstrings.                                               | US-M4/AC-4: test fails if any description is empty.                                                       |
| R-8 | `fastmcp` runtime dependencies (Starlette, anyio, httpx) bloat install footprint.                                                | Audit `uv tree` after migration; document new minimum install footprint in `runbook.md`.                  |

---

## References

- `[[pages/code/cpp-mcp]]` — current architecture, ADR table, env-var list, tool inventory, 327/1 test baseline.
- `[[pages/manuals/fastmcp/getting-started]]` — installation, version-pin warning, minimal server.
- `[[pages/manuals/fastmcp/servers]]` — `FastMCP` constructor, tools decorator API, `ToolError`, lifespan, middleware, custom HTTP routes.
- `[[pages/manuals/fastmcp/cli]]` — CLI entry points.
- `[[pages/manuals/fastmcp/python-sdk-reference]]` — 241-file navigation index.
- Source file: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements-fastmcp-migration.md`
- v1 handoff: `~/workspace/cpp-mcp/.claude/handoff/v1/requirements.md` (US-1..US-14)
- v1 ADRs: `~/workspace/cpp-mcp/.claude/handoff/v1/adr-{1..10}.md`
- Cognee dataset: `agent-memory` (tags: `task:fastmcp-migration`, `role:product-manager`)
