# v6 Requirements — Graph Query Surface (`query_graphdb` + `describe_graph_schema`)

**Status:** ready-for-architect
**Date:** 2026-05-17
**run_id:** cpp-mcp-v6
**Predecessor:** handoff/v5 (rename release, commit `bb98c28`, pushed to `github.com/husams/cpp-mcp`, v0.3.0)
**Plan reference:** `[[pages/planning/cpp-mcp-codexgraph-gap]]` — S1 + adjacent schema-discovery work
**Target version:** `0.3.0` → `0.4.0` (additive surface; no rename, no breaking change)

---

## Context

Through v5 the server exposes seven tools: six **read** tools that consult clang
in the moment (`get_ast`, `get_definition`, `get_references`, `get_type_info`,
`get_header_info`, `get_preprocessor_state`) and one **write** tool
(`ingest_code`) that exports a project into a graph database (Neo4j or IndraDB).

The graph is currently **write-only from the MCP surface** — `ingest_code`
populates 99 vertices / 180 edges for `{fmt}/src/os.cc`, but **no MCP tool reads
the graph back**. Agents that want to use the graph today must drop out of the
MCP transport and talk to Neo4j/IndraDB directly, which defeats the point of
exposing the server. This is the largest functional gap identified in
`[[pages/planning/cpp-mcp-codexgraph-gap]]` (table row "Query-side tool": **Blocker**).

v6 closes that gap with two new MCP tools:

| New tool | Purpose |
|---|---|
| `query_graphdb` | Execute a read-only graph query against the active backend and return rows + stats. |
| `describe_graph_schema` | Return the live schema (node types, edge types, properties, counts) so the agent can plan queries without prior knowledge of the model. |

**Why two tools, not one.** Agents using a code graph for the first time don't
know the schema. CodexGraph addresses this by embedding the schema in the
translator's few-shot prompt; we expose it as a first-class MCP call so any
agent (not just one with our prompt) can self-discover. Without
`describe_graph_schema`, `query_graphdb` is only usable by agents that already
have hardcoded knowledge of the node/edge taxonomy.

**Additive, non-breaking.** No existing tool is renamed, removed, or has its
schema changed. The version bump is a minor (`0.4.0`) because the surface grows.
The rename-invariant test from v5 still applies — new tool names MUST be
unprefixed (`query_graphdb`, `describe_graph_schema`).

---

## Story US-V6-Q1 — `query_graphdb` MCP tool

