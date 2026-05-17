# v4 Requirements — Real End-to-End Tests + v3 Post-Ship Bug Fixes

**Status:** approved
**Date:** 2026-05-17
**run_id:** cpp-mcp-v4
**Predecessor:** handoff/v3 (Neo4j + IndraDB backends shipped, never exercised end-to-end)

---

## Story US-V4-1 — In-memory FastMCP client harness

As a cpp-mcp maintainer, I want a pytest fixture that wraps the FastMCP server with `fastmcp.Client(server)` in-memory transport, so that every tool can be invoked through the real MCP request/response path without spawning a subprocess.

**Acceptance criteria:**
- AC-1-1: `conftest.py` in `tests/conftest.py` exposes a session-scoped fixture `mcp_client` that yields a connected `fastmcp.Client` bound to `build_server()`.
- AC-1-2: A smoke test calls `cpp_get_ast` via `client.call_tool("cpp_get_ast", ...)` against a fixture C++ file; the test asserts `result["cache_hit"] == False` on the first call and `result["cache_hit"] == True` on a second call with the same arguments.
- AC-1-3: Each of the seven exposed tools (`cpp_get_ast`, `cpp_get_definition`, `cpp_get_references`, `cpp_get_type_info`, `cpp_get_header_info`, `cpp_get_preprocessor_state`, `cpp_export_to_graphdb`) has at least one test that invokes it via `client.call_tool(...)` and asserts a non-error response.
- AC-1-4: All tests in this story live under `tests/integration/` and are decorated `@pytest.mark.integration`.
- AC-1-5: Running `uv run pytest` (without `-m integration`) skips all integration tests cleanly with zero failures.

**Priority:** P0 — structural prerequisite for all other v4 test stories.

**Dependencies:** none upstream; US-V4-2 depends on this story.

**Open questions:** none.

**References:**
- `[[project-fastmcp-migration]]` — supplies `build_server()` entry point
- `fastmcp.client.transports.memory.FastMCPTransport` — `Client(server_instance)` in-process transport

---

## Story US-V4-2 — Real IndraDB end-to-end test

As a cpp-mcp maintainer, I want an end-to-end test that exports `test-repo/fmt/src/os.cc` to a real IndraDB daemon via the in-memory FastMCP client, so that the regressions from 2026-05-17 cannot recur silently.

**Acceptance criteria:**
- AC-2-1: Test is marked `@pytest.mark.integration` and `@pytest.mark.indradb`; it is skipped when `INDRADB_TEST_URI` is unset.
- AC-2-2: A session-scoped fixture starts `~/.cargo/bin/indradb-server memory` on `127.0.0.1:27615` when `INDRADB_AUTOSTART=1`; otherwise the fixture assumes an already-running daemon and emits a `pytest.skip` if the daemon is unreachable.
- AC-2-3: After export, the test queries IndraDB directly and asserts vertex count equals `nodes_written` from the tool response and edge count equals `edges_written` from the tool response.
- AC-2-4: A second `cpp_export_to_graphdb` call with the same file produces `nodes_written == 0` and `edges_written == 0` (true idempotency — not trivially passing because the field was missing).
- AC-2-5: The test asserts exact vertex and edge counts pinned to values re-confirmed after US-V4-3 and US-V4-5 land; the specific numbers are recorded in `scenarios.md` by the QA engineer, not hardcoded in this requirements file.

**Priority:** P0 — primary regression guard for the 2026-05-17 defects.

**Dependencies:** US-V4-1 (harness), US-V4-3 (insert counts correct), US-V4-4 (protobuf pin), US-V4-5 (Identifier patch). This story's AC cannot pass until all four are resolved.

**Open questions:**
- OQ-2-1: Exact pinned vertex/edge counts for `os.cc` must be re-confirmed once US-V4-3 and US-V4-5 land; QA engineer records them in `scenarios.md`.

**References:**
- `[[project-graphdb-v3-post-ship-findings]]` — defects 3, 4, 5 (counts, idempotency)
- Live reproducer: `~/.cargo/bin/indradb-server memory > /tmp/indradb.log 2>&1 &`

---

## Story US-V4-3 — Fix `edges_written` and `nodes_written` to count inserts, not attempts

As a caller of `cpp_export_to_graphdb`, I want `nodes_written` and `edges_written` to reflect rows actually inserted, so that the metrics are usable for progress and idempotency reporting.

**Acceptance criteria:**
- AC-3-1: IndraDB driver tracks inserts separately from attempts; the tool response `nodes_written` and `edges_written` fields contain insert counts only (i.e. on re-export of an already-imported file both return 0).
- AC-3-2: Optionally, the driver may also expose `nodes_attempted` and `edges_attempted` as additional response fields; if exposed, they are documented in the tool's docstring.
- AC-3-3: The Neo4j driver is verified via code review (not a live test — no Neo4j daemon is assumed available) to use `MERGE`-affected-row counts rather than attempt counts; the reviewer records this finding in `logs/developer-us-v4-3.md`.
- AC-3-4: US-V4-2 idempotency assertion (AC-2-4) passes, confirming this fix is correct.

**Priority:** P0 — defect 4 from 2026-05-17; corrupts all export metrics.

**Dependencies:** US-V4-5 (driver must compile before counts can be tested).

**Open questions:**
- OQ-3-1: Is Neo4j MERGE-affected-rows verification a code-review check only, or does it require a live Neo4j daemon test? Section 4 Out-of-Scope defers live Neo4j tests; this AC resolves the conflict by making it code-review only — escalate if stakeholder disagrees.

