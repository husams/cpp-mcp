# Design — v6 Graph Query Surface (`query_graphdb` + `describe_graph_schema`)

**Status:** ready-for-senior-developer
**Date:** 2026-05-17
**run_id:** cpp-mcp-v6
**Upstream:** `requirements.md`, `scenarios.md`
**Companion ADRs:** `adr-22.md` (Cypher read-only enforcement), `adr-23.md` (IndraDB JSON query schema), `adr-24.md` (live-vs-cached schema discovery)
**Target version:** `0.3.0` → `0.4.0` (additive)

---

## 1. Goals / non-goals

**Goals.** Add two MCP tools (`query_graphdb`, `describe_graph_schema`) that let an
agent read the property graph populated by `ingest_code`, against either Neo4j
or IndraDB, without ever mutating it. Reuse the v3 URI-scheme dispatch and
ADR-8 error envelope verbatim.

**Non-goals.** No NL→query translation (S2, future v7), no schema/access-kind
edge changes (S3–S5), no Neo4j live integration test (mock-driver unit tests
only), no per-call auth (URI is the trust boundary).

---

## 2. Module layout

New files (Python; lazy imports for optional deps; type-annotated; pass `ruff` +
`mypy --strict` per `python-conventions`):

```
src/cpp_mcp/graphdb/
  query_executor.py            # ABC + 2 impls; entry point for both tools
  neo4j_query_executor.py      # Cypher exec + EXPLAIN-based read-only guard
  indradb_query_executor.py    # JSON-shaped read-only query subset
  schema_introspector.py       # describe-schema impl per backend
  schema_version.py            # SCHEMA_VERSION = "v1" constant (ADR-24)

src/cpp_mcp/tools/
  query_graphdb.py             # MCP tool: validate → dispatch → executor
  describe_graph_schema.py     # MCP tool: validate → dispatch → introspector

tests/unit/graphdb/
  test_neo4j_read_only.py      # EXPLAIN-plan inspection allowlist
  test_indradb_query_subset.py # JSON shape parser + dispatch
  test_query_executor_purity.py # AC-Q1-4 module-symbol-name guard
  test_schema_introspector.py  # ordering, clamps, empty-graph
tests/unit/tools/
  test_query_graphdb.py        # error envelope mapping, row_limit clamp
  test_describe_graph_schema.py
tests/integration/
  test_query_graphdb_e2e.py        # IndraDB live (US-V6-Q3)
  test_describe_graph_schema_e2e.py
```

**Why a new `query_executor.py` instead of extending `GraphDriver`.** The
`GraphDriver` Protocol (driver.py) is intentionally write-only: `connect`,
`upsert_nodes`, `upsert_edges`, `close`. Adding read methods would force every
driver to grow a (largely backend-specific) read surface and would silently
extend the existing public protocol. We introduce a parallel protocol
`QueryExecutor` so the read and write surfaces evolve independently and the
AC-Q1-4 purity check ("executor module imports no write symbols") remains a
1-line module-namespace assertion.

---

## 3. Public protocols

### 3.1 `QueryExecutor` (graphdb/query_executor.py)

```python
class QueryExecutor(Protocol):
    backend: str  # "neo4j" | "indradb"

    def connect(self, uri: str, **kwargs: Any) -> None: ...
    def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None,
        row_limit: int,
        timeout_s: int,
    ) -> QueryResult: ...
    def close(self) -> None: ...

class QueryResult(TypedDict):
    rows: list[dict[str, Any]]
    rows_returned: int
    truncated: bool
    ms: int
```

`select_executor(db_uri: str) -> QueryExecutor` mirrors `select_driver`:
pure scheme dispatch, no lazy imports at module load. Same scheme frozensets
as `graphdb/__init__.py` so Neo4j (`bolt`, `neo4j`, `+s`, `+ssc` variants) and
IndraDB (`indradb`, `grpc`, `indradb+grpc`) work identically.

### 3.2 `SchemaIntrospector` (graphdb/schema_introspector.py)

```python
class SchemaIntrospector(Protocol):
    backend: str
    def connect(self, uri: str, **kwargs: Any) -> None: ...
    def describe(self, sample_size: int) -> SchemaDescription: ...
    def close(self) -> None: ...
```

Returns the exact dict shape from AC-Q2-2 (see §6.2).

---

## 4. Tool surface (MCP signatures)

### 4.1 `query_graphdb`

```python
@mcp.tool(name="query_graphdb", description="Execute a read-only graph query.")
@wrap_tool("query_graphdb")
def query_graphdb_tool(
    db_uri: Annotated[str, "Backend URI: bolt://... or indradb://..."],
    query: Annotated[str, "Cypher (Neo4j) or IndraDB JSON query shape"],
    parameters: Annotated[dict[str, Any] | None, "Bound params (Cypher only)"] = None,
    row_limit: Annotated[int, "Max rows (clamped to [1, 500])"] = 200,
) -> dict[str, Any]: ...
```

