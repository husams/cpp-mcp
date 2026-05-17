# Plan — v6 Graph Query Surface

Status: ready-for-developer
Date: 2026-05-17
Run: cpp-mcp-v6
Driving docs: requirements.md, design.md, adr-22, adr-23, adr-24
Language: python (uv, ruff, mypy --strict, pytest)
Project root: /Users/husam/workspace/cpp-mcp
Target version: 0.3.0 → 0.4.0 (additive surface, no breaking changes)

---

## Goal

Implement two new MCP tools (`query_graphdb`, `describe_graph_schema`) that
read the property graph populated by `ingest_code`, against Neo4j or IndraDB,
without ever mutating it. Reuse the v3 URI-scheme dispatch and ADR-8 error
envelope. Ship with mock-driver Neo4j coverage + IndraDB live integration
tests + README/CHANGELOG/ADR docs + version bump.

---

## Conventions (apply to every story)

- All commands run from project root with `uv`.
- Type-annotated, `mypy --strict` clean, `ruff` clean (line-length 100, ruleset E,F,I,UP,B,SIM,RUF; B008 ignored — see pyproject).
- Lazy-import optional backend deps (`neo4j`, `indradb`) inside `connect()` to mirror existing driver pattern; raise `DependencyMissingError` on import failure.
- New tool modules use `@mcp.tool(name=...)` + `@wrap_tool(...)`, returning JSON-serializable dicts, with `request_id` (uuid4 hex) on success.
- Tool names MUST be unprefixed — v5 rename-invariant test continues to pass.
- No new runtime deps. No new test deps.

---

## Story S1 — Error-envelope codes + schema_version constant + writer stamp

**Goal:** Land the cross-cutting plumbing every later story depends on, in a single small change so S2/S3 can run in parallel.

**AC IDs satisfied:** AC-Q1-7 (new codes registered), AC-Q2-2 (`schema_version` field), ADR-24 writer stamp.

**Files to change:**
- `src/cpp_mcp/core/error_envelope.py` — add `ErrorCode.READ_ONLY_VIOLATION`, `QUERY_PARSE_ERROR`, `QUERY_UNSUPPORTED`, `QUERY_TIMEOUT`; add matching `ReadOnlyViolationError`, `QueryParseError`, `QueryUnsupportedError`, `QueryTimeoutError` exception classes; extend `_EXC_TO_CODE`. Reuse existing `DB_UNREACHABLE` as the wire code for the `CONNECTION_FAILED` alias documented per design §5.
- `src/cpp_mcp/graphdb/exporter.py` — in `extract_nodes_and_edges`, stamp `schema_version = SCHEMA_VERSION` on every `File` node's `props` (ADR-24).

**New files:**
- `src/cpp_mcp/graphdb/schema_version.py` — `SCHEMA_VERSION: str = "v1"` and module docstring referencing ADR-24.
- `tests/unit/core/test_query_error_codes.py` — assert each new exception class maps to its code via `_EXC_TO_CODE`; assert codes are present in `ErrorCode` enum and unique.
- `tests/unit/graphdb/test_schema_version_stamp.py` — invoke `extract_nodes_and_edges` on a small fixture and assert every emitted `File` node carries `schema_version == "v1"`.

**Exit criteria (run from project root):**
```bash
uv run ruff check src/cpp_mcp/core/error_envelope.py src/cpp_mcp/graphdb/exporter.py src/cpp_mcp/graphdb/schema_version.py tests/unit/core/test_query_error_codes.py tests/unit/graphdb/test_schema_version_stamp.py
uv run mypy
uv run pytest tests/unit/core/test_query_error_codes.py tests/unit/graphdb/test_schema_version_stamp.py -q
uv run pytest -q   # full unit suite still green (existing 642+ tests)
```

**Parallel-safe:** no (foundation; S2 and S3 depend on it).

---

## Story S2 — `query_graphdb` executor + tool (IndraDB path + dispatch + tool entry)

**Goal:** Land `QueryExecutor` protocol, IndraDB executor, scheme dispatch, the MCP tool, and unit coverage of validation/envelope/clamps/purity. Neo4j executor is a stub in this story (raises `NotImplementedError` on `execute` for Neo4j URIs); story S3 fills the Cypher read-only path.

