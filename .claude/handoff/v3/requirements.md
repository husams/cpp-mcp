---
run_id: graphdb-multi-v3
stage: product-manager
date: 2026-05-16
status: final
predecessor: v2/requirements.md (FastMCP migration — closed 2026-05-16, 472 tests passing)
---

# Requirements: Pluggable GraphDB Backends (v3)

## Background

`cpp_export_to_graphdb` currently writes only to Neo4j (Bolt). The user wants a second backend, **IndraDB** (MPL-2.0, actively maintained — `indradb==3.0.1` on PyPI, Rust core v5.0.0 released 2025-08-16), to be supported as a peer of Neo4j for commercial use.

Both backends share these properties:
- **Persistent on disk** (Neo4j page-cache + store files; IndraDB via RocksDB-backed daemon).
- **Multi-process clients** (Neo4j over Bolt; IndraDB over gRPC).
- **Daemon-based** — neither runs embedded in the cpp-mcp process.
- **Commercially usable** — Neo4j Community (GPLv3, separate-daemon avoids viral linking); IndraDB (MPL-2.0, no relicensing trigger when consumed as a library).

The existing `GraphDriver` Protocol (`src/cpp_mcp/graphdb/driver.py`, ADR-7) already permits multiple implementations. This feature realizes that affordance.

## AC format note

Acceptance criteria are testable prose with story-scoped IDs (`US-G<n>/AC-<m>`). BA stage may rewrite into Given/When/Then.

---

## Compatibility Constraints (HARD gate conditions)

| ID   | Constraint | Verification |
|------|------------|--------------|
| C-G1 | `cpp_export_to_graphdb` tool name, argument names, types, and required/optional status unchanged. `db_uri: str` still the only target identifier. | `tools/list` JSON unchanged; schema-parity test (`tests/unit/test_schema_parity.py`) passes. |
| C-G2 | Existing Neo4j export behavior — node labels, edge types, USR-based MERGE idempotency, error envelope — unchanged when `db_uri` starts with `bolt://` or `neo4j://`. | All current Neo4j tests pass (`tests/bdd/test_export_to_graphdb.py`, `tests/unit/test_graphdb_exporter.py`); no new skips. |
| C-G3 | The error envelope shape `{code, message, tool, request_id}` is preserved; existing 8 error codes remain. New error codes (if any) are additive. | Envelope tests (`tests/unit/test_envelope_codes.py`) pass; any new code documented in ADR-2 amendment or new ADR. |
| C-G4 | Driver selection happens before any I/O; URI scheme drives the choice. No environment variable changes the dispatch. | Unit test `test_driver_dispatch.py` asserts scheme → driver class mapping. |
| C-G5 | All graphdb dependencies remain **optional extras** in `pyproject.toml`. Default install must not pull in `neo4j` or `indradb`. | `uv sync` (no extras) yields neither package; `uv sync --extra graphdb-neo4j` adds neo4j only; `uv sync --extra graphdb-indradb` adds indradb only. |
| C-G6 | When a backend driver package is missing, the tool returns a clear, actionable error envelope **before** attempting to connect. | New unit test asserts envelope `code=DEPENDENCY_MISSING` and message contains the install command. |
| C-G7 | Existing 472 pytest cases continue to pass. 1 skipped (Neo4j) remains skipped unless `NEO4J_TEST_URI` set. A second skip is permitted for IndraDB, gated on `INDRADB_TEST_URI`. | `uv run pytest -q` reports `>=472 passed, <=2 skipped`. |
| C-G8 | The `ClangSession` executor model (ADR-2) is preserved: driver I/O runs on the worker thread. | `clang_session.py` unchanged; export call site still uses `session.executor.submit(...)`. |

---

## Stories

---

### US-G1 — Introduce a new error code `DEPENDENCY_MISSING`

Story: As an operator who selects a backend whose Python driver is not installed, I want a precise error envelope that tells me which extra to install, so that I do not misread it as a database-unreachable failure.

Acceptance criteria:
- US-G1/AC-1: A new error class `DependencyMissingError` is added to `core/error_envelope.py`, mapping to code `DEPENDENCY_MISSING`.
- US-G1/AC-2: The envelope wire shape is unchanged: `{code: "DEPENDENCY_MISSING", message: str, tool: str, request_id: str}`. The message includes the exact install command (e.g. `pip install "cpp-mcp[graphdb-indradb]"`).
- US-G1/AC-3: The existing miswired path that currently returns `DB_UNREACHABLE` when the neo4j Python driver is absent is corrected to return `DEPENDENCY_MISSING`.
- US-G1/AC-4: An ADR (logical ADR-2 amendment, file `adr-13.md`) is filed documenting the new code; the error-codes table in the runbook is updated.

Priority: P0 — blocks the multi-backend dispatch.
Dependencies: none.
Open questions: none.
References: ADR-2 (error envelope), `tools/export_to_graphdb.py:DB_UNREACHABLE`, observed misclassification during fmt test run on 2026-05-16.