Result on success:
```json
{
  "rows": [...],
  "stats": {"backend": "neo4j"|"indradb", "ms": 17, "rows_returned": 21, "truncated": false},
  "request_id": "<uuid4-hex>"
}
```

### 4.2 `describe_graph_schema`

```python
@mcp.tool(name="describe_graph_schema", description="Discover node/edge types live.")
@wrap_tool("describe_graph_schema")
def describe_graph_schema_tool(
    db_uri: Annotated[str, "Backend URI"],
    sample_size: Annotated[int, "Per-type vertex sample for property key inference; clamped [10, 1000]"] = 100,
) -> dict[str, Any]: ...
```

---

## 5. Validation / dispatch order (mirrors `ingest_code`)

For both tools, in this order; first failure short-circuits to the envelope.

1. `INVALID_ARGUMENT`  — empty/missing `db_uri` or `query`; `row_limit` non-positive (clamped to `max(1, ...)`, capped to 500); `sample_size` clamped to `[10, 1000]`.
2. `INVALID_ARGUMENT`  — unknown URI scheme (raised by `select_executor` / `select_introspector`).
3. `DEPENDENCY_MISSING` — backend driver package not importable (caught from executor `connect`).
4. `CONNECTION_FAILED` / `DB_UNREACHABLE` — backend reachable check fails. **Wire-code reuse:** the existing `DB_UNREACHABLE` ErrorCode is reused; per AC-Q1-7 the docstring documents it under the alias `CONNECTION_FAILED` (semantic equivalence). No new ErrorCode is added to keep the enum closed per ADR-8.
5. `READ_ONLY_VIOLATION` (Neo4j) — see ADR-22.
6. `QUERY_PARSE_ERROR` — Cypher syntax error (caught from Neo4j `EXPLAIN`); IndraDB JSON parse failure; or **Cypher string sent to IndraDB URI** (OQ-Q1-2 confirm: no translation in v6 — early-reject as `QUERY_PARSE_ERROR` when the IndraDB executor cannot `json.loads(query)`).
7. `QUERY_UNSUPPORTED` — IndraDB JSON `query` field is not in the allowlisted subset (ADR-23).
8. `QUERY_TIMEOUT` — execution exceeds resolved timeout (see §7).
9. Success → coerce rows → enforce `row_limit` → return.

**New ErrorCodes added to `core/error_envelope.py`:** `READ_ONLY_VIOLATION`,
`QUERY_PARSE_ERROR`, `QUERY_UNSUPPORTED`, `QUERY_TIMEOUT`. Each gets a domain
exception class and an entry in `_EXC_TO_CODE`. This is the only change to the
shared error module; existing tools are untouched.

---

## 6. Result coercion

### 6.1 `query_graphdb` rows

- **Neo4j.** `neo4j.graph.Node` → `{"_labels": list[str], **dict(node)}`. `neo4j.graph.Relationship` → `{"_type": str, "_start": str, "_end": str, **dict(rel)}`. `neo4j.graph.Path` → `{"_nodes": [...], "_rels": [...]}`. Scalars + lists/maps pass through `json.loads(json.dumps(v, default=str))` to guarantee JSON-serializability.
- **IndraDB.** `Vertex` → `{"id": str(uuid), "t": str, "properties": dict}`. `Edge` → `{"outbound_id": ..., "inbound_id": ..., "t": ..., "properties": dict}`. Properties are fetched per-result-set via `client.get_properties(...)` in **one batch per result page** (avoid N+1 round-trips); pre-AC-Q1-6 truncation, only the first `row_limit` items have properties fetched.

### 6.2 `describe_graph_schema` result

Exact shape from AC-Q2-2. Implementation notes:

- **Neo4j.** `CALL db.labels()` → list of labels; for each, `MATCH (n:`<label>`) RETURN count(n) AS c, collect(distinct keys(n))[..$sample] AS sample` parameterized. `CALL db.relationshipTypes()` → list; for each, `MATCH ()-[r:`<type>`]->() RETURN count(r), collect(distinct keys(r))[..$sample]`. **No `apoc.*`** (AC-Q2-3). Label/type names are interpolated with backtick-escaping (validated against `^[A-Za-z_][A-Za-z0-9_]*$` before interpolation; reject otherwise) since Cypher does not parameterize labels.
- **IndraDB.** Iterate `AllVertexQuery`/`AllEdgeQuery`, group by `t`, sample up to `sample_size` per type, call `get_properties` to enumerate keys. Card is small (current live run: 6 vertex types, 2 edge types).
- **Ordering** (AC-Q2-5): `sorted(types, key=lambda t: (-t["count"], t["name"]))`.
- **`db_uri` non-echo** (AC-Q2-6): result dict never contains the URI; only the resolved `backend` string. The error envelope's `echo` machinery in `wrap_tool` echoes any string that starts with `/` — DB URIs start with their scheme (`bolt:`, `indradb:`), so they will not be echoed by the existing sanitizer; no extra work needed. We do NOT add the URI to `echo` in the tool entry point.
- **Schema-version note** (OQ-Q2-1, resolved by ADR-24): `notes` always contains the static disclaimer strings from AC-Q2-2; **plus** if a sampled `File` node's `schema_version` property exists and differs from `schema_version.SCHEMA_VERSION`, append `"Graph ingested under schema_version=<x>; current code is <y>; counts and property keys may differ."`. The writer is amended in this handoff to stamp `schema_version = SCHEMA_VERSION` on every `File` node (small, additive; tracked in plan.md).

