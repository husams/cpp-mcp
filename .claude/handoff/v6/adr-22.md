# ADR-22: Cypher read-only enforcement via Neo4j EXPLAIN plan inspection
Status: accepted
Date: 2026-05-17
Run: cpp-mcp-v6

## Context

`query_graphdb` (US-V6-Q1, AC-Q1-3) must guarantee that no Cypher string sent
through the tool can mutate the graph. The graph is a derived artifact of
`ingest_code`; a mutating query would silently corrupt the index used by every
downstream agent. The enforcement boundary lives entirely in the MCP server —
the underlying Neo4j account may have write privileges.

Forces:
- **C-G5 (v3) — optional dependencies.** Adding a Cypher AST parser (e.g. `pycypher`, `antlr4-python3-runtime` + a grammar) inflates the install footprint and pulls in unmaintained code paths.
- **`pycypher` is unmaintained** (last meaningful release pre-2020; tracks an old openCypher grammar; cannot parse Neo4j 5.x `CALL { ... }` subquery syntax correctly).
- **Regex on the query string is unsafe.** Trivial bypasses: `MATCH (n) WITH n /* CREATE */ RETURN n` followed by `CALL apoc.create.node([...], {})` inside a string literal in a property predicate; `WHERE n.name = "DELETE"` would false-positive a naive guard.
- **Neo4j ships its own parser** — every query the server is about to run is already going to be parsed by Neo4j. `EXPLAIN <query>` runs that parser and returns a plan without executing the query (it is itself a read-only operation: verified in Neo4j docs for both 4.x and 5.x).
- **Allowlist clauses (from AC-Q1-3):** `MATCH`, `OPTIONAL MATCH`, `WITH`, `RETURN`, `WHERE`, `UNWIND`, `ORDER BY`, `SKIP`, `LIMIT`, read-only `CALL { ... }` subqueries. Rejected: `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, any `CALL <proc>` outside a small read-only `db.*` allowlist (notably any `apoc.*` mutator).

## Decision

**Enforce read-only by running `EXPLAIN <query>` against the same Neo4j
connection, then recursively walking the returned `ResultSummary.plan` tree
and rejecting any operator whose name matches a write-side prefix or any
`ProcedureCall` whose procedure name is not in a small read-only allowlist.**

Algorithm (in `neo4j_query_executor._enforce_read_only`):

```python
WRITE_OPERATOR_PREFIXES = (
    "Create", "Merge", "Delete", "DetachDelete",
    "SetProperty", "SetLabels", "SetNodeProperty", "SetRelationshipProperty",
    "RemoveLabels", "RemoveProperty",
    "LoadCsv", "Foreach", "EmptyResult",  # Foreach can wrap writes
)
READ_ONLY_PROCEDURES = frozenset({
    "db.labels", "db.relationshipTypes", "db.propertyKeys",
    "db.schema.visualization", "db.schema.nodeTypeProperties",
    "db.schema.relTypeProperties",
})

def _walk(plan: Plan) -> None:
    op = plan.operator_type  # e.g. "AllNodesScan", "CreateNode", "ProcedureCall"
    if any(op.startswith(p) for p in WRITE_OPERATOR_PREFIXES):
        raise ReadOnlyViolation(f"operator {op!r} is not read-only")
    if op == "ProcedureCall":
        name = plan.arguments.get("Details") or plan.arguments.get("name", "")
        if name not in READ_ONLY_PROCEDURES:
            raise ReadOnlyViolation(f"procedure {name!r} not in read-only allowlist")
    for child in plan.children:
        _walk(child)
