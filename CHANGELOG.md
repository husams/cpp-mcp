# Changelog

All notable changes to this project will be documented in this file.

## 0.4.0 — 2026-05-17

**Additive surface — no breaking changes to existing tools.**

Two new read-only MCP tools extend the graph query surface introduced by `ingest_code`.
Existing 0.3.0 clients require no changes; the seven renamed tools from 0.3.0 are unchanged.

### New tools

| Tool | What it does |
|---|---|
| `query_graphdb` | Execute a read-only query against a Neo4j or IndraDB graph and return matching rows (capped at `row_limit`, default 200, max 500). Neo4j path accepts Cypher with EXPLAIN-based read-only enforcement (ADR-22). IndraDB path accepts a 7-verb JSON shape (ADR-23). |
| `describe_graph_schema` | Discover live node/edge types, counts, and sampled property keys from the connected graph. Returns a `schema_version` field and surface notes when the graph was ingested under an older writer schema (ADR-24). |

### Error codes added

`READ_ONLY_VIOLATION`, `QUERY_PARSE_ERROR`, `QUERY_UNSUPPORTED`, `QUERY_TIMEOUT` — all follow the existing ADR-8 error envelope shape.

### Schema versioning

`ingest_code` now stamps `schema_version = "v1"` on every `File` node it writes.
`describe_graph_schema` compares the stamp to the current code version and surfaces a note
when the graph was ingested under a different schema. Graphs ingested before 0.4.0 are valid
and keep working; re-run `ingest_code` to add the stamp.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `CPP_MCP_QUERY_TIMEOUT_SECONDS` | `30` | Per-query timeout in seconds (clamped to [1, 120]). |

### References

- ADR-22: Cypher read-only enforcement via Neo4j EXPLAIN plan inspection
- ADR-23: IndraDB query JSON shape and supported subset
- ADR-24: Schema discovery is live per call; writer stamps `schema_version` on `File` nodes

---

## 0.3.0 — 2026-05-17

**Rationale:** Tool names have been normalised to drop the redundant `cpp_` prefix and rename
`cpp_export_to_graphdb` to `ingest_code`, as part of the CodexGraph gap roadmap documented in
[`pages/planning/cpp-mcp-codexgraph-gap.md`](~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md).
This aligns the server with the planned `query_graphdb` / `translate_query` tools and makes the
tool surface self-documenting without language qualification.

### Tool renames

| 0.2.x name (old)            | 0.3.0 name (new)        |
|-----------------------------|-------------------------|
| `cpp_get_ast`               | `get_ast`               |
| `cpp_get_definition`        | `get_definition`        |
| `cpp_get_references`        | `get_references`        |
| `cpp_get_type_info`         | `get_type_info`         |
| `cpp_get_header_info`       | `get_header_info`       |
| `cpp_get_preprocessor_state`| `get_preprocessor_state`|
| `cpp_export_to_graphdb`     | `ingest_code`           |

**Breaking:** no compatibility aliases are provided. Clients calling 0.2.x tool names will receive
an MCP `tool not found` error. Update all `client.call_tool(...)` invocations to the new names
shown in the table above.
