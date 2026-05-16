# ADR-12: URI-scheme-based driver dispatch for `cpp_export_to_graphdb`
Status: accepted
Date: 2026-05-16
Run: graphdb-multi-v3

## Context

The `cpp_export_to_graphdb` tool currently instantiates `Neo4jDriver()`
directly (see `src/cpp_mcp/tools/export_to_graphdb.py:85`). v3 introduces a
second backend (`IndraDBDriver`) and we want the existing `db_uri: str`
argument to choose between them — no new tool arguments, no environment
variables (constraint C-G1, C-G4 in `requirements.md`).

Forces:
- ADR-7 defined `GraphDriver` Protocol with multiple-impl in mind.
- C-G5 requires `neo4j` and `indradb` to remain **optional** extras — the
  dispatcher must not import them at module load.
- C-G6 requires `DEPENDENCY_MISSING` to fire *before* any I/O attempt.
- The current helper `graphdb.__init__.make_driver(uri, **kwargs)` connects
  inline and raises `ValueError` on unknown schemes; `ValueError` is not in
  `_EXC_TO_CODE`, so it would surface as `INTERNAL_ERROR` instead of
  `INVALID_ARGUMENT`.

## Decision

Replace `make_driver` with a pure dispatch function `select_driver(db_uri:
str) -> GraphDriver` in `src/cpp_mcp/graphdb/__init__.py`:

- Returns an **unconnected** driver instance.
- Scheme → class mapping (frozensets):
  - `{bolt, bolt+s, bolt+ssc, neo4j, neo4j+s, neo4j+ssc}` → `Neo4jDriver`
  - `{indradb, grpc, indradb+grpc}` → `IndraDBDriver`
- Unknown / empty / missing-`://` → `InvalidArgumentError` (maps to
  `INVALID_ARGUMENT` via existing `_EXC_TO_CODE`). Message lists supported
  schemes.
- No imports of `neo4j` / `indradb` happen here. Each driver's `connect()`
  does the lazy import and raises `DependencyMissingError` (adr-13) if the
  package is absent.

The caller (`_do_export_to_graphdb`) becomes:

```python
driver = select_driver(db_uri)
try:
    driver.connect(db_uri)
except (DependencyMissingError, DBUnreachableError):
    raise
```

`select_driver` does **not** include `cognee://` because v3 stories scope
dispatch to Neo4j + IndraDB. `CogneeDriver` remains importable for any
external/test caller but is not wired into the export-tool path. Adding
cognee back is a future ADR.

OQ resolutions recorded here:
- **OQ-G1**: `IndraDBDriver` is sync-only for v3. Async deferred. Rationale:
  Protocol is sync (ADR-7), `session.executor` already serialises blocking
  work, no caller currently needs async.
- **OQ-G3**: Lazy `import` lives inside each driver's `connect()`, not in
  `select_driver`. Mirrors the existing Neo4j pattern at
  `src/cpp_mcp/graphdb/neo4j_driver.py:50`.

## Alternatives considered

1. **Single Bolt adapter with two URI variants** — rejected. IndraDB does not
   speak Bolt; it speaks gRPC with a different protobuf surface. A single
   adapter cannot bridge these without re-implementing IndraDB on top of
   Bolt, which would require running Neo4j to talk to IndraDB. No viable
   integration path.

2. **Add `backend: str` argument to the tool** — rejected. Violates C-G1
   (tool schema must remain unchanged). Also redundant: `db_uri` already
   carries enough information in its scheme.

3. **Environment variable `CPP_MCP_GRAPHDB_BACKEND`** — rejected. Violates
   C-G4 ("driver selection happens before any I/O; URI scheme drives the
   choice. No environment variable changes the dispatch.") Operationally
   worse: split-brain when the env var disagrees with the URI scheme.

4. **Embedded backend (Kuzu, CozoDB, SurrealDB-embedded, DuckPGQ)** —
   rejected. None provide multi-process writers + active maintenance +
   commercial-friendly license + property-graph in 2026. Documented in
   `requirements.md` § Out of scope.

5. **Memgraph / FalkorDB** — rejected. Memgraph BSL and FalkorDB SSPL are
   commercial-use risks. If demand emerges they extend the Neo4j adapter
   (same Bolt protocol) and do not need a separate driver class — out of
   scope for v3.

6. **Keep `make_driver` (current name) and add IndraDB to it** — rejected.
   `make_driver` connects inline and raises `ValueError`; refactoring its
   error mapping is a larger blast radius than introducing `select_driver`
   and removing `make_driver`. No external caller depends on `make_driver`
   (verified by grep in repo). Removing it also simplifies the
   "scheme→class, then call connect" two-step that scenarios "INVALID_ARGUMENT
   fires before PATH_VIOLATION/FILE_NOT_FOUND" require.

## Consequences

Positive:
- One pure function owns the scheme→class mapping; trivially unit-tested.
- Default install (no extras) still imports the module without dragging
  `neo4j` or `indradb` in (C-G5).
- Error ordering preserved: INVALID_ARGUMENT (unknown scheme) → PATH_VIOLATION
  → FILE_NOT_FOUND → DEPENDENCY_MISSING / DB_UNREACHABLE.
- `wrap_tool` envelope mapping needs no change for unknown-scheme; it
  already maps `InvalidArgumentError` → `INVALID_ARGUMENT`.

Negative / follow-ups:
- `make_driver` is removed. Anyone (tests, scripts) that imported it must
  switch to `select_driver` + explicit `connect`. Grep verifies no current
  in-repo use, but external consumers of the package would break — accepted
  given v3 is a minor version bump and the function was internal.
- Cognee driver no longer reachable via `cpp_export_to_graphdb`. Recorded
  here as a known scope choice; future ADR can re-introduce it if needed.

## References

- `requirements.md` US-G3 (AC-1..AC-5).
- `scenarios.md` Feature "URI-scheme-based driver dispatch".
- `src/cpp_mcp/graphdb/__init__.py` (current `make_driver`).
- `src/cpp_mcp/graphdb/driver.py` (Protocol).
- `src/cpp_mcp/tools/export_to_graphdb.py:85` (dispatch site).
- IndraDB Python client v3.x: `indradb>=3.0,<4` on PyPI (MPL-2.0).
- adr-13 (DEPENDENCY_MISSING), adr-14 (USR→UUID), adr-15 (prop serialization).
