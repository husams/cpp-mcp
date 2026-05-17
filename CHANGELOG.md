# Changelog

All notable changes to this project will be documented in this file.

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
