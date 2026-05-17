# v4 Requirements — Real End-to-End Tests + v3 Post-Ship Bug Fixes

**Status:** draft
**Date:** 2026-05-17
**Owner:** TBD
**Predecessor:** handoff/v3 (Neo4j + IndraDB backends shipped, never exercised end-to-end)

## 1. Problem Statement

The v3 release of `cpp_export_to_graphdb` (590 tests passing) **was never validated against a live IndraDB daemon before merge**. The first live run on 2026-05-17 against `test-repo/fmt/src/os.cc` surfaced five real defects (see [[project-graphdb-v3-post-ship-findings]]):

1. `indradb==3.0.1` is incompatible with `protobuf>=4` — import crash.
2. `indradb.Identifier(...)` does not exist in the Python 3.0.1 API — `AttributeError` in `indradb_driver.py:143,178`.
3. `indradb/indradb:5.0.0` Docker image does not exist on Docker Hub — `tests/fixtures/indradb-compose.yml` is broken.
4. `edges_written` metric returns *attempt* count, not *insert* count (23169 reported vs 180 actual).
5. `test_export_to_indradb.py` idempotency assertion is trivially `0 == 0` because the tool response lacked a `nodes_written` field.

Root cause across all five: **BDD tests are env-gated (`INDRADB_TEST_URI`), CI has no daemon, and no test exercises the FastMCP → driver → daemon → C++ parse path end-to-end against real services.** A working tree patch exists for (2) but is uncommitted.

## 2. Goal

Add a real end-to-end test layer that exercises **FastMCP tools through the in-memory `Client(server)` transport against real backends (libclang, IndraDB daemon, optionally Neo4j daemon) on a real C++ project** — and fix the five v3 defects so the new tests pass.

Non-goals: full CI integration (deferred to v5), production deployment changes, schema changes.

## 3. User Stories

### US-V4-1 — In-memory FastMCP client harness
**As a** cpp-mcp maintainer
**I want** a pytest fixture that wraps the FastMCP server with `fastmcp.Client(server)` in-memory transport
**So that** every tool can be invoked through the real MCP request/response path without spawning a subprocess.

**Acceptance criteria**
- Fixture `mcp_client` in `tests/conftest.py` yields a connected `Client` bound to `build_server()`.
- One smoke test calls `cpp_get_ast` via `client.call_tool(...)` against a fixture C++ file and asserts `cache_hit` toggles on second call.
- All seven exposed tools (`cpp_get_ast`, `cpp_get_definition`, `cpp_get_references`, `cpp_get_type_info`, `cpp_get_header_info`, `cpp_get_preprocessor_state`, `cpp_export_to_graphdb`) have at least one in-memory client invocation test.
- Tests live under `tests/integration/` and are marked `@pytest.mark.integration`.

### US-V4-2 — Real IndraDB end-to-end test
**As a** cpp-mcp maintainer
**I want** an end-to-end test that exports `test-repo/fmt/src/os.cc` to a real IndraDB daemon via the in-memory FastMCP client
**So that** the regressions from 2026-05-17 cannot recur silently.

**Acceptance criteria**
- Test marked `@pytest.mark.integration` and `@pytest.mark.indradb`, skipped unless `INDRADB_TEST_URI` is set.
- Test starts (or assumes) `indradb-server memory` on `127.0.0.1:27615` — provide a session-scoped fixture that launches `~/.cargo/bin/indradb-server memory` if `INDRADB_AUTOSTART=1`, otherwise relies on an externally-running daemon.
- After export, the test queries IndraDB directly and asserts:
  - vertex count equals `nodes_written` from the tool response,
  - edge count equals `edges_written` from the tool response,
  - a second export call produces `nodes_written == 0` and `edges_written == 0` (true idempotency).
- Test asserts the exact vertex/edge counts for `os.cc` are pinned (e.g. `99 vertices`, `180 edges` — to be re-confirmed once the bug fixes land).

### US-V4-3 — Fix `edges_written` and `nodes_written` to count inserts, not attempts
**As a** caller of `cpp_export_to_graphdb`
**I want** `nodes_written` and `edges_written` to reflect rows actually inserted
**So that** the metrics are usable for progress/idempotency reporting.