Per design §5, dispatch order, row-limit clamp ([1,500]), timeout resolver via `CPP_MCP_QUERY_TIMEOUT_SECONDS` (clamped [1,120]), and `request_id` generation live in the tool entry / executor base — all wired here so S3 only adds the Cypher walker.

**AC IDs satisfied:** AC-Q1-1, AC-Q1-2, AC-Q1-4, AC-Q1-5, AC-Q1-6, AC-Q1-7 (IndraDB path + dispatch + envelope), AC-Q1-8 (timeout resolver + IndraDB ThreadPoolExecutor wrap), AC-Q1-9, AC-Q1-10. ADR-23 in full.

**Files to change:**
- `src/cpp_mcp/server/app.py` (or wherever the tool registry imports happen) — register the new `query_graphdb` tool.
- `tests/unit/test_tool_registration.py` — assert 9 registered tools; both new names unprefixed.

**New files:**
- `src/cpp_mcp/graphdb/query_executor.py` — `QueryExecutor` Protocol, `QueryResult` TypedDict, `select_executor(db_uri)` scheme dispatch mirroring `select_driver` (reuse the existing scheme frozensets from `graphdb/__init__.py`).
- `src/cpp_mcp/graphdb/indradb_query_executor.py` — `IndraDbQueryExecutor` implementing `QueryExecutor`. Lazy-imports `indradb` only inside `connect`. Imports only `Client.get`, `get_properties`, and the 7 `*Query` constructors needed by ADR-23. JSON-shape validator (`_dispatch_query`) implementing the 7 verbs from ADR-23; coerces vertex/edge rows per design §6.1 with batched `get_properties` per page; truncates at `row_limit`.
- `src/cpp_mcp/graphdb/neo4j_query_executor.py` — stub class with `connect` that imports `neo4j` lazily and `execute` that raises `NotImplementedError("filled in S3")`. Present so `select_executor` returns the right type today.
- `src/cpp_mcp/core/query_config.py` — `resolve_query_timeout_s()` per design §7.
- `src/cpp_mcp/tools/query_graphdb.py` — MCP tool entry: input validation (`INVALID_ARGUMENT` for empty `db_uri`/`query`, clamp `row_limit` to `max(1, min(500, row_limit))`, default 200), scheme dispatch via `select_executor`, timeout from `resolve_query_timeout_s`, error envelope mapping, `request_id`. Reuses `clang_session.executor` (single-worker pool, design §7) to wrap IndraDB calls with `concurrent.futures` timeout; maps `concurrent.futures.TimeoutError` → `QueryTimeoutError`.
- `tests/unit/graphdb/test_indradb_query_subset.py` — parametrize all 7 allowed verb shapes (happy path against a fake IndraDB client), 3 unsupported verbs (→ `QueryUnsupportedError`), 2 malformed-JSON cases (→ `QueryParseError`), bad `t` regex, bad UUID, missing/extra args.
- `tests/unit/graphdb/test_query_executor_purity.py` — `import cpp_mcp.graphdb.indradb_query_executor as m; assert not any(n.startswith(("set_", "delete")) for n in dir(m))` (AC-Q1-4).
- `tests/unit/graphdb/test_query_executor_dispatch.py` — `select_executor("bolt://x")` returns Neo4j executor type; `select_executor("indradb://x")` returns IndraDB executor type; unknown scheme raises `InvalidArgumentError`.
- `tests/unit/tools/test_query_graphdb.py` — envelope mapping for every error code (`INVALID_ARGUMENT`, `DEPENDENCY_MISSING`, `DB_UNREACHABLE`, `QUERY_PARSE_ERROR`, `QUERY_UNSUPPORTED`, `QUERY_TIMEOUT`); `row_limit` default 200; clamp to [1,500]; truncation flag; `request_id` is a 32-char hex string; backend field correct per URI scheme. Uses fake IndraDB driver / monkeypatched executor — no live backend.
- `tests/unit/core/test_query_config.py` — env unset → 30; valid env → that value clamped to [1,120]; invalid env → 30.

**Exit criteria:**
```bash
uv run ruff check src/cpp_mcp/graphdb/query_executor.py src/cpp_mcp/graphdb/indradb_query_executor.py src/cpp_mcp/graphdb/neo4j_query_executor.py src/cpp_mcp/core/query_config.py src/cpp_mcp/tools/query_graphdb.py tests/unit/graphdb tests/unit/tools/test_query_graphdb.py tests/unit/core/test_query_config.py tests/unit/test_tool_registration.py
uv run mypy
uv run pytest tests/unit/graphdb/test_indradb_query_subset.py tests/unit/graphdb/test_query_executor_purity.py tests/unit/graphdb/test_query_executor_dispatch.py tests/unit/tools/test_query_graphdb.py tests/unit/core/test_query_config.py tests/unit/test_tool_registration.py -q
uv run pytest -q
```