---

### US-G2 — Add `IndraDBDriver` implementing the `GraphDriver` Protocol

Story: As an exporter, I want a concrete IndraDB driver that satisfies the existing `GraphDriver` Protocol, so that the exporter loop does not need to know which backend it is talking to.

Acceptance criteria:
- US-G2/AC-1: New module `src/cpp_mcp/graphdb/indradb_driver.py` defines `IndraDBDriver` with the four Protocol methods: `connect`, `upsert_nodes`, `upsert_edges`, `close`.
- US-G2/AC-2: `connect(uri, **kwargs)` parses the URI (`indradb://host:port`, `grpc://host:port`, or `indradb+grpc://host:port`) and opens a gRPC channel using the `indradb` Python package; on failure, raises `DBUnreachableError` with the original exception chained.
- US-G2/AC-3: The same USR string produces the same vertex identifier across independent runs (deterministic mapping); the mechanism for this determinism is left to the architect.
- US-G2/AC-4: `upsert_nodes(batch)` is idempotent: re-running the export on the same translation unit produces the same vertex count in the database.
- US-G2/AC-5: `upsert_edges(batch)` is idempotent: re-running the export on the same translation unit does not create duplicate edges.
- US-G2/AC-6: Node label is preserved on round-trip (readable back from the database after export); node `props` are stored as vertex properties; edge `edge_type` is stored as edge type. The specific storage fields are left to the architect.
- US-G2/AC-7: `close()` releases the gRPC channel; calling `close()` twice is safe (idempotent).
- US-G2/AC-8: When the `indradb` package is not importable, `connect()` raises `DependencyMissingError` (per US-G1), not `DBUnreachableError`.

Priority: P0 — core feature.
Dependencies: US-G1.
Open questions:
- OQ-G1: Should `IndraDBDriver` expose a sync API only, or also an async path for future use? Current Protocol is sync (matches Neo4jDriver); recommend sync-only for v3, async deferred. Defer to architect.
- OQ-G2: How to handle property types IndraDB does not natively support (e.g. nested dicts in `props`)? Recommend JSON-serializing such fields with a logged warning; document in implementation notes. Defer to architect.
References: `src/cpp_mcp/graphdb/driver.py` (Protocol), `src/cpp_mcp/graphdb/neo4j_driver.py` (reference impl), `indradb-client` PyPI v3.0.1.

---

### US-G3 — URI-scheme-based driver dispatch in `cpp_export_to_graphdb`

Story: As a tool caller, I want the existing `db_uri` argument to drive backend selection so that I do not need a new argument or env var to choose between Neo4j and IndraDB.

Acceptance criteria:
- US-G3/AC-1: A new function `select_driver(db_uri: str) -> GraphDriver` in `src/cpp_mcp/graphdb/__init__.py` returns:
  - `Neo4jDriver()` for schemes `bolt`, `bolt+s`, `bolt+ssc`, `neo4j`, `neo4j+s`, `neo4j+ssc`.
  - `IndraDBDriver()` for schemes `indradb`, `grpc`, `indradb+grpc`.
- US-G3/AC-2: An unknown or missing scheme raises `InvalidArgumentError` with the message listing supported schemes.
- US-G3/AC-3: `cpp_export_to_graphdb._do_export_to_graphdb` is refactored to call `select_driver(db_uri)` instead of directly instantiating `Neo4jDriver`; no other behavior changes.
- US-G3/AC-4: Path-validation order (INVALID_ARGUMENT → PATH_VIOLATION → FILE_NOT_FOUND → DB_UNREACHABLE / DEPENDENCY_MISSING) is preserved; dependency-missing fires at `connect()` time, after path checks.
- US-G3/AC-5: An ADR (`adr-12.md`) documents the dispatch design and records alternatives considered as rejected: single Bolt adapter with two URI variants; embedded backends; Memgraph in-memory.

Priority: P0 — wires US-G2 into the tool.
Dependencies: US-G1, US-G2.
Open questions: none.
References: `src/cpp_mcp/tools/export_to_graphdb.py:85`, ADR-7.

---

### US-G4 — Optional dependency packaging and dual extras

Story: As an integrator installing cpp-mcp, I want to install only the graph backend I plan to use, so that I do not pull in both `neo4j` and `indradb` (and their transitive `grpcio` / `protobuf`) unnecessarily.

Acceptance criteria:
- US-G4/AC-1: `pyproject.toml` `[project.optional-dependencies]` exposes:
  - `graphdb-neo4j = ["neo4j>=5,<6"]`
  - `graphdb-indradb = ["indradb>=3.0,<4"]`
  - `graphdb = ["cpp-mcp[graphdb-neo4j]", "cpp-mcp[graphdb-indradb]"]` (meta-extra for "install both").
