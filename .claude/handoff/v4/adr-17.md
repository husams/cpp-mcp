# ADR-17: `nodes_written` / `edges_written` count inserts only; attempts are separate fields

Status: accepted
Date: 2026-05-17
Resolves: OQ-3-1 (partial), tightens ADR-7 / ADR-14 contract
Bound stories: US-V4-2, US-V4-3

## Context

The v3 `IndraDBDriver` returns `len(batch)` from both `upsert_nodes` and `upsert_edges` (`indradb_driver.py:154, 187`). The Neo4j driver returns `RETURN n`-row counts (`neo4j_driver.py:88-91, 121-124`), which also count attempts because `MERGE … RETURN n` always returns a row whether the node was created or merely matched. Both backends therefore report attempts, not inserts.

The exporter (`graphdb/exporter.py:511-514`) and the tool layer (`tools/export_to_graphdb.py:116-117, 134-135`) forward these counts into the tool response as `nodes_written` / `edges_written`. Defect 4 of `[[project-graphdb-v3-post-ship-findings]]` shows that re-exporting the same file reports the same `nodes_written` / `edges_written` as the first export, making the metrics unusable for progress display and breaking the idempotency expectation that callers naturally form.

The `GraphDriver` Protocol docstring currently says "Number of nodes actually written (created or updated)" — ambiguous. AC-3-1 forces the question: pick one.

Forces:

- Callers want **insert counts** so a second call returning `(0, 0)` proves idempotency.
- Callers also occasionally want **attempt counts** for progress bars during long exports.
- Backwards compatibility is moot: the v3 ship was never used in production (memory says "effectively unshipped until fixed"); there are no external consumers of the current attempt-count semantics.
- IndraDB has no `MERGE`-native API; `create_vertex` on an existing UUID is a no-op but returns nothing useful — we must check pre-existence ourselves.
- Neo4j has `ResultSummary.counters.nodes_created` / `relationships_created` exactly for this purpose.

## Decision

1. **Tighten the `GraphDriver` Protocol contract:** `upsert_nodes` and `upsert_edges` return the count of records **actually inserted** (created for the first time). A repeated upsert of identical records returns 0.

2. **Extend the exporter return** to include both flavours:
   ```python
   {
       "nodes_written":    int,  # inserts (was: attempts)
       "edges_written":    int,  # inserts (was: attempts)
       "nodes_attempted":  int,  # len(node_batch); always >= nodes_written
       "edges_attempted":  int,  # len(edge_batch); always >= edges_written
   }
   ```
   Propagate up through `tools/export_to_graphdb.py` (renamed to `tools/ingest_code.py` in v5) so the MCP tool response carries all four fields.

3. **IndraDB implementation:** per-record `get(SpecificVertexQuery(vid))` / `get(SpecificEdgeQuery(edge))` pre-check; create-and-increment only when the query returns empty.

4. **Neo4j implementation:** drop `RETURN n`; use `result.consume().counters.nodes_created` / `relationships_created` to sum inserts. Verified by code review (AC-3-3) — no live daemon test available.

5. **Document the contract** in the Protocol docstring (`driver.py:68-82`) and in the tool docstring (`tools/export_to_graphdb.py`, renamed to `tools/ingest_code.py` in v5).

## Alternatives considered

a. **Keep attempt semantics, rename fields to `nodes_attempted` / `edges_attempted`.**
   Rejected: AC-3-1 explicitly mandates that `nodes_written` / `edges_written` reflect inserts, and the field names already imply inserts to every reasonable reader. A rename would break callers' mental model worse than fixing the values.

b. **Compute inserts via a single `count_vertices` before/after delta** (batch-level rather than per-record).
   Rejected: cannot disambiguate per-record on partial failure; the IndraDB `count_*` RPC counts the whole graph, not a query subset, so it conflates this export with any concurrent writer. Per-record pre-check is local and unambiguous.

c. **Return only inserts (no `*_attempted` fields).**
   Rejected: AC-3-2 makes the attempts fields optional but encouraged for progress reporting, and `len(batch)` is free at the call site — exposing it costs nothing.

