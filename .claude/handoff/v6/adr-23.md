# ADR-23: IndraDB query JSON shape and supported subset
Status: accepted
Date: 2026-05-17
Run: cpp-mcp-v6

## Context

`query_graphdb` against an IndraDB backend (AC-Q1-5) needs a query language.
IndraDB has no native text query language analogous to Cypher; its Python
client v3.x exposes a typed builder API (`AllVertexQuery`, `VertexWithTypeQuery`,
`SpecificVertexQuery`, `PipeQuery`, `VertexWithPropertyValueQuery`, etc.) that
compose by `>>`. We need a wire-format that an MCP-client agent can send as a
JSON string in the `query` parameter, with a small, well-defined subset.

Forces:
- **AC-Q1-5 minimum coverage.** "(a) all vertices of type X, (b) all edges of type Y, (c) vertices where property name == X, (d) one-hop traversal (`pipe` outbound/inbound)."
- **AC-Q1-4 read-only.** The executor module imports only `get*` and `Query` constructors — no `set_*` / `delete_*`. The JSON shape MUST NOT have any verb that could imply mutation.
- **CodexGraph use-cases.** "Which functions call `vformat`?" → property-equal vertex query + outbound `CALLS` pipe. "What does this file define?" → outbound `DEFINES` pipe from a `File` vertex. The minimum subset covers both with one round trip each.
- **Agent ergonomics.** The agent already calls `describe_graph_schema` to learn vertex/edge type names; the query JSON should consume those names verbatim.
- **No new dependency.** Parse with stdlib `json`; validate with hand-written shape checks.

## Decision

Pin the IndraDB query wire format as a single-level JSON object:

```json
{"query": "<verb>", "args": { ... }}
```

Allowlisted verbs (case-sensitive) and required `args`:

| verb | required `args` | IndraDB builder mapping |
|---|---|---|
| `all_vertices` | `{}` | `AllVertexQuery()` |
| `all_edges` | `{}` | `AllEdgeQuery()` |
| `vertex_with_type` | `{"t": str}` | `VertexWithTypeQuery(t)` |
| `edge_with_type` | `{"t": str}` | `EdgeWithTypeQuery(t)` |
| `vertex_with_property_equal` | `{"name": str, "value": JSON-scalar}` | `VertexWithPropertyValueQuery(name, value)` |
| `edge_with_property_equal` | `{"name": str, "value": JSON-scalar}` | `EdgeWithPropertyValueQuery(name, value)` |
| `pipe` | `{"vertex_id": uuid-str, "direction": "outbound"\|"inbound", "t": str?}` | `SpecificVertexQuery(uuid) >> PipeQuery(direction[, t])` |

**Validation rules:**
1. `query` must be a JSON object (not a Cypher string). If the IndraDB executor cannot `json.loads(query)`, raise `QueryParseError` (this implements OQ-Q1-2 — a Cypher string sent to an IndraDB URI fails parse, not translation).
2. `query["query"]` must be one of the seven verbs above. Otherwise → `QueryUnsupportedError`.
3. `args` must contain exactly the required keys (no extras except documented optionals). Otherwise → `QueryParseError`.
4. `t` must match `^[A-Za-z_][A-Za-z0-9_]*$` (mirrors the IndraDB type-identifier rule).
5. `vertex_id` must be a valid UUID string (`uuid.UUID(...)` succeeds). Note: USR-derived vertex IDs are `uuid5(NS_CPPMCP_USR, usr)` per ADR-14; the agent obtains them from a prior `query_graphdb` result.
6. `value` must be a JSON scalar (str/int/float/bool/null). Matches the IndraDB property type contract.

**Result coercion** (per design.md §6.1):
- Vertex result row → `{"id": str(uuid), "t": str, "properties": dict}`.
- Edge result row → `{"outbound_id": str, "inbound_id": str, "t": str, "properties": dict}`.
- Properties are fetched **per page**, capped at `row_limit` — no N+1 round-trips beyond the truncation boundary.

**`pipe` semantics:** returns the **neighboring vertices** (not edges) by default
(matches the most common agent question "what does X point to?"). If `t` is
provided, restricts to edges of that type. To enumerate edges separately the
agent uses `edge_with_type`. This single-direction one-hop coverage is the
minimum from AC-Q1-5; multi-hop and edge-projection compositions are out of
scope for v6.

**Versioning:** the wire format is `query_schema_version = "v1"` and surfaced
in the `query_graphdb` tool docstring. Future verbs (e.g. `count`, `paged`)
add to the allowlist without breaking existing clients.

## Alternatives considered

1. **Expose the full IndraDB builder API as JSON.** Rejected. Builder
   composition with `>>` is hard to express unambiguously in JSON without a
   recursive grammar; tooling agents will struggle to compose nested pipes
   correctly. The 7-verb flat shape covers the AC-Q1-5 minimum and ~90% of
   the question patterns from the gap analysis with no recursion.

2. **Use a Cypher-on-IndraDB transpiler.** Rejected. No mature library; we
   would own the transpiler. Also conflicts with OQ-Q1-2 resolution (no
   translation in v6 — it is the explicit scope of S2 / `translate_query` in
   the gap roadmap, future v7).

3. **Adopt Gremlin syntax for the IndraDB path.** Rejected. IndraDB does not
   speak Gremlin; we would write a Gremlin → IndraDB translator. Same
   problem as (2), worse because Gremlin is larger than Cypher.

4. **Make `query` always be a Python-eval string of the builder API.**
   Rejected outright for the obvious code-execution attack surface.

5. **Embed an existing query DSL like SPARQL.** Rejected. IndraDB is a
   property graph, not RDF; mapping would lose information and require a
   translator we do not own.

## Consequences

Positive:
- **Easy to parse and validate** — stdlib `json` + 7 small validators; no
  grammar, no parser-generator, no third-party dep.
- **Covers AC-Q1-5 minimum exactly**, with one verb per requirement.
- **Symmetric with `describe_graph_schema` output** — the agent receives
  vertex/edge type names from `describe_graph_schema` and uses them as `t`
  values without transformation.
- **Read-only by construction** — none of the 7 verbs imply a write; the
  executor module imports only `Client.get` and the `*Query` constructors.

Negative / follow-ups:
- No filter composition (e.g. `vertex_with_type` AND `vertex_with_property_equal`).
  Agents needing intersection must do it client-side after retrieval, or wait
  for a future `and` / `intersection` verb (additive — would not break v1).
- No multi-hop traversal. A `pipe_n` verb with a `depth` arg can be added
  later; v6 deliberately limits to one hop to avoid runaway queries until we
  add a depth budget.
- `pipe` returns neighbor vertices, not edges — agents wanting the edge
  records must use `edge_with_type` separately. Documented in the tool
  docstring.
- IndraDB Python client v3.x is pinned; if upstream renames builder classes
  in v4, the executor's lazy-import block needs an update. The wire format
  is stable independent of that change.

## References

- AC-Q1-4, AC-Q1-5 (requirements.md)
- IndraDB Python client v3.x: `indradb>=3,<4` (MPL-2.0) — `Query` builder API
- ADR-14 (USR → uuid5 — vertex IDs surfaced to agents are deterministic uuid5)
- ADR-15 (property serialization — scalars pass through, others JSON-encoded)
- `design.md` §9 (subset table), §6.1 (result coercion)