**Parallel-safe:** yes — can run in parallel with S4 (`describe_graph_schema`) since the only shared touchpoints are `test_tool_registration.py` (count bumps from 7→8 here, 8→9 in S4 — coordinate the merge) and `select_executor` infrastructure used by S4 introspector. Sequence S2 before S3.

---

## Story S3 — Neo4j `query_graphdb` executor with EXPLAIN-based read-only enforcement

**Goal:** Replace the S2 stub with the full Neo4j executor implementing the ADR-22 algorithm.

**AC IDs satisfied:** AC-Q1-3 (Neo4j read-only enforcement), AC-Q1-8 (Neo4j timeout path), AC-Q1-2 (Neo4j row coercion: Node/Relationship/Path → dicts per design §6.1). ADR-22 in full.

**Files to change:**
- `src/cpp_mcp/graphdb/neo4j_query_executor.py` — implement `connect` (lazy `import neo4j`, build driver from URI), `execute` (run `EXPLAIN <query>` first with bound parameters and timeout; walk `ResultSummary.plan` per ADR-22 algorithm — `WRITE_OPERATOR_PREFIXES`, `READ_ONLY_PROCEDURES` allowlist, fail-closed); on pass run actual query in same session with `timeout=timeout_s`; coerce rows per design §6.1; map `neo4j.exceptions.CypherSyntaxError` → `QueryParseError`, transaction-timeout → `QueryTimeoutError`, service-unavailable → `DbUnreachableError`.

**New files:**
- `tests/unit/graphdb/test_neo4j_read_only.py` — fabricated `ResultSummary.plan` trees per test case: allow set (`MATCH`/`OPTIONAL MATCH`/`WITH`/`RETURN`/`WHERE`/`UNWIND`/`ORDER BY`/`SKIP`/`LIMIT`/read-only `CALL { MATCH ... }` subquery / `db.labels` proc); reject set (`CREATE`, `MERGE`, `DELETE`, `DetachDelete`, `SET`, `RemoveLabels`, `LoadCsv`, `Foreach`, `apoc.create.node` proc, `CALL { CREATE ... }` nested write, unknown-write-prefix operator). Mocks `session.run` to return the fabricated summary; asserts allow vs `ReadOnlyViolationError`.
- `tests/unit/graphdb/test_neo4j_query_executor.py` — happy-path row coercion using `neo4j.graph.Node`/`Relationship`/`Path` fake objects; error mapping for syntax/timeout/unreachable.

**Exit criteria:**
```bash
uv run ruff check src/cpp_mcp/graphdb/neo4j_query_executor.py tests/unit/graphdb/test_neo4j_read_only.py tests/unit/graphdb/test_neo4j_query_executor.py
uv run mypy
uv run pytest tests/unit/graphdb/test_neo4j_read_only.py tests/unit/graphdb/test_neo4j_query_executor.py tests/unit/tools/test_query_graphdb.py -q
uv run pytest -q
```

**Parallel-safe:** no — depends on S2 (replaces its stub). Can run parallel with S4.

---

## Story S4 — `describe_graph_schema` introspector + tool

**Goal:** Land the schema-discovery tool for both backends, including the `File`-node schema_version note logic from ADR-24.

**AC IDs satisfied:** AC-Q2-1..AC-Q2-8. ADR-24 in full.

**Files to change:**
- `src/cpp_mcp/server/app.py` — register `describe_graph_schema`.
- `tests/unit/test_tool_registration.py` — count to 9 (final).

