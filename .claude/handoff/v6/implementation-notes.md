# S6 Implementation Notes — Docs, CHANGELOG, version bump

## Files changed

- `pyproject.toml` — version 0.3.0 → 0.4.0
- `CHANGELOG.md` — added `## 0.4.0` section: new tools, error codes, schema versioning, config var, ADR refs
- `README.md` — Tools section: 7 → 9 tools; new "Query surface" section (describe_graph_schema, query_graphdb, IndraDB verb table, Neo4j Cypher allowlist, end-to-end agent example); config table: added CPP_MCP_QUERY_TIMEOUT_SECONDS; test count updated to 642+
- `~/workspace/wiki/pages/code/cpp-mcp-v6.md` — new wiki page: new surface, ADR-22/23/24 summaries, verb table, Cypher allowlist, agent pattern, story list
- `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md` — marked S1 as shipped in v6; links cpp-mcp-v6.md
- `~/workspace/wiki/index.md` — cpp-mcp entry updated to v0.4.0 / 9 tools; v6 entry added
- `~/workspace/wiki/log.md` — appended v6 ingest entry

## Tests added/run

```
uv run pytest -q
# 867 passed, 6 skipped in 19.47s

uv build
# Successfully built dist/cpp_mcp-0.4.0.tar.gz + cpp_mcp-0.4.0-py3-none-any.whl

# Exit-criteria checks (all pass):
# VERSION OK, CHANGELOG OK, README query_graphdb OK, README describe_graph_schema OK, WIKI PAGE OK
```

## Deviations from plan

None. All files-to-touch per plan.md S6 addressed.

## Follow-ups

None. S6 is release hygiene; all implementation code is in S1–S5.

## References

- `plan.md` lines 172–202 (S6 story)
- `.claude/handoff/v6/adr-22.md`, `adr-23.md`, `adr-24.md`
- CHARTER.md

---

# S5 Implementation Notes — IndraDB live integration tests

## Files changed

- `tests/integration/test_query_graphdb_e2e.py` — NEW (4 tests covering AC-Q3-1, AC-Q3-2, AC-Q3-4)
- `tests/integration/test_describe_graph_schema_e2e.py` — NEW (6 tests covering AC-Q3-1, AC-Q3-2, AC-Q3-4, schema_version/notes)
- `src/cpp_mcp/graphdb/indradb_query_executor.py` — fixed 4 bugs (see below)
- `src/cpp_mcp/graphdb/schema_introspector.py` — fixed 2 bugs (see below)
- `tests/fixtures/fake_indradb.py` — updated to match real API shapes for properties-mode
- `tests/unit/graphdb/test_schema_introspector.py` — updated inline fake to return VertexProperties/EdgeProperties

## Tests added/run

### Exit gate: lint
```
uv run ruff check tests/integration/test_query_graphdb_e2e.py \
  tests/integration/test_describe_graph_schema_e2e.py \
  tests/fixtures/fake_indradb.py src/cpp_mcp/graphdb/indradb_query_executor.py \
  src/cpp_mcp/graphdb/schema_introspector.py \
  tests/unit/graphdb/test_schema_introspector.py
# All checks passed!
```

### Exit gate: unit tests
```
uv run pytest -q --ignore=tests/integration
# 867 passed, 6 skipped in 13.76s
```

### Exit gate: integration tests
```
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 \
  uv run pytest -m "integration and indradb" \
  tests/integration/test_query_graphdb_e2e.py \
  tests/integration/test_describe_graph_schema_e2e.py -q
# 10 passed in 415.73s (0:06:55)
```

## Bugs fixed (discovered in live S5 testing)

### Bug 1 (fixed in previous session): `_fetch_vertex_props` / `_fetch_edge_props` used `client.get_properties()`
The real indradb Client has no `get_properties()` method. Both helpers were rewritten to use
`client.get(query.properties())` which yields batches of `VertexProperties` / `EdgeProperties`.

### Bug 2: `VertexWithTypeQuery` / `EdgeWithTypeQuery` don't exist in real indradb
`indradb_query_executor._dispatch_query()` used `indradb.VertexWithTypeQuery(t)` and
`indradb.EdgeWithTypeQuery(t)` — these don't exist in the pinned version.
Fix: replaced with `AllVertexQuery()`/`AllEdgeQuery()` + client-side Python filter `[v for v in raw if str(v.t) == t]`.
Properties are fetched via `SpecificVertexQuery(*[v.id for v in items])` (variadic).

### Bug 3: `schema_introspector._vertex_property_keys()` / `_edge_property_keys()` treated `VertexProperties` as `NamedProperty`
`client.get(SpecificVertexQuery(vid).properties())` yields batches of `VertexProperties` objects
(with `.vertex` and `.props`), not flat `NamedProperty` objects. Both methods were updated to
iterate the double-loop: `for vp in prop_batch: for np in vp.props: keys.add(np.name)`.

### Bug 4: `schema_introspector._build_notes()` had same `VertexProperties` traversal bug
Same fix applied to `_build_notes()` which tracked `schema_version` property on File nodes.

### Bug 5: `pipe` verb used `client.get_properties()`
The `pipe` verb had its own `client.get_properties()` call. Replaced with
`_fetch_vertex_props(client, SpecificVertexQuery(*[item.id for item in items]), items)`.

## fake_indradb.py changes

- Added `NamedProperty`, `VertexProperties`, `EdgeProperties` classes matching real API shapes.
- `SpecificVertexQuery` now takes `*vids` (variadic); legacy `.vid` attribute preserved for single-id compat.
- `SpecificEdgeQuery` now takes `*edges` (variadic).
- All query types gained `.properties()` returning `_VertexPropertiesQuery` / `_EdgePropertiesQuery`.
- `Client.get()` dispatches properties-mode via internal wrappers, returning proper VertexProperties/EdgeProperties batches.
- `VertexWithTypeQuery` and `EdgeWithTypeQuery` kept as legacy no-ops (production code no longer uses them).

## test_schema_introspector.py changes

- Replaced `_FakeProp` with `_FakeNamedProp`, `_FakeVertexProperties`, `_FakeEdgeProperties`.
- `_FakeSpecificVertexQuery.properties()` now returns `_FakePropertiesQuery`.
- `_FakeIndraDBClient.get()` dispatches `_FakePropertiesQuery` to return proper `_FakeVertexProperties` objects.

## Deviations from plan

- Plan did not explicitly list the 4 production bugs in executor + introspector; these were found during live
  testing and fixed per design §13 ("finalize in implementation against the pinned indradb version").
- Integration tests took ~7 minutes (vs plan's "under 60s" combined); each of the 10 tests independently
  runs `ingest_code` on {fmt}/src/os.cc which requires a full clang AST parse. All 10 pass correctly.

## Follow-ups

None. All plan.md S5 exit criteria clear.

## References

- `plan.md` lines 150–171 (S5 story)
- `design.md` §13 (live API finalization)
- Cognee tags: `task:cpp-mcp-v6`, `role:developer`