As an MCP-client agent investigating a C++ codebase, I want to execute
read-only graph queries against the active backend through a single MCP tool,
so that I can answer structural questions (e.g. "which functions call
`vformat`?") without bypassing the MCP transport.

**Acceptance criteria:**

- AC-Q1-1: A new tool `query_graphdb` is registered in `src/cpp_mcp/tools/query_graphdb.py` with parameters:
  - `db_uri: str` (required) — `bolt://...` for Neo4j, `grpc://...` for IndraDB. Same scheme dispatch already used by `ingest_code`.
  - `query: str` (required) — query body. Cypher when `db_uri` is Neo4j; IndraDB property-query JSON (see AC-Q1-5) when `db_uri` is IndraDB.
  - `parameters: dict[str, Any] | None = None` — bound parameters for parameterized Cypher; ignored for IndraDB.
  - `row_limit: int = 200` — hard upper cap of 500 enforced server-side; the tool may shrink but never exceed.
- AC-Q1-2: Result shape is `{"rows": [...], "stats": {"backend": "neo4j" | "indradb", "ms": int, "rows_returned": int, "truncated": bool}, "request_id": str}`. Rows are JSON-serializable (Neo4j Node/Relationship coerced to dicts with `_labels`/`_type` keys; IndraDB Vertex/Edge coerced to dicts with `id`, `t`, and `properties`).
- AC-Q1-3: **Read-only enforcement (Neo4j).** Queries are validated by parsing the Cypher AST, not by string regex. Allowlist of clause types: `MATCH`, `OPTIONAL MATCH`, `WITH`, `RETURN`, `WHERE`, `UNWIND`, `ORDER BY`, `SKIP`, `LIMIT`, `CALL { ... }` (subquery form, read-only inner). Rejected verbs include but are not limited to `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, and any `CALL <procedure>` outside the read-only allowlist (notably anything `apoc.*` that mutates). Rejection emits `READ_ONLY_VIOLATION` error envelope (see AC-Q1-7).
- AC-Q1-4: **Read-only enforcement (IndraDB).** The IndraDB backend only ever calls `client.get(...)` and never `set_vertices` / `set_edges` / `delete`. This is enforced at the driver layer (the query executor has no write methods imported) and verified by a test that imports the executor module and asserts no symbol named `set_` or `delete` is present.
- AC-Q1-5: **IndraDB query language.** Queries against IndraDB use a JSON shape mirroring the official `indradb` Python `Query` builders: `{"query": "all_vertices" | "all_edges" | "vertex_with_type" | "edge_with_type" | "vertex_with_property_equal" | "edge_with_property_equal" | "pipe", "args": {...}}`. The exact subset and JSON schema is finalized in `design.md` by the architect; minimum must cover (a) "all vertices of type X", (b) "all edges of type Y", (c) "vertices where property name == X", (d) one-hop traversal (`pipe` outbound/inbound). Anything outside this subset returns `QUERY_UNSUPPORTED`.
- AC-Q1-6: **Result cap.** When the underlying query would return more than `row_limit` rows, the tool returns the first `row_limit` rows, sets `stats.truncated = true`, and does NOT raise. The agent is expected to refine the query.
- AC-Q1-7: **Error envelope.** All failures (`CONNECTION_FAILED`, `QUERY_PARSE_ERROR`, `READ_ONLY_VIOLATION`, `QUERY_UNSUPPORTED`, `QUERY_TIMEOUT`, `DEPENDENCY_MISSING`) use the existing `core/error_envelope.py` machinery; each error code is documented in the tool's docstring with one-line semantics.
- AC-Q1-8: **Timeout.** Default 30s per query, configurable via `CPP_MCP_QUERY_TIMEOUT_SECONDS` env var, clamped to `[1, 120]`. Exceeding the timeout returns `QUERY_TIMEOUT`.
- AC-Q1-9: **Tool registration smoke test.** `tests/unit/test_tool_registration.py` is updated to expect **9** registered tools (was 7) and asserts neither new name carries the `cpp_` prefix.
- AC-Q1-10: **Rename-invariant guard.** `tests/unit/test_rename_invariant.py` (added in v5) continues to pass — verifies no `cpp_*` tool name in the registry.

**Priority:** P0 — primary v6 deliverable; blocks all other CodexGraph-gap stories.

**Dependencies:** none upstream. US-V6-Q2 depends on the schema-discovery mechanism this story introduces (live introspection of the backend).

**Open questions:**

- OQ-Q1-1: Cypher AST parser library — `pycypher` is the obvious candidate but unmaintained. Architect must decide between (a) adding a maintained dependency, (b) wrapping Neo4j's own `EXPLAIN <query>` and inspecting the plan for write operators, or (c) implementing a minimal recursive-descent parser scoped to the allowlist. Recommend (b) — uses the server's own parser, no extra dep, and `EXPLAIN` is a read-only operation itself.
- OQ-Q1-2: When `db_uri` is IndraDB and the agent sends a Cypher-shaped string by mistake, do we attempt translation or return `QUERY_PARSE_ERROR` immediately? Recommend the latter for v6; translation belongs in S2 `translate_query` (future handoff).

**References:**

- `[[pages/planning/cpp-mcp-codexgraph-gap]]` § "S1 — `query_graphdb` MCP tool"
- `src/cpp_mcp/graphdb/indradb_driver.py`, `src/cpp_mcp/graphdb/neo4j_driver.py`
- v3 ADRs `adr-12`..`adr-15` (URI-scheme dispatch — reuse the same pattern)

---

## Story US-V6-Q2 — `describe_graph_schema` MCP tool

As an MCP-client agent that has never seen this graph before, I want to ask
the server what node and edge types exist (with property names and rough counts),
so that I can compose meaningful `query_graphdb` calls without hardcoded schema
knowledge.

**Acceptance criteria:**

- AC-Q2-1: A new tool `describe_graph_schema` is registered in `src/cpp_mcp/tools/describe_graph_schema.py` with parameters:
  - `db_uri: str` (required) — same dispatch as `ingest_code` and `query_graphdb`.
  - `sample_size: int = 100` — number of vertices per type sampled to enumerate property keys; clamped to `[10, 1000]`.
- AC-Q2-2: Result shape:
  ```json
  {
    "backend": "neo4j" | "indradb",
    "schema_version": "v1",
    "node_types": [
      {"name": "Function", "count": 21, "property_keys": ["name", "usr", "file", "line", "is_definition"], "sample_ids": ["..."]}
    ],
    "edge_types": [
      {"name": "DEFINES", "count": 98, "property_keys": []}
    ],
    "totals": {"vertices": 99, "edges": 180},
    "notes": [
      "Property keys are inferred from a sample of up to <sample_size> vertices per type; rare keys may be missing.",
      "Counts are live as of the call; the graph may change between this call and a follow-up query_graphdb call."
    ],
    "request_id": "..."
  }
  ```
- AC-Q2-3: **Neo4j implementation.** Uses `CALL db.labels()`, `CALL db.relationshipTypes()`, and parameterized `MATCH (n:<label>) RETURN keys(n) LIMIT <sample_size>` per type. No `apoc.*` dependency.
- AC-Q2-4: **IndraDB implementation.** Iterates `AllVertexQuery` and `AllEdgeQuery` to build a histogram of `t` (vertex/edge type), and for each type samples up to `sample_size` items via `properties()` to enumerate keys. Result is bounded by the schema's type cardinality (currently 6 vertex types, 2 edge types — trivially small).
- AC-Q2-5: **Stable ordering.** `node_types` and `edge_types` are sorted by `count` descending, then by `name` ascending, so deterministic for agent prompts.
- AC-Q2-6: **No leak of secrets.** `db_uri` is never echoed back in the response; if credentials are embedded in the URI, the response's `backend` field is the only identifier surfaced.
- AC-Q2-7: **Empty-graph case.** Calling against a brand-new database returns `node_types: []`, `edge_types: []`, `totals: {vertices: 0, edges: 0}` with no error.
- AC-Q2-8: **Tool registration smoke test.** Same `tests/unit/test_tool_registration.py` update from AC-Q1-9 covers this tool (count = 9).

**Priority:** P0 — without this, `query_graphdb` is only usable by agents with pre-baked schema knowledge.

**Dependencies:** none upstream. Best implemented in parallel with US-V6-Q1; the two tools share the URI-dispatch + driver layer.

**Open questions:**

- OQ-Q2-1: Should the schema include the indexing version (e.g. `ingest_code`'s schema-version constant from `[[project-graphdb-multi]]`) so an agent can detect that a graph was ingested under an older schema? Recommend yes — add `schema_version` from the writer constant and surface it in `notes` if it doesn't match the current code.

**References:**

- `[[pages/planning/cpp-mcp-codexgraph-gap]]` § "Side-by-side" (node/edge type tables)
- `src/cpp_mcp/graphdb/` (writer's schema-version constants)

---

## Story US-V6-Q3 — Integration tests against real graph (Neo4j + IndraDB)

As a v6 maintainer, I want both new tools exercised end-to-end against a real
backend, so that the same class of regressions caught in v3 (false-positive unit
tests on a write tool that didn't actually work) cannot recur on the read surface.

**Acceptance criteria:**

- AC-Q3-1: New file `tests/integration/test_query_graphdb_e2e.py`, marked `@pytest.mark.integration` and `@pytest.mark.indradb`, that:
  1. Reuses the existing `INDRADB_AUTOSTART=1` daemon fixture from v4.
  2. Calls `ingest_code` on `test-repo/fmt/src/os.cc` to populate the graph (99 vertices / 180 edges, pinned from v4).
  3. Calls `query_graphdb` with `{"query": "vertex_with_type", "args": {"t": "Function"}}` and asserts exactly **21** Function vertices (matches the live-verification breakdown from 2026-05-17).
  4. Calls `query_graphdb` with `{"query": "all_edges"}` and asserts `stats.rows_returned == 180`.
  5. Calls `query_graphdb` with `{"query": "all_vertices"}` and `row_limit=50`, asserts `stats.truncated == true` and `len(rows) == 50`.
- AC-Q3-2: New file `tests/integration/test_describe_graph_schema_e2e.py`, same markers, that:
  1. Calls `describe_graph_schema` against the same populated database.
  2. Asserts the result lists exactly six vertex types (`Variable`, `TypeAlias`, `Function`, `Class`, `Namespace`, `File`) and two edge types (`DEFINES`, `REFERENCES`) — pinned counts from 2026-05-17 live run (33/28/21/13/3/1 and 98/82).
  3. Asserts `totals.vertices == 99` and `totals.edges == 180`.
  4. Asserts each vertex type's `property_keys` is non-empty and includes `name` (where applicable per writer schema).
- AC-Q3-3: Neo4j integration test is **optional** — code-review only unless a local Neo4j daemon is available; the AC-Q1-3 read-only allowlist is verified by unit tests against a mock driver.
- AC-Q3-4: Both new integration tests pass with `INDRADB_AUTOSTART=1 uv run pytest -m integration` in under 60s combined.

**Priority:** P0 — gate for the v6 release.

**Dependencies:** US-V6-Q1, US-V6-Q2.

**Open questions:** none.

**References:**

- `tests/integration/test_indradb_e2e.py` (existing v4 fixture pattern)
- `[[project-v4-live-verification]]` (pinned counts source)

---

## Story US-V6-Q4 — Docs, ADRs, version bump

As a downstream user, I want clear documentation of the new query surface and
its safety boundaries, so that I can safely give my agent access to the tools.

**Acceptance criteria:**

- AC-Q4-1: `README.md` gains a "Query surface" section documenting both tools, the IndraDB JSON query shape, the Cypher allowlist (link to ADR), and an end-to-end agent example (`describe_graph_schema` → reason about schema → `query_graphdb`).
- AC-Q4-2: New ADR `adr-22.md` — "Cypher read-only enforcement strategy" — records the decision from OQ-Q1-1 (likely `EXPLAIN`-based) with a Status of "accepted".
- AC-Q4-3: New ADR `adr-23.md` — "IndraDB query JSON schema" — pins the subset of `indradb.Query` exposed and the rationale for that subset.
- AC-Q4-4: New ADR `adr-24.md` — "Schema-discovery tool: live vs cached" — records why introspection is live each call (acceptable cost; freshness wins over caching at this scale).
- AC-Q4-5: `CHANGELOG.md` gains a `0.4.0` section listing both new tools and noting "additive surface; no breaking changes to existing tools".
- AC-Q4-6: `pyproject.toml` version bumped `0.3.0` → `0.4.0`.
- AC-Q4-7: Wiki page `~/workspace/wiki/pages/code/cpp-mcp-v6.md` created (sibling of `cpp-mcp-v5.md`) summarizing the new surface and linking back to `[[pages/planning/cpp-mcp-codexgraph-gap]]`; `cpp-mcp-codexgraph-gap.md` updated to mark S1 as "shipped in v6" and reference the new page.
- AC-Q4-8: README "Migration" table from v5 is untouched (no rename); a new short note records that v6 is additive.

**Priority:** P1 — required for release but not a code blocker.

**Dependencies:** US-V6-Q1, US-V6-Q2, US-V6-Q3.

**Open questions:** none.

**References:**

- `README.md` (current structure post-v5)
- `~/workspace/wiki/pages/code/cpp-mcp-v5.md`
- `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md`

---

## Out of scope (intentionally)

- **`translate_query` (S2 of the gap roadmap).** Natural-language → query translation is a separate handoff (v7). v6 deliberately ships only the execution + introspection surface, so agents that already know Cypher or our IndraDB JSON can use it immediately.
- **`access_kind` edge sub-types (S3), FIELD/GLOBAL_VARIABLE split (S4), dangling-edge fix (S5), C++ benchmark (S6).** All deferred to later handoffs. They change the *content* of the graph; v6 only changes the *surface* used to read it.
- **Neo4j live integration test.** Deferred to a future handoff once a CI Neo4j daemon is wired up; v6 ships with mock-driver unit tests for the Neo4j path and IndraDB live tests as the regression guard.
- **PyPI publish of 0.4.0.** Tagging and publishing remain manual; deploy-notes will document the `uv build` + `git tag v0.4.0` + `gh release create` sequence.
- **Authentication on `query_graphdb`.** No per-call auth; the security boundary is the database URI (the client controls who can connect). Read-only enforcement is the only server-side guard.

---

## Cross-story invariants

- I-V6-1: No existing tool's name or schema is modified. Only additions.
- I-V6-2: Both new tools follow the v5 rename rule — unprefixed names, no `cpp_*`.
- I-V6-3: Both new tools reuse the URI-scheme dispatch from `ingest_code`; no new dispatch mechanism is introduced.
- I-V6-4: All test counts (99 vertices / 180 edges; 21 Function vertices; etc.) trace back to the 2026-05-17 live verification run pinned in `[[project-v4-live-verification]]` and `[[project-v5-status-and-next]]`. If the writer's schema changes in a future handoff, these counts will need re-pinning.

---

## Traceability

| Story | AC IDs | Driving doc |
|---|---|---|
| US-V6-Q1 | AC-Q1-1..AC-Q1-10 | gap roadmap S1 |
| US-V6-Q2 | AC-Q2-1..AC-Q2-8 | gap roadmap "Query-side tool" gap + agent self-discovery rationale |
| US-V6-Q3 | AC-Q3-1..AC-Q3-4 | v4 regression-guard precedent |
| US-V6-Q4 | AC-Q4-1..AC-Q4-8 | release hygiene |

---

## References (consolidated)

- `[[pages/planning/cpp-mcp-codexgraph-gap]]` — roadmap source
- `[[pages/code/cpp-mcp-v5.md]]` — predecessor release
- `[[project-v4-live-verification]]` — pinned graph counts
- `[[project-v5-status-and-next]]` — current project status
- `.claude/handoff/v5/CHARTER.md` — handoff structure template
- `.claude/handoff/v4/requirements.md` — story/AC formatting template