```

The EXPLAIN call itself uses the same `timeout=resolve_query_timeout_s()` and
catches `neo4j.exceptions.CypherSyntaxError` → `QUERY_PARSE_ERROR`. On
allowlist pass, the actual query runs in the same `session.run(..., timeout=...)`
call; on reject, the actual query never executes.

**Failure mode is fail-closed.** Unknown operator names (e.g. a new Neo4j
release introduces an operator we have not yet classified) default to
**reject** if they match any write prefix; otherwise they pass. The prefix
match is conservative — `CreateIndex` (technically schema-only and not a data
mutation) is rejected, which is acceptable for v6.

**CALL { ... } subqueries.** Neo4j compiles read-only inner bodies into plain
read operators (`Argument`, `Apply`, `Eager*`-free `Projection`, etc.) and
write inner bodies into the same `Create*`/`Merge*`/etc. operators as a
top-level write. The recursive walk catches them identically.

## Alternatives considered

1. **`pycypher` AST parser (PM option (a)).** Rejected. Unmaintained (no
   release tracking Neo4j 5.x syntax including `CALL { ... }` subqueries,
   `EXISTS { ... }` patterns, or query-language version directives). Pulls in
   a heavy ANTLR runtime. Would require us to keep the grammar in sync as
   Neo4j evolves.

2. **Minimal recursive-descent parser scoped to the allowlist (PM option (c)).**
   Rejected. Cypher is non-trivial to tokenize correctly (string-literal
   handling, multiline comments, parameterized labels, escape sequences in
   backtick identifiers). Maintaining a correct mini-parser is a recurring
   tax; getting it 99% right is the dangerous case — a parser that almost
   works lets a determined caller construct a bypass we did not foresee.

3. **Read-only Neo4j account + role-based access control.** Rejected as the
   *only* mechanism: violates the requirement that enforcement live in the
   MCP server (the URI may carry credentials with write privileges set by an
   operator who does not realize this tool is being exposed). Useful as
   defense-in-depth; **operators are encouraged in the README** to use a
   read-only role, but the server does not rely on it.

4. **`CALL { ... } IN TRANSACTIONS` + rollback.** Rejected. Would require
   actually running the query then aborting; some side effects (e.g.
   triggered procedures, audit log entries) cannot be rolled back. Wasteful
   even when read-only.

5. **String-level regex/keyword scan (PM option (a) variant in the wild).**
   Rejected on the security argument above — trivial bypasses via string
   literals, comments, and parameter-name aliasing.

## Consequences

Positive:
- **No new dependency.** Uses the parser Neo4j is going to use anyway.
- **Always tracks Neo4j semantics** — if Neo4j changes how `MERGE` is
  compiled, the plan still shows a `Merge*` operator, the allowlist still
  rejects.
- **EXPLAIN is cheap** (~1–5 ms for the queries we expect; verified against
  Neo4j 5.x docs claim "EXPLAIN does not execute the query").
- **Fail-closed default** on unknown operators.

Negative / follow-ups:
- Operator-name set varies across Neo4j 4.x / 5.x (e.g. `MergeCreate` vs
  `Merge`). Mitigation: prefix-match on `Merge*` catches both. A regression
  test fixture records the set of operator names emitted by the pinned
  `neo4j` driver version; CI surfaces drift.
- `Foreach` can wrap writes (`FOREACH (x IN [1,2,3] | CREATE (:N {v:x}))`) —
  conservatively rejected by listing `Foreach` in the prefix set even though
  read-only `FOREACH` constructs exist. Acceptable for v6; a future ADR can
  relax this by inspecting `Foreach` children instead.
- One extra round-trip per query (EXPLAIN + actual). Acceptable given the
  agent-driven workload (queries are infrequent and human-scale latency).
- Read-only allowlist for `db.*` procedures is small; if an agent needs
  `db.schema.visualization` or similar, it is already included; adding more
  read-only procs is a one-line allowlist edit + ADR amendment.

## References

- AC-Q1-3 (requirements.md), OQ-Q1-1
- Neo4j Cypher Manual: `EXPLAIN` planner operators (4.4 / 5.x)
- `neo4j` Python driver: `ResultSummary.plan` shape — `operator_type`, `arguments`, `children`
- `src/cpp_mcp/graphdb/neo4j_driver.py` (lazy-import + error-mapping precedent reused)
- ADR-12 (URI-scheme dispatch), ADR-13 (DEPENDENCY_MISSING)
- `design.md` §8 (enforcement summary)
