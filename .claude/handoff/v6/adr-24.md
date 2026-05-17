# ADR-24: Schema discovery is live per call; writer stamps schema_version on File nodes
Status: accepted
Date: 2026-05-17
Run: cpp-mcp-v6

## Context

`describe_graph_schema` (US-V6-Q2) must return node/edge types with counts and
property keys. Two orthogonal design questions:

1. **Live vs cached.** Should the tool query the backend every call, or cache
   the schema for some TTL? Caching is cheaper but stale; live is fresh but
   pays per-call cost.
2. **Schema-version mismatch detection (OQ-Q2-1).** A graph ingested under
   an older writer schema may have different node/edge type names or property
   keys than the current code expects. How does the agent know it is looking
   at an old graph?

Forces:
- **Graph cardinality is small.** Pinned live verification (2026-05-17): 99 vertices, 180 edges, 6 vertex types, 2 edge types for `{fmt}/src/os.cc`. Even at 100× this scale (~10k vertices), the live cost on Neo4j is two `CALL db.*` round-trips + N small `MATCH (n:Label) RETURN keys(n) LIMIT $sample` round-trips — sub-100ms total.
- **The graph can change between calls.** `ingest_code` may have been re-run; another agent may be ingesting concurrently. Cached schema would silently mislead.
- **No process-shared cache exists.** FastMCP tools are stateless across calls; introducing process-state for caching adds invalidation logic for zero functional gain at this scale.
- **AC-Q2-2 result includes `schema_version: "v1"`.** The writer needs a stable constant the reader can compare against.
- **OQ-Q2-1 PM recommendation:** surface a warning in `notes` when the writer-stamped version on the graph differs from the current code.

## Decision

**Discovery is live per call.** No caching. Every `describe_graph_schema`
invocation issues fresh queries against the backend.

**Schema version stamping.** Introduce a single module-level constant:

```python
# src/cpp_mcp/graphdb/schema_version.py
SCHEMA_VERSION = "v1"
```

The exporter (`graphdb/exporter.py::extract_nodes_and_edges`) is amended to
stamp this value on every `File` node it emits:

```python
nodes: list[NodeRecord] = [
    NodeRecord(
        label=NODE_FILE,
        usr=f_usr,
        props={
            "path": str(file_path),
            "spelling": file_path.name,
            "schema_version": SCHEMA_VERSION,   # NEW
        },
    )
]
```

This is **additive**: existing graphs without the property are valid; they
simply do not surface a version note. The property is on `File` nodes (and
only those) because every export produces at least one `File` node, and
sampling them gives a single source of truth without polluting domain nodes.

**Mismatch detection** in `describe_graph_schema`:
1. After enumerating vertex types, if `File` is present, sample up to
   `sample_size` `File` vertices and collect the distinct values of
   `schema_version` property (absent → `null`).
2. The result's `schema_version` field is the current code's
   `SCHEMA_VERSION` constant — always.
3. The `notes` array always contains the two static disclaimers from
   AC-Q2-2 ("Property keys are inferred from a sample..."; "Counts are live...").
4. **If** any sampled `File` node has a non-null `schema_version` that
   differs from `SCHEMA_VERSION`, append:
   `"Graph contains File nodes with schema_version=<observed>; current code is <SCHEMA_VERSION>; counts and property keys may differ. Re-run ingest_code to re-stamp."`
5. **If** the graph contains `File` nodes but none has a `schema_version`
   property, append:
   `"Graph was ingested under a pre-v6 schema (no schema_version stamp); current code is <SCHEMA_VERSION>. Re-run ingest_code to re-stamp."`

The note is **opportunistic** — agents cannot rely on the absence of a note
to mean the schema is current (e.g. a graph with no `File` nodes will not
surface the warning). This is acceptable: every realistic ingest produces
`File` nodes.

**The `schema_version` constant lives in its own module** (not `schema.py`)
so importing the version does not pull in the (larger) schema constants
module — which matters for callers that only need the version string.

