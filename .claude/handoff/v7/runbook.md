run_id: cpp-mcp-v7-s1
produced_by: devops
scope: downstream consumer guidance for cpp-mcp v7 S1 schema upgrade (v1 → v2)
charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md

---

# Runbook: cpp-mcp schema v1 → v2 upgrade (S1)

## Trigger

Use this runbook when:
- Upgrading cpp-mcp to a build that includes v7 S1 (Variable→Field/GlobalVariable split, MEMBER_OF.access, new node properties).
- Consuming a graph written by cpp-mcp with SCHEMA_VERSION "v2".
- Querying a backend that contains a v1 graph and you need to know whether re-ingestion is required.

---

## Prerequisites

- cpp-mcp installed from a build at or after commit `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`.
- A running graph backend (Neo4j or IndraDB) reachable at the configured URI.
- MCP server started and `describe_graph_schema` tool accessible.

---

## Steps

### 1. Detect the schema version in your backend

Call the `describe_graph_schema` tool (via MCP or direct Python import):

```python
from cpp_mcp.graphdb.schema_introspector import IndraDbSchemaIntrospector  # or Neo4jSchemaIntrospector
# or via MCP tool call: describe_graph_schema({})
```

Inspect the response object:

```python
response = describe_graph_schema()
print(response["schema_version"])    # "v2" if backend was written by S1+ exporter
print(response["node_types"])        # list of node type names
```

If `schema_version` is `"v2"`:
- The graph was written by the S1 exporter. Fields are stored as `Field`, namespace-scope variables as `GlobalVariable`, parameters as `Variable`.
- No action needed.

If `schema_version` is `"v1"` (or absent):
- The backend holds a legacy graph. See step 3.

### 2. Verify new node types are present (v2 graphs only)

```python
node_types = response["node_types"]
assert "Field" in node_types,          "S1 upgrade not reflected"
assert "GlobalVariable" in node_types, "S1 upgrade not reflected"
assert "Variable" in node_types,       "PARM_DECL nodes still emitted as Variable"
```

Check new property keys on `Field` and `GlobalVariable` entries:

```python
for nt in response["node_types_detail"]:
    if nt["name"] in ("Field", "GlobalVariable"):
        props = nt["property_keys"]
        assert "is_const" in props
        assert "is_constexpr" in props
        assert "is_static" in props
        assert "storage_class" in props
```

Check MEMBER_OF carries `access`:

```python
for et in response["edge_types_detail"]:
    if et["name"] == "MEMBER_OF":
        assert "access" in et["property_keys"]
```

### 3. Handling v1 graphs already in your backend

The read path (`query_graphdb`, `describe_graph_schema`) **tolerates v1 graphs** — it will not raise an exception (ADR-25 D1). The introspector surfaces a skew note when the stored `schema_version` differs from `SCHEMA_VERSION = "v2"`.

Decision tree:

| Situation | Action |
|---|---|
| Query-only workload, v1 graph is acceptable | No action. Queries work; `Variable` nodes are returned where `Field`/`GlobalVariable` would appear in v2. |
| You need `Field`/`GlobalVariable` distinction | Re-ingest: call `ingest_code` against your compile DB. The S1 exporter will write v2 nodes. |
| You need `MEMBER_OF.access` values | Re-ingest: the v1 exporter wrote `MEMBER_OF` edges without `access`; they will have no `access` property. |
| Mixed v1+v2 data in same backend | Nodes written before upgrade retain their old type (`Variable`). Re-ingest affected TUs to promote them. |

To re-ingest a specific translation unit:

```
# via MCP
ingest_code({"source_file": "/path/to/file.cpp", "graph_db_uri": "<uri>"})
```

There is no automatic migration tool. Re-ingestion is the only supported promotion path.

### 4. Querying the new node types

After v2 ingest, query for `Field` or `GlobalVariable` via `query_graphdb`:

```python
# Find all private fields of a class
query_graphdb({
    "query": "MATCH (f:Field)-[e:MEMBER_OF {access: 'private'}]->(c:Class) RETURN f, c",
    "graph_db_uri": "<uri>"
})

# Find all GlobalVariable nodes
query_graphdb({
    "query": "MATCH (g:GlobalVariable) RETURN g",
    "graph_db_uri": "<uri>"
})
```

IndraDB users: use the `edge_with_property_equal` verb for access filtering (client-side fallback implemented in v6 bugfix; no protocol change required).

---

## Verification

After re-ingestion, call `describe_graph_schema` and confirm:

- `schema_version == "v2"`
- `"Field"` and `"GlobalVariable"` appear in `node_types`
- `MEMBER_OF` edge type has `"access"` in `property_keys`
- Legacy `"Variable"` is still present (PARM_DECL function parameters remain `Variable` per ADR-25 D2)

---

## Rollback

There is no automated rollback. If you need to revert to v1 behaviour:

1. Pin cpp-mcp to the last pre-S1 commit (before `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`).
2. Re-ingest your codebase. The v1 exporter will write `Variable` nodes for all FIELD_DECL and VAR_DECL cursors.
3. The backend will then hold a v1 graph (schema_version "v1").

---

## On-call notes

- `schema_version` discrepancy between the running library and the stored graph is surfaced as an informational skew note in `describe_graph_schema` output — it is not a failure.
- `Variable` nodes will persist in v2 graphs for PARM_DECL cursors (function parameters). This is intentional (ADR-25 D2) and not a classification bug.
- If `Field` and `GlobalVariable` are both absent from `node_types` on a freshly ingested v2 graph, the source file likely contains no class member fields or namespace-scope variables (e.g., header-only template library or function-only source).
- Integration tests that use a live IndraDB daemon and assert pinned node counts (test_describe_graph_schema_e2e.py `_EXPECTED_NODE_COUNTS_STABLE`) will need count updates after the first live v2 ingest — see test-report.md advisory (b).

---

## References

- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md (D1, D2, D4, D5, D8)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/design.md §7 (schema_version), §8 (read tolerance)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/implementation-notes.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/test-report.md
- src/cpp_mcp/graphdb/schema_version.py
- src/cpp_mcp/graphdb/schema_introspector.py
