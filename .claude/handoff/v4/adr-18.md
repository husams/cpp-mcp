# ADR-18: Integration-test harness uses `fastmcp.Client(server)` in-process transport

Status: accepted
Date: 2026-05-17
Bound stories: US-V4-1, US-V4-2, US-V4-7 (DEPENDENCY_MISSING test)
Related: ADR-3 (FastMCP framework adoption)

## Context

v4 needs a test fixture that drives every MCP tool through the real request/response pipeline (schema marshalling, error envelopes, lifespan setup) without spawning a subprocess. v3 tests bypass the MCP layer entirely and call tool functions directly — that is why defects 1, 2, 4, 5 of `[[project-graphdb-v3-post-ship-findings]]` slipped through.

FastMCP 3.x exposes three transport modes for `fastmcp.Client`:

1. **Stdio subprocess** (`Client("path/to/script.py")`) — spawns a subprocess; slow; introduces process-level state we don't want in unit-adjacent tests.
2. **HTTP transport** (`Client("http://host:port/mcp")`) — needs a running server; circular dependency for tests.
3. **In-process transport** (`Client(server_instance)`) — wires the client directly into the server's request handler in the same event loop. No subprocess, no socket.

Forces:

- Tests must exercise the real MCP envelope, not the underlying Python functions.
- Tests must be fast (~ms per call); a subprocess per test would make a 7-tool smoke take seconds.
- `build_server()` already exists as the canonical entry point (`src/cpp_mcp/server/app.py:60`).
- The project already uses `pytest-asyncio` with `asyncio_mode = "auto"` (pyproject.toml:56).
- AC-1-5 forbids integration tests from running on bare `uv run pytest` — markers must gate them.

> **v5 note:** the `cpp_export_to_graphdb` tool referenced in tests bound to this ADR was renamed
> to `ingest_code` in v5. The in-process harness decision is unaffected by the rename.

## Decision

1. **Transport:** `fastmcp.Client(build_server())` — in-process, same event loop.

2. **Fixture scope:** `session`. The `mcp_client` fixture is constructed once per pytest session and shared across all integration tests. Rationale: `build_server()` is cheap, but the ClangSession it lifespan-instantiates is heavy (libclang + cache state); sharing across tests matches production behaviour where the server runs continuously. Per-test reset is handled separately by the `fresh_indradb` fixture for the IndraDB story.

3. **Fixture location:** `tests/conftest.py` (root-level, so any test under `tests/` can request it). Integration-only fixtures (`indradb_uri`, `indradb_daemon`) live in `tests/integration/conftest.py`.

4. **Marker discipline:**
   - Register `integration` in `[tool.pytest.ini_options].markers`.
   - Set `addopts = "-ra -m 'not integration'"` so `uv run pytest` deselects them by default. Override with `uv run pytest -m integration`.
   - The existing `indradb` marker remains; integration-indradb tests carry both.

5. **`protobuf<4` pin** lives in this ADR by association: it is the operational guard that makes `import indradb` work in any environment the harness loads. Pinned in `[project.optional-dependencies].graphdb-indradb`.

## Alternatives considered

a. **Direct in-Python tool function calls** (the v3 status quo).
   Rejected: bypasses the MCP envelope; cannot detect serialization bugs, schema-validation failures, or `DEPENDENCY_MISSING` envelope wording. Allowed the v3 ship defects.

b. **Spawn `cpp-mcp` console script via subprocess and speak JSON-RPC over stdio.**
   Rejected: 10–50× slower per test (process spawn + handshake), introduces flakiness on slow CI hosts, complicates teardown. The existing `SC_C10_ENTRY` test in `tests/bdd/` already covers the "the console script actually frames JSON" concern.

c. **HTTP transport with a daemon-style fixture.**
   Rejected: needs a port allocator, server-ready probe, and teardown signal. All friction with no value over in-process for tests that aren't exercising the HTTP transport itself. `SC_USM2_1` / `SC_USM2_4` already cover HTTP at the framework level.

d. **Function-scope `mcp_client` fixture** (fresh server per test).
   Rejected: ~100 ms per test for ClangSession lifespan setup; no test in the v4 scope mutates server-level state in a way that requires isolation. The cache-hit test (SC-V4-1-02) explicitly *requires* shared state across two calls.

## Consequences

Positive:

- Tests exercise the same path that production clients (Claude Code, etc.) use.
- ~ms per call; full integration suite runs in <10 s when no daemon-gated tests are active.
- One canonical fixture (`mcp_client`) for all seven tool stories.
- ClangSession is shared across tests, matching production behaviour and exposing leakage bugs (file handles, cache invalidation) that a per-test fresh server would hide.

Negative:

- Session-scoped state means test ordering can mask bugs. Mitigation: the IndraDB e2e test uses per-test `fresh_indradb` to wipe daemon state; other tools are read-only.
- A fixture failure during `build_server()` blocks the entire integration session. Acceptable: that failure is the actual signal we want (server doesn't build).
- The `protobuf<4` pin is one more constraint that may collide with a future dep. Tracked in ADR review for v5.

Follow-ups:

- If a future story needs an isolated server (e.g. tools that mutate file system state non-atomically), introduce a function-scoped `mcp_client_isolated` fixture; do **not** change the default `mcp_client` scope.
- v5: consider adding an HTTP-transport variant of the harness once a v5 story needs to test the HTTP envelope end-to-end.

## References

- `[[project-fastmcp-migration]]` — v2 ship of `build_server()`
- `[[project-graphdb-v3-post-ship-findings]]` — defects 1, 2, 4, 5 slipped because no MCP-envelope test existed
- `src/cpp_mcp/server/app.py:60` — `build_server()`
- FastMCP docs: in-memory `Client(server_instance)` transport (`fastmcp~=3.1.0`)
- requirements.md US-V4-1, AC-1-1..AC-1-5
- scenarios.md SC-V4-1-01..SC-V4-1-04
- ADR-3 (FastMCP framework adoption, v2)

---

## Addendum (v4 post-ship, 2026-05-17)

`asyncio_default_test_loop_scope = "session"` is now set project-wide in
`pyproject.toml` under `[tool.pytest.ini_options]` (landed in S5).  This
applies the session event loop to every async test in the project by default.

**Implication for future test authors:** any async test that requires
per-function isolation (e.g. it mutates module-level async state or sets up a
fixture that must not bleed into sibling tests) MUST decorate the test
explicitly:

```python
@pytest.mark.asyncio(loop_scope="function")
async def test_needs_fresh_loop() -> None:
    ...
```

Do not change the project-wide default to achieve per-test isolation for a
single test — that would degrade performance for the whole suite.  Use the
per-test decorator instead.

Status remains **accepted**.