---

## 7. Timeout resolution

`core/config.py` (or a small `core/query_config.py` helper) exposes:

```python
def resolve_query_timeout_s() -> int:
    raw = os.environ.get("CPP_MCP_QUERY_TIMEOUT_SECONDS", "30")
    try:
        v = int(raw)
    except ValueError:
        v = 30
    return max(1, min(120, v))
```

- **Neo4j.** Passed via `session.run(..., timeout=timeout_s)` (driver-level Bolt server-side timeout). On timeout the driver raises `neo4j.exceptions.ClientError` with code `Neo.ClientError.Transaction.TransactionTimedOut`; mapped to `QUERY_TIMEOUT`.
- **IndraDB.** No native per-call timeout in the Python client (verified against `indradb>=3,<4`). Wrap execution in `concurrent.futures.ThreadPoolExecutor.submit(...).result(timeout=timeout_s)`; on `TimeoutError`, raise `QueryTimeoutError`. The executor thread is the same single-worker pattern used by `clang_session.executor` — reuse `session.executor` rather than allocating a new pool.

---

## 8. Read-only enforcement (summary; full rationale in ADR-22)

- **Neo4j.** `EXPLAIN <query>` is executed first (`EXPLAIN` itself is a read-only operation — it returns a plan without execution). Inspect `ResultSummary.plan` recursively; the set of allowed operator names is an allowlist derived from the read-only Cypher fragment (no `Create*`, `Merge*`, `Delete*`, `SetProperty*`, `RemoveLabels*`, `LoadCsv*`, no `ProcedureCall` outside a small allowlist of `db.*` read-only procs). Any disallowed operator → `READ_ONLY_VIOLATION`. **No external dependency added.**
- **IndraDB.** Driver layer never imports or calls `set_*` / `delete_*` methods. The `indradb_query_executor` module is statically verified by AC-Q1-4: a unit test imports the module, walks its namespace, and asserts no symbol name starts with `set_` or `delete_`. The module imports only `Client.get`, `get_properties`, and the `Query` constructors needed by the allowlisted JSON shapes.

---

## 9. IndraDB JSON query shape (summary; full grammar in ADR-23)

Allowlisted `query` strings (case-sensitive):

| `query` | required `args` | maps to |
|---|---|---|
| `all_vertices` | `{}` | `AllVertexQuery()` |
| `all_edges` | `{}` | `AllEdgeQuery()` |
| `vertex_with_type` | `{"t": str}` | `VertexWithTypeQuery(t)` |
| `edge_with_type` | `{"t": str}` | `EdgeWithTypeQuery(t)` |
| `vertex_with_property_equal` | `{"name": str, "value": JSON-scalar}` | `VertexWithPropertyValueQuery(name, value)` |
| `edge_with_property_equal` | `{"name": str, "value": JSON-scalar}` | `EdgeWithPropertyValueQuery(name, value)` |
| `pipe` | `{"direction": "outbound"|"inbound", "vertex_id": uuid-str, "t": str?}` | `SpecificVertexQuery(uuid) >> PipeQuery(direction[, t])` |

Anything else → `QUERY_UNSUPPORTED`. Missing/extra `args` keys → `QUERY_PARSE_ERROR`.
Class names above use the IndraDB Python client v3.x surface; the executor
imports them lazily inside `connect()` mirroring the driver pattern.

---

## 10. Test architecture (informs senior-dev plan)