## Consequences

Positive:

- AC-2-4 (idempotent re-export returns `(0, 0)`) becomes naturally true.
- Metrics are useful for progress display: `nodes_written / nodes_attempted` is a meaningful ratio.
- Protocol contract is unambiguous; future backends (Memgraph, Kuzu) have a clear spec.
- The Neo4j MERGE-counter fix is correct-by-construction (uses the driver's own affected-rows counters rather than re-inventing them).

Negative:

- IndraDB driver issues 2× the gRPC calls per record (one `get`, one optional `create_vertex` / `create_edge`, plus property writes). Per-record latency ~doubles for first-import; idempotent re-imports actually become **faster** because most `create_*` calls are skipped.
- Existing v3 BDD scenarios (`SC_US_G5_1`, `SC_US_G5_2` in pyproject) and `tests/fixtures/fake_indradb.py` assume attempt-count semantics — they must be updated as part of the developer plan. Listed in design.md §5.
- Slight risk of race condition on the IndraDB driver: two concurrent exports could both see "absent" and both create — but IndraDB's `create_vertex` is itself idempotent on UUID collision, so the worst case is one over-count by 1 in a concurrent scenario. cpp-mcp does not export concurrently to the same daemon today (single-process MCP server); flagged in design §5 as a v5+ concern only if multi-process becomes a goal.

Follow-ups:

- v5: add a live Neo4j daemon test to actually exercise the `counters.nodes_created` path.
- v5+: if exports become large enough that 2× RPC cost matters, switch IndraDB to a bulk pre-fetch (`get(RangeVertexQuery())` filtered by USR set) then in-memory diff.

## References

- `[[project-graphdb-v3-post-ship-findings]]` — defects 4 and 5
- `src/cpp_mcp/graphdb/driver.py` — Protocol to tighten
- `src/cpp_mcp/graphdb/indradb_driver.py:124-187` — per-record pre-check refactor target
- `src/cpp_mcp/graphdb/neo4j_driver.py:80-127` — `RETURN n` → `consume().counters` refactor target
- `src/cpp_mcp/graphdb/exporter.py:504-514` — extend return dict
- `src/cpp_mcp/tools/export_to_graphdb.py:116-135` — propagate new fields (renamed to `ingest_code.py` in v5)
- requirements.md US-V4-3, AC-3-1..AC-3-4, OQ-3-1
- scenarios.md SC-V4-3-01, SC-V4-3-02, SC-V4-2-04
- Neo4j Python driver docs: `ResultSummary.counters` (`neo4j` ≥5.x stable)

---

## Known-gap addendum (v4)

During the S6 live e2e run against `test-repo/fmt/src/os.cc`, the export
attempted approximately 23 000 edge inserts but only 180 were stored by the
daemon.  The ~22 820 dropped attempts are **not** a silent data-loss bug —
they are IndraDB rejecting `create_edge` calls whose source or target vertex
was not present in the graph at insert time (edges referencing USR identifiers
from headers outside the fixture's compile unit).  IndraDB returns success but
does not store the edge; the per-record `SpecificEdgeQuery` post-create verify
path (§Decision §3) detects absence and correctly counts these as 0 inserts.

Consequences:

1. `edges_attempted` (~23 K) >> `edges_written` (180) for a typical single-file
   export.  This ratio is expected and correct; it is not a driver defect.

2. The post-create verify path issues one additional `get(SpecificEdgeQuery)`
   call per edge attempt, roughly doubling gRPC round-trips for the edge phase.
   This cost is accepted per §Consequences above for fixture-sized exports.

3. **Deferred to v5** if larger exports hit a real ceiling: switch to a
   bulk pre-fetch of the USR vertex set before the edge phase, skip all edges
   whose endpoints are not in that set without issuing a `create_edge` RPC at
   all.  That eliminates the ~22 K wasted `create_edge` + `SpecificEdgeQuery`
   pairs.