- US-G4/AC-2: A unit test (`tests/unit/test_pyproject_extras.py`) parses `pyproject.toml` and asserts the three extras exist with the expected version pins.
- US-G4/AC-3: The runbook lists install commands for each backend and a sample `db_uri` per backend.
- US-G4/AC-4: `uv sync` (no extras) does **not** install neo4j or indradb; verified by `uv pip list | grep -E 'neo4j|indradb'` returning empty.

Priority: P1 — packaging hygiene.
Dependencies: none.
Open questions: none.
References: existing `pyproject.toml` extras section.

---

### US-G5 — IndraDB BDD coverage with the export tool

Story: As QA, I want a BDD scenario that exports a small C++ file to a real IndraDB daemon and verifies the resulting graph, so that we catch regressions in the IndraDB path the way we already do for Neo4j.

Acceptance criteria:
- US-G5/AC-1: A new feature file `tests/bdd/features/export_to_indradb.feature` covers: connect, single-file export, idempotent re-export (same count after second run), and unreachable-daemon error path.
- US-G5/AC-2: Tests are skipped unless `INDRADB_TEST_URI` is set (mirror of the existing Neo4j skip).
- US-G5/AC-3: A `docker compose` fragment under `tests/fixtures/indradb-compose.yml` brings up `indradb-server` with the RocksDB backend for local runs; CI integration is out of scope for v3.
- US-G5/AC-4: A unit test exercises the URI-dispatch table for all advertised schemes without requiring a live daemon (uses a fake driver).
- US-G5/AC-5: Path validation, error envelope, and idempotency assertions match those of `test_export_to_graphdb.py`.

Priority: P1.
Dependencies: US-G2, US-G3.
Open questions: none.
References: `tests/bdd/test_export_to_graphdb.py`, `tests/bdd/features/`.

---

### US-G6 — Documentation update

Story: As an operator, I want the README and runbook to describe both backends, the URI schemes, the install commands, and the license posture, so that I can pick a backend without reading the ADRs.

Acceptance criteria:
- US-G6/AC-1: `README.md` adds a "Graph database backends" section listing Neo4j (default) and IndraDB (alternative), with one-line summaries.
- US-G6/AC-2: `.claude/handoff/v3/runbook.md` documents: URI scheme → driver mapping table; daemon install / docker command for each backend; error-code reference including `DEPENDENCY_MISSING`; license posture (GPLv3 for Neo4j Community via separate daemon; MPL-2.0 for IndraDB).
- US-G6/AC-3: Wiki page `~/workspace/wiki/pages/code/cpp-mcp.md` (confirmed to exist) is updated to add the IndraDB backend to the architecture summary.

Priority: P2.
Dependencies: US-G1..US-G5 complete.
Open questions: none.
References: existing `README.md`, `.claude/handoff/v2/runbook.md`, `~/workspace/wiki/pages/code/cpp-mcp.md`.

---

## Out of scope (v3)

- Embedded graph backends (Kuzu, CozoDB, SurrealDB embedded, DuckPGQ) — none provide multi-process writers + active maintenance + commercial-friendly license + property-graph in 2026. Tracked in ADR-12 as "considered and rejected".
- Memgraph and FalkorDB — Bolt-compatible alternatives would extend the Neo4j adapter only; deferred until concrete demand. License caveats (BSL for Memgraph, SSPL for FalkorDB) make them risky in a commercial context.
- Migration tooling between Neo4j and IndraDB — out of scope; users export fresh per backend.
- Auth on the graph DB connection — deferred to a future story; today both backends are reached over trusted local networks.
- Performance benchmarking between backends — not in v3 acceptance criteria.

---

## Open questions (cross-cutting)

- OQ-G3: Should we emit a deprecation log when neither extra is installed, or only when the user actually invokes `cpp_export_to_graphdb`? Recommend the latter (lazy import inside `select_driver`). Defer to architect.
- OQ-G4: Should `DependencyMissingError` be classified as a user error (4xx-equivalent) or a setup error in metrics? Defer to architect.
- OQ-G5: Daemon health-check before export — for both backends — would catch "daemon up but DB not ready" cases. Useful but out of v3 scope.

---

## References

- `src/cpp_mcp/graphdb/driver.py` — `GraphDriver` Protocol (ADR-7).
- `src/cpp_mcp/graphdb/neo4j_driver.py` — reference adapter.
- `src/cpp_mcp/tools/export_to_graphdb.py` — dispatch site.
- IndraDB PyPI: `indradb==3.0.1`, requires `grpcio>=1.26.0`, `protobuf>=3.11.2`.
- IndraDB license: MPL-2.0.
- Neo4j Community license: GPLv3 (separate daemon, no linking of cpp-mcp code).
- Observed defect on 2026-05-16: `cpp_export_to_graphdb` returned `DB_UNREACHABLE` when the `neo4j` Python driver was missing. Misclassification — should be `DEPENDENCY_MISSING`. Closed by US-G1/AC-3.