**New files:**
- `src/cpp_mcp/graphdb/schema_introspector.py` — `SchemaIntrospector` Protocol; `select_introspector(db_uri)` (mirrors `select_executor`); `Neo4jSchemaIntrospector` (uses `CALL db.labels()`, `CALL db.relationshipTypes()`, per-label parameterized `MATCH` with backtick-escaped label/type names validated against `^[A-Za-z_][A-Za-z0-9_]*$`; no `apoc.*`); `IndraDbSchemaIntrospector` (`AllVertexQuery`/`AllEdgeQuery` → group by `t` → sample per type via `get_properties`); builds the AC-Q2-2 result dict with `schema_version = SCHEMA_VERSION`, sorted `node_types`/`edge_types` by `(-count, name)`, the two static notes, and the ADR-24 mismatch/missing-stamp note when `File` samples disagree.
- `src/cpp_mcp/tools/describe_graph_schema.py` — MCP tool entry: input validation (empty `db_uri` → `INVALID_ARGUMENT`; clamp `sample_size` to `[10, 1000]`), dispatch via `select_introspector`, timeout from `resolve_query_timeout_s` wrapping introspector calls, error envelope, `request_id`, never echoes `db_uri` (design §6.2).
- `tests/unit/graphdb/test_schema_introspector.py` — ordering (count desc, name asc), `sample_size` clamp, empty-graph (`node_types: []`/`edge_types: []`/`totals: {0,0}`), schema-version mismatch note (sampled `File` with different version), pre-v6 note (sampled `File` without `schema_version`), no note when version matches. Uses fake clients for both backends.
- `tests/unit/tools/test_describe_graph_schema.py` — envelope mapping for `INVALID_ARGUMENT`, `DEPENDENCY_MISSING`, `DB_UNREACHABLE`, `QUERY_TIMEOUT`; `sample_size` clamps; `db_uri` non-echo (response dict must not contain the URI string); `request_id` shape; `schema_version` field equals `SCHEMA_VERSION`.

**Exit criteria:**
```bash
uv run ruff check src/cpp_mcp/graphdb/schema_introspector.py src/cpp_mcp/tools/describe_graph_schema.py tests/unit/graphdb/test_schema_introspector.py tests/unit/tools/test_describe_graph_schema.py tests/unit/test_tool_registration.py
uv run mypy
uv run pytest tests/unit/graphdb/test_schema_introspector.py tests/unit/tools/test_describe_graph_schema.py tests/unit/test_tool_registration.py -q
uv run pytest -q
```

**Parallel-safe:** yes — can run parallel with S2/S3 once S1 lands; coordinate `test_tool_registration.py` count edits (S2 bumps 7→8, S4 bumps 8→9 — merge ordering matters).

---

## Story S5 — IndraDB live integration tests

**Goal:** Pin the v4-style regression guard on the new read surface against a live IndraDB daemon (the same one v4 wired up).

**AC IDs satisfied:** AC-Q3-1, AC-Q3-2, AC-Q3-3 (Neo4j integration deferred — noted), AC-Q3-4.

**New files:**
- `tests/integration/test_query_graphdb_e2e.py` — `@pytest.mark.integration` + `@pytest.mark.indradb`. Reuses `INDRADB_AUTOSTART=1` fixture from v4's `tests/integration/test_indradb_e2e.py`. Sequence: `ingest_code` on `test-repo/fmt/src/os.cc` → assert pinned 99 vertices / 180 edges via `query_graphdb` with `{"query":"all_edges"}` and `all_vertices`; `{"query":"vertex_with_type","args":{"t":"Function"}}` → exactly 21 rows; `{"query":"all_vertices"}` with `row_limit=50` → `stats.truncated == True`, `len(rows) == 50`.
- `tests/integration/test_describe_graph_schema_e2e.py` — same markers and fixture. After `ingest_code`, call `describe_graph_schema` and assert exactly six vertex types (`Variable`, `TypeAlias`, `Function`, `Class`, `Namespace`, `File`) with counts (33/28/21/13/3/1) and two edge types (`DEFINES`, `REFERENCES`) with counts (98/82); `totals.vertices == 99`, `totals.edges == 180`; each vertex type's `property_keys` non-empty and includes `name` where applicable per writer schema.

**Exit criteria:**
```bash
uv run ruff check tests/integration/test_query_graphdb_e2e.py tests/integration/test_describe_graph_schema_e2e.py
uv run mypy
INDRADB_AUTOSTART=1 uv run pytest -m integration tests/integration/test_query_graphdb_e2e.py tests/integration/test_describe_graph_schema_e2e.py -q   # under 60s combined
uv run pytest -q   # unit suite still green
```

**Parallel-safe:** no — depends on S2, S3, S4.

---

## Story S6 — Docs, ADRs (already accepted), CHANGELOG, version bump