## Alternatives considered

### For live-vs-cached

1. **TTL cache (e.g. 60 s in-process).** Rejected. Adds invalidation surface
   (concurrent ingest, multiple URIs, restart semantics) for negligible
   savings at the current graph scale. Defeats the freshness guarantee in
   AC-Q2-2 note ("Counts are live as of the call").

2. **Cache keyed by `db_uri` with manual invalidation tool.** Rejected. New
   tool surface for invalidation; adds state that does not exist today.
   Re-evaluate if a profiling run shows discovery >500 ms on a realistic
   workload — not the case at current scale.

3. **Persist the schema in the graph itself as a special node.** Rejected.
   Couples reader and writer through a graph-stored side-channel; adds a
   write to `ingest_code` that needs its own idempotency story. The
   `schema_version` property on `File` nodes already gives a sample-based
   answer without inventing a "metadata vertex" convention.

### For mismatch detection

1. **Store schema version as a property on EVERY node.** Rejected. Wastes
   space (98 of 99 props are duplicates of the same string). Only `File`
   nodes need it; every export touches at least one.

2. **Compare graph node/edge type names against `schema.py` constants.**
   Rejected as the *primary* mechanism. The constant set is the same v1
   set in this handoff; in a future handoff that splits `Variable` →
   `FIELD` / `GLOBAL_VARIABLE` (gap S4), the **old** graph still has
   `Variable` nodes that the new code does not expect. Name comparison
   would surface "extra types" but not give the agent a stable identifier
   for which schema version produced them. Version stamping does.

3. **Hash the writer's edge/node type sets and stamp the hash.** Rejected
   as overkill. A human-readable version string is more useful in agent
   output and easier to bump explicitly when the schema changes.

4. **No version field at all (defer to a later handoff).** Rejected.
   Without it the AC-Q2-2 `schema_version: "v1"` field would be a static
   lie — the field claims a version that has no relationship to the graph
   on disk. PM recommendation in OQ-Q2-1 to surface a warning is
   inexpensive once the constant exists; ship both.

## Consequences

Positive:
- **Freshness guaranteed.** Every call sees the current graph.
- **No new state, no cache, no invalidation logic.**
- **Forward-compatible.** Schema bumps require: (a) edit `SCHEMA_VERSION`,
  (b) re-ingest to re-stamp `File` nodes. The reader code does not change.
- **Backward-compatible.** Old un-stamped graphs surface a "pre-v6" note;
  they keep working.
- **Cost is small.** Two `db.*` calls + N small `MATCH` queries on Neo4j;
  one `AllVertexQuery` + one `AllEdgeQuery` + per-type sampling on IndraDB.

Negative / follow-ups:
- Per-call cost grows with type cardinality (per-type sample query). At
  current 6+2 type cardinality this is trivial; at 100+ types it would be
  worth revisiting. Not in scope for v6.
- A graph with no `File` nodes (e.g. a graph populated by a non-cpp-mcp
  writer) cannot surface a schema-version note. Acceptable — that graph is
  outside the contract.
- Re-ingestion is the only way to migrate the version stamp on an existing
  graph. Documented in the tool docstring and in CHANGELOG `0.4.0`.

## References

- AC-Q2-1..AC-Q2-7 (requirements.md)
- OQ-Q2-1 (open question resolved here)
- `src/cpp_mcp/graphdb/exporter.py` — `extract_nodes_and_edges` (writer site for stamp)
- `src/cpp_mcp/graphdb/schema.py` — node/edge type constants
- ADR-14 (USR → uuid5 — `File` USRs are `file://<path>`)
- `[[project-v4-live-verification]]` — pinned graph cardinality (99V/180E/6+2 types)
- `[[pages/planning/cpp-mcp-codexgraph-gap]]` — S4 (FIELD/GLOBAL_VARIABLE split that would bump SCHEMA_VERSION)
- `design.md` §6.2 (schema-version note implementation)