**Acceptance criteria**
- IndraDB driver tracks inserts separately from attempts; the tool response includes `nodes_written` and `edges_written` (inserts only). Optionally expose `nodes_attempted` / `edges_attempted` as new fields.
- Neo4j driver path verified to behave the same — `MERGE` returns affected rows; use that, do not double-count.
- US-V4-2 idempotency assertion passes against both backends.

### US-V4-4 — Pin `protobuf<4` in `graphdb-indradb` extra
**As a** user installing `cpp-mcp[graphdb-indradb]`
**I want** a working install on a clean venv
**So that** I don't hit `TypeError: Descriptors cannot be created directly` on first import.

**Acceptance criteria**
- `pyproject.toml` `[project.optional-dependencies].graphdb-indradb` pins `protobuf<4`.
- A new smoke test in `tests/integration/test_install.py` imports `indradb` and `cpp_mcp.graphdb.indradb_driver` and passes on a fresh `uv sync --extra graphdb-indradb`.

### US-V4-5 — Commit the `Identifier → str` driver patch and clean docstrings
**As a** maintainer
**I want** the uncommitted working-tree fix to `src/cpp_mcp/graphdb/indradb_driver.py` landed
**So that** the v3 ship is actually functional.

**Acceptance criteria**
- `indradb_driver.py:143,178` use `str` labels for `Vertex(uuid, label)` and `Edge(t=...)` — matching `indradb==3.0.1` API.
- Module docstring lines 8 and 10 no longer reference `Identifier(...)`.
- US-V4-2 passes (proves the patch is correct).

### US-V4-6 — Replace the broken Docker fixture with cargo-install instructions
**As a** developer setting up local IndraDB
**I want** working setup docs and fixtures
**So that** `docker pull indradb/indradb:5.0.0` (which 404s) is no longer referenced.

**Acceptance criteria**
- `tests/fixtures/indradb-compose.yml` removed OR replaced with a working image (e.g. self-built and pushed to senussi registry — decision recorded in an ADR).
- README graphdb section documents `cargo install indradb` → `indradb-server memory` as the supported local-dev path.
- `.claude/handoff/v3/runbook.md` references updated to match.

### US-V4-7 — README install fix for default graphdb extras
**As a** new user
**I want** the README to spell out the `--extra graphdb-neo4j` / `--extra graphdb-indradb` flags
**So that** I don't get `DEPENDENCY_MISSING` on the first export call.

**Acceptance criteria**
- README install section lists the three extras (`graphdb-neo4j`, `graphdb-indradb`, `graphdb`) with example `uv sync` commands.
- Error message returned by `DEPENDENCY_MISSING` cites the exact extra to install (already partially done in v3; verify wording).

## 4. Out of Scope

- Wiring the integration suite into GitLab CI (separate v5 story — needs a daemon-in-CI strategy).
- Neo4j-specific live tests beyond a single happy-path export (no Neo4j daemon was running on 2026-05-17; assume it works but verify via the same harness once a daemon is available).
- New backends (Memgraph, Kuzu, etc.) — out of scope per v3 ADRs.

## 5. Definition of Done

- All seven acceptance criteria sections pass on a clean venv with `INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m integration`.
- Default `uv run pytest` (no env vars) still passes — integration tests skip cleanly without daemons.
- `project_graphdb_v3_post_ship_findings.md` memory updated to reflect items 1–6 closed; one open follow-up (CI integration) moved to a new v5 memory.
- New ADR(s) for the IndraDB-Docker decision (US-V4-6) filed under `.claude/handoff/v4/`.

## 6. References

- [[project-graphdb-v3-post-ship-findings]] — the bug list and reproducer details.
- [[project-graphdb-multi]] — v3 ship record.
- [[project-fastmcp-migration]] — v2 architecture; supplies `build_server()` entry point.
- FastMCP in-memory transport: `fastmcp.client.transports.memory.FastMCPTransport` — `Client(server_instance)` connects directly to the server in-process; no subprocess, no network.
- Live reproducer: `~/.cargo/bin/indradb-server memory > /tmp/indradb.log 2>&1 &` then export `test-repo/fmt/src/os.cc` with `db_uri="indradb://localhost:27615"`.