**References:**
- `[[project-graphdb-v3-post-ship-findings]]` — defect 4
- `src/cpp_mcp/graphdb/indradb_driver.py`

---

## Story US-V4-4 — Pin `protobuf<4` in `graphdb-indradb` extra

As a user installing `cpp-mcp[graphdb-indradb]`, I want a working install on a clean venv, so that I don't hit `TypeError: Descriptors cannot be created directly` on first import.

**Acceptance criteria:**
- AC-4-1: `pyproject.toml` `[project.optional-dependencies].graphdb-indradb` contains `protobuf<4`.
- AC-4-2: A new test in `tests/integration/test_install.py` executes `import indradb` and `import cpp_mcp.graphdb.indradb_driver` and passes on a venv created with `uv sync --extra graphdb-indradb`.
- AC-4-3: The test is marked `@pytest.mark.integration` and passes in CI without a running daemon (import-only, no network call).

**Priority:** P0 — defect 1 from 2026-05-17; blocks all IndraDB usage on import.

**Dependencies:** none.

**Open questions:** none.

**References:**
- `[[project-graphdb-v3-post-ship-findings]]` — defect 1
- `pyproject.toml`

---

## Story US-V4-5 — Commit the `Identifier → str` driver patch and clean docstrings

As a maintainer, I want the uncommitted working-tree fix to `src/cpp_mcp/graphdb/indradb_driver.py` landed, so that the v3 ship is actually functional.

**Acceptance criteria:**
- AC-5-1: Lines 143 and 178 of `indradb_driver.py` (or their post-edit equivalents) use plain `str` labels for `Vertex(uuid, label)` and `Edge(t=...)` — the `indradb.Identifier(...)` call is absent.
- AC-5-2: Module docstring no longer references `Identifier(...)` on any line (lines 8 and 10 in the pre-patch file).
- AC-5-3: US-V4-2 passes end-to-end, confirming the patch is correct against a live daemon.

**Priority:** P0 — defect 2 from 2026-05-17; causes `AttributeError` on every export call.

**Dependencies:** US-V4-4 (protobuf pin needed for clean import to run tests).

**Open questions:** none.

**References:**
- `[[project-graphdb-v3-post-ship-findings]]` — defect 2
- `src/cpp_mcp/graphdb/indradb_driver.py` (working-tree patch is uncommitted as of 2026-05-17)

---

## Story US-V4-6 — Replace the broken Docker fixture with cargo-install instructions

As a developer setting up local IndraDB, I want working setup docs and fixtures, so that the 404-ing `docker pull indradb/indradb:5.0.0` image is no longer referenced anywhere in the repo.

**Acceptance criteria:**
- AC-6-1: `tests/fixtures/indradb-compose.yml` is either removed or replaced with a file using an image that resolves (not `indradb/indradb:5.0.0`); the decision is recorded in an ADR under `.claude/handoff/v4/`.
- AC-6-2: The README graphdb section includes a "Local development" subsection documenting `cargo install indradb` followed by `indradb-server memory` as the supported local-dev path.
- AC-6-3: `.claude/handoff/v3/runbook.md` references to the broken image are updated to reflect the cargo-install path.

**Priority:** P1 — defect 3 from 2026-05-17; blocks local dev setup but does not affect runtime correctness.

**Dependencies:** none.

**Open questions:**
- OQ-6-1: Should the Docker fixture be replaced with a self-built image pushed to the senussi registry, or removed entirely in favor of the cargo path? Architect records decision as an ADR; product-manager position is that cargo-only is simpler and reduces infra overhead, but final decision is an architecture call.

**References:**
- `[[project-graphdb-v3-post-ship-findings]]` — defect 3
- `tests/fixtures/indradb-compose.yml`
- `.claude/handoff/v3/runbook.md`

---

## Story US-V4-7 — README install fix for `graphdb` extras

As a new user, I want the README to spell out the `--extra graphdb-neo4j` / `--extra graphdb-indradb` flags, so that I don't hit `DEPENDENCY_MISSING` on the first export call.

**Acceptance criteria:**
- AC-7-1: README install section lists all three extras (`graphdb-neo4j`, `graphdb-indradb`, `graphdb`) with a concrete `uv sync --extra <name>` example for each.
- AC-7-2: The `DEPENDENCY_MISSING` error message returned by the tool contains the exact extra flag string (e.g. `--extra graphdb-indradb`) — either verified to already include it or updated to do so; the developer records the pre/post wording in `logs/developer-us-v4-7.md`.

**Priority:** P1 — developer ergonomics; no runtime impact.

**Dependencies:** none.

**Open questions:** none.

**References:**
- `README.md`
- `src/cpp_mcp/graphdb/` — DEPENDENCY_MISSING error construction

---

## Definition of Done

- `INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m integration` exits 0 with all seven stories' AC covered.
- `uv run pytest` (no env vars) exits 0 with all integration tests skipped cleanly.
- `[[project-graphdb-v3-post-ship-findings]]` memory updated: defects 1–5 closed, CI integration moved to a v5 open item.
- New ADR(s) for the IndraDB-Docker decision (US-V4-6) filed under `.claude/handoff/v4/`.

## Out of Scope

- Wiring the integration suite into GitLab CI (v5).
- Live Neo4j daemon tests beyond code-review verification of the MERGE path (no daemon available; see OQ-3-1).
- New backends (Memgraph, Kuzu, etc.).
