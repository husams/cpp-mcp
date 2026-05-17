title: cpp-mcp S2 Consumer Runbook — Detecting S2 Enrichment
run_id: cpp-mcp-v7-s2
audience: downstream consumers of cpp-mcp (IDE plugins, graph query scripts, CI pipelines)
schema_version: v2 (additive; no schema bump in S2)

## Trigger

Use this runbook when you need to verify that a cpp-mcp build includes S2 enrichment (Type/Parameter
nodes, RETURNS/HAS_PARAM/OF_TYPE/POINTS_TO/REFERS_TO edges, Function/Class signature properties).

## Prerequisites

- cpp-mcp installed (v0.4.0 or later wheel, or editable install from this repo)
- MCP server running OR Python shell with access to cpp_mcp package
- A C++ compile database (compile_commands.json) for the target project
- GraphDB backend reachable (Neo4j URI or IndraDB URI); URI in environment variable

## Steps

### 1. Verify package version

```bash
python -c "import importlib.metadata; print(importlib.metadata.version('cpp-mcp'))"
# Expected: 0.4.0
```

### 2. Verify schema_version

```bash
python -c "from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION; print(SCHEMA_VERSION)"
# Expected: v2
```

### 3. Call describe_graph_schema and check node_types

```python
from cpp_mcp.graphdb.schema_introspector import describe_graph_schema
# db is your connected GraphDB backend instance
result = describe_graph_schema(db)

# S2 enrichment check: these labels must be present
assert "Type" in result["node_types"], "Type node missing — pre-S2 build"
assert "Parameter" in result["node_types"], "Parameter node missing — pre-S2 build"
print("node_types:", result["node_types"])
```

Expected output (node_types will include at minimum):
```
Function, Class, Field, GlobalVariable, File, Parameter, Type
```

### 4. Check edge_types for all five new S2 edges

```python
s2_edges = {"RETURNS", "HAS_PARAM", "OF_TYPE", "POINTS_TO", "REFERS_TO"}
missing = s2_edges - set(result["edge_types"])
assert not missing, f"Missing S2 edges: {missing}"
print("edge_types:", result["edge_types"])
```

Expected output (edge_types will include at minimum):
```
DEFINES, DECLARES, MEMBER_OF, CALLS, INCLUDES, RETURNS, HAS_PARAM, OF_TYPE, POINTS_TO, REFERS_TO
```

### 5. Verify a live ingest emits S2 nodes

After running `ingest_code` against a real C++ project:

```python
# Check via query_graphdb (MCP tool) or direct Neo4j / IndraDB query
# Example using query_graphdb MCP tool:
#   query_graphdb(query="MATCH (n:Type) RETURN count(n) AS type_count")
#   query_graphdb(query="MATCH (n:Parameter) RETURN count(n) AS param_count")
#   query_graphdb(query="MATCH ()-[r:RETURNS]->() RETURN count(r) AS returns_count")
#
# All counts must be > 0 on a non-trivial C++ codebase.
```

### 6. Verify schema_version field on the graph

```python
# query_graphdb: MATCH (n:File) RETURN n.schema_version LIMIT 1
# Expected: "v2"
# Note: v1 graphs return "v1"; S2 build reads them without error (see backward compat below).
```

## Verification

S2 enrichment is confirmed when ALL of the following hold:

| Check | Pass condition |
|-------|---------------|
| Package version | 0.4.0 |
| SCHEMA_VERSION constant | "v2" |
| describe_graph_schema node_types | contains "Type" AND "Parameter" |
| describe_graph_schema edge_types | contains all of RETURNS, HAS_PARAM, OF_TYPE, POINTS_TO, REFERS_TO |
| Live ingest Type count | > 0 |
| Live ingest Parameter count | > 0 |
| schema_version on graph | "v2" |

## Backward compat: v1 and v2-from-S1 graphs

v1 graphs (schema_version="v1"): readable without error. describe_graph_schema reflects only
labels present in the stored graph (no Type/Parameter if not ingested with S2 build).

v2-from-S1 graphs (schema_version="v2", ingested before S2): readable. Type and Parameter
nodes absent — this is expected. No read errors are raised. Re-ingest to populate S2 nodes.

Proof of backward compat: test_describe_v1_compat.py passes against seeded v1 graph fixtures;
NODE_VARIABLE constant still exported from schema.py for read-compat queries.

## PARM_DECL migration note

Graphs produced by S2+ builds classify function parameter cursors as `Parameter` (was `Variable`
in S1 and earlier). Queries that filter `node_type = "Variable"` to find parameters will return
empty on S2 graphs. Update queries to `node_type = "Parameter"`.

`Variable` nodes in existing graphs are unaffected. The `NODE_VARIABLE` schema constant remains
exported for compatibility with old graph readers.

## Rollback

cpp-mcp is a library; rollback = reinstall the prior wheel:

```bash
pip install dist/cpp_mcp-0.3.0-py3-none-any.whl --force-reinstall
# or pin in your dependency spec: cpp-mcp==0.3.0
```

Graphs ingested with S2 build (containing Type/Parameter/new-edges) will have those nodes/edges
orphaned after rollback — the S1 build does not clean up extra nodes. If graph purity is required,
truncate and re-ingest from the S1 build.

## On-call notes

- No k8s resources, no Istio routes, no certs, no Vault secrets involved.
- The only runtime dependency is the GraphDB backend (Neo4j or IndraDB).
- If `describe_graph_schema` returns fewer node_types than expected after upgrade, the graph was
  ingested with a pre-S2 build — re-run `ingest_code` to populate new labels.
- If `uv build` fails: check `uv` version (`uv --version`; requires 0.4+) and that
  `dist/` is writable.

## References

- plan.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/plan.md
- ADR-26: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md (decisions D1–D11)
- deploy-notes.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/deploy-notes.md
- test-report.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/test-report.md
- CHARTER: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md
- Prior stage runbook: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/ (S1)
- PRD: ~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md
- Cognee tags: task:cpp-mcp-v7-s2, role:devops
