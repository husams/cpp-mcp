story: S3 fix-metrics-inserts-vs-attempts-both-drivers
date: 2026-05-17
author: developer (Claude Sonnet 4.6)
ac: AC-3-3

## Neo4j driver code-review finding (AC-3-3)

### Bug identified

`src/cpp_mcp/graphdb/neo4j_driver.py` — both `upsert_nodes` and `upsert_edges`
were counting **attempt rows**, not **insert rows**.

**Root cause (nodes, pre-fix lines 87-90):**
```python
query = f"MERGE (n:`{label}` {{usr: $usr}}) SET n += $props RETURN n"
result = tx.run(query, usr=usr, props=props)
if result.single() is not None:
    written += 1
```
`MERGE … RETURN n` always returns a row whether the node was newly created or
merely matched.  `result.single() is not None` is therefore always `True` for
an existing node, producing attempt-count semantics instead of insert-count.

**Root cause (edges, pre-fix lines 115-123):** identical pattern with
`MERGE (a)-[r:TYPE]->(b) … RETURN r`.

### Fix applied

Dropped `RETURN n` / `RETURN r` from the Cypher queries and switched to
`ResultSummary.counters`:

```python
# nodes
result = tx.run(query, usr=usr, props=props)
summary = result.consume()
written += summary.counters.nodes_created

# edges
result = tx.run(query, src=src, tgt=tgt, props=props)
summary = result.consume()
written += summary.counters.relationships_created
```

`nodes_created` is 1 only when `MERGE` creates a new node; 0 when it matches an
existing one.  Same semantics for `relationships_created`.  This is the
canonical pattern from the Neo4j Python driver docs (`ResultSummary.counters`
≥ neo4j 5.x stable).

### Verification status

Code review only — no live Neo4j daemon test in v4 scope (out-of-scope per
requirements §Out of Scope and design §6).  AC-3-3 is explicitly a
code-review AC.  A live daemon test is tracked as a v5 follow-up in ADR-17
§Follow-ups.

### Files changed

- `src/cpp_mcp/graphdb/neo4j_driver.py` — `upsert_nodes` and `upsert_edges`
  both updated (lines 80-127 pre-fix; see git diff for exact ranges).