**Goal:** Release hygiene. ADRs 22/23/24 already exist as `accepted` in this handoff; doc work is README + CHANGELOG + pyproject + wiki.

**AC IDs satisfied:** AC-Q4-1, AC-Q4-2, AC-Q4-3, AC-Q4-4, AC-Q4-5, AC-Q4-6, AC-Q4-7, AC-Q4-8.

**Files to change:**
- `README.md` — add "Query surface" section: doc both tools, IndraDB JSON shape (table from ADR-23), Neo4j Cypher allowlist (link ADR-22), end-to-end agent example (`describe_graph_schema` → reason → `query_graphdb`), short note that v6 is additive (no rename).
- `CHANGELOG.md` — `0.4.0` section listing `query_graphdb` + `describe_graph_schema`; note "additive surface; no breaking changes to existing tools".
- `pyproject.toml` — `version = "0.4.0"`.

**New files:**
- `~/workspace/wiki/pages/code/cpp-mcp-v6.md` — sibling of `cpp-mcp-v5.md`: summarize the new surface, link `[[pages/planning/cpp-mcp-codexgraph-gap]]`, link ADRs 22/23/24.
- Update `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md` — mark S1 as "shipped in v6"; link `cpp-mcp-v6.md`.
- Update `~/workspace/wiki/index.md` and append `~/workspace/wiki/log.md` per the wiki ingest workflow.

**Exit criteria:**
```bash
uv run pytest -q          # nothing broken
uv build                  # 0.4.0 sdist + wheel build clean
test "$(uv run python -c 'import importlib.metadata as m; print(m.version("cpp-mcp"))')" = "0.4.0"
grep -q '^## 0.4.0' /Users/husam/workspace/cpp-mcp/CHANGELOG.md
grep -q 'query_graphdb' /Users/husam/workspace/cpp-mcp/README.md
grep -q 'describe_graph_schema' /Users/husam/workspace/cpp-mcp/README.md
test -f /Users/husam/workspace/wiki/pages/code/cpp-mcp-v6.md
```

**Parallel-safe:** no — runs last; depends on S1–S5.

---

## Story ordering and dependencies

```
S1 (foundation) ──► S2 (executor + tool + IndraDB) ──► S3 (Neo4j executor)
                ╲                                    ╲
                 ╲                                    ╲──► S5 (live integration) ──► S6 (release)
                  ╲                                   ╱
                   ╲──► S4 (describe_graph_schema) ──╯
```

- S1 must land first.
- S2 and S4 can run in parallel after S1; coordinate `test_tool_registration.py` count merge.
- S3 must follow S2.
- S5 requires S2+S3+S4.
- S6 runs last.

Parallel-safe count: 2 (S2 ‖ S4).

---

## Risks / Out of scope

- Out of scope: NL→query translation (`translate_query`, v7), schema/access-kind edge changes (gap S3–S5), Neo4j live integration test (mock-driver coverage only — AC-Q3-3), PyPI publish (manual release step in deploy-notes), per-call auth.
- Risk: Neo4j EXPLAIN operator-name set drifts across 4.x/5.x. Mitigation: ADR-22's prefix-match plus fail-closed default; S3 records the operator set produced by the pinned driver as a fixture.
- Risk: IndraDB `pipe` may require `t` filter on the pinned client version. Mitigation: per ADR-23, `t` is optional in the wire format; the executor detects unsupported untyped form and falls back to surfacing `QUERY_PARSE_ERROR` requiring `t` (design §13).
- Risk: `test_tool_registration.py` count edits collide when S2 and S4 are merged in parallel. Mitigation: coordinator merges S2 first (7→8), then S4 (8→9), or both stories edit the file via a shared "expected_tool_names = {...}" constant introduced in S2.
- Risk: `schema_version` stamping on `File` nodes is a writer change that affects existing graphs only after re-ingest. ADR-24 accepts this (opportunistic note).

---

## References

- requirements.md (US-V6-Q1..Q4, all ACs)
- design.md (§§2,3,4,5,6,7,8,9,10,12,13)
- adr-22 (Cypher read-only via EXPLAIN)
- adr-23 (IndraDB JSON query subset)
- adr-24 (live schema discovery + version stamping)
- CHARTER.md (run paths, traceability chain)
- v4 IndraDB fixture: `tests/integration/test_indradb_e2e.py`
- Pinned graph counts source: `[[project-v4-live-verification]]`