- **Unit (no live backend):**
  - `test_neo4j_read_only.py`: mock `session.run` to return a fabricated `ResultSummary.plan` per test case; assert allow vs reject for the AC-Q1-3 scenario matrix (MATCH/OPTIONAL MATCH/WITH/... allow; CREATE/MERGE/DELETE/SET/REMOVE/DROP/LOAD CSV/`apoc.create.node` reject; nested `CALL { ... CREATE ... }` reject; nested `CALL { ... MATCH ... }` allow).
  - `test_indradb_query_subset.py`: parametrize over the 7 allowed shapes + 3 unsupported shapes + 2 malformed-JSON cases.
  - `test_query_executor_purity.py`: `import cpp_mcp.graphdb.indradb_query_executor as m; assert not any(n.startswith(("set_", "delete")) for n in dir(m))`.
  - `test_query_graphdb.py`: validate envelope on every error code, `row_limit` clamp, default 200, hard cap 500, truncation flag, `request_id` shape.
  - `test_describe_graph_schema.py`: ordering, clamps, empty-graph, credential non-echo, schema-version-mismatch note.
  - `test_tool_registration.py` (existing) updated to expect **9** tools; rename-invariant test (existing v5 `test_rename_invariant.py`) continues to pass.
- **Integration (IndraDB live, `@pytest.mark.integration`, `@pytest.mark.indradb`):**
  - Reuses `INDRADB_AUTOSTART=1` fixture from v4.
  - Sequence: `ingest_code` on `test-repo/fmt/src/os.cc` → assertions per AC-Q3-1, AC-Q3-2 (21 Function vertices, 180 edges, truncation at 50, 6 vertex types incl. property `name`).
- **Neo4j integration**: deferred (AC-Q3-3). Mock-driver coverage only.

---

## 11. Dependencies

- **No new runtime dependencies.** Cypher read-only is verified by Neo4j's own `EXPLAIN` (which the project's existing `neo4j` extra already provides). IndraDB JSON shape is parsed with stdlib `json`.
- **No new test dependencies.** Existing `pytest`, `pytest-asyncio`, IndraDB fixture from v4.

---

## 12. Cross-story traceability

| Story | AC | Code surface |
|---|---|---|
| US-V6-Q1 | AC-Q1-1..2 | `tools/query_graphdb.py` + `QueryExecutor.execute` shape |
| US-V6-Q1 | AC-Q1-3 | `neo4j_query_executor.py` `_enforce_read_only` (EXPLAIN + plan walk) — ADR-22 |
| US-V6-Q1 | AC-Q1-4 | `indradb_query_executor.py` module purity + `test_query_executor_purity.py` |
| US-V6-Q1 | AC-Q1-5 | `indradb_query_executor.py` `_dispatch_query` — ADR-23 |
| US-V6-Q1 | AC-Q1-6 | `QueryExecutor.execute` row-cap logic (§6.1) |
| US-V6-Q1 | AC-Q1-7 | Error envelope mapping table (§5) |
| US-V6-Q1 | AC-Q1-8 | `resolve_query_timeout_s` (§7) |
| US-V6-Q1 | AC-Q1-9..10 | `tests/unit/test_tool_registration.py` update |
| US-V6-Q2 | AC-Q2-1..8 | `tools/describe_graph_schema.py` + `schema_introspector.py` — ADR-24 |
| US-V6-Q3 | AC-Q3-1..4 | Integration tests (§10) |
| US-V6-Q4 | AC-Q4-1..8 | docs + version bump (doc-writer/devops stages) |

---

## 13. Risks / follow-ups (for senior-dev to consider in plan.md)

- **EXPLAIN plan operator names** vary slightly across Neo4j 4.x vs 5.x. The allowlist matches against a known set; unknown operator names default to **reject** (fail-closed). Add a regression test that records the operator names produced by the current Neo4j version in fixture form.
- **`schema_version` stamping on File nodes** is a writer-side change (additive prop on the File node). Re-ingestion against existing graphs is required to surface the note; older un-stamped graphs surface no warning (acceptable — note is opportunistic, not a guarantee).
- **IndraDB `pipe` over un-typed edges**: client API requires a type filter for `PipeQuery` in some versions; when absent we issue the untyped form and document the per-version caveat in the tool docstring. If unsupported on the pinned indradb version, downgrade `pipe` to "requires `t`" and surface `QUERY_PARSE_ERROR` if `t` is missing — finalize in implementation against the pinned `indradb` version.

---

## 14. References

- `requirements.md` US-V6-Q1..Q4, all ACs
- `scenarios.md` (Gherkin)
- `src/cpp_mcp/graphdb/__init__.py` — `select_driver` reuse pattern
- `src/cpp_mcp/graphdb/{neo4j_driver,indradb_driver}.py` — lazy-import + error mapping precedent
- `src/cpp_mcp/core/error_envelope.py` — `wrap_tool`, `_EXC_TO_CODE`, `ErrorCode` enum
- ADR-12 (URI-scheme dispatch), ADR-13 (DEPENDENCY_MISSING), ADR-14 (USR→UUID), ADR-15 (prop serialization)
- ADR-22 (this handoff): Cypher read-only via EXPLAIN
- ADR-23 (this handoff): IndraDB JSON query subset
- ADR-24 (this handoff): live schema discovery + version stamping
