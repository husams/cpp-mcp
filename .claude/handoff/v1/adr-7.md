# ADR-7: GraphDB backend — Neo4j MVP behind a GraphDriver Protocol; upsert idempotency
Status: accepted
Context:
  - OQ-8: choose graph DB target. Candidates: Neo4j (industry standard, Bolt protocol, mature Python driver), Cognee (user's existing infrastructure per ~/.claude/CLAUDE.md), abstract-only (no concrete backend).
  - OQ-9: idempotency. Re-exporting the same file must not duplicate nodes/edges.
  - US-7/AC-1, AC-2 fix the node + edge type sets we must populate.

Decision:
  - **MVP backend: Neo4j** via the official `neo4j` Python driver (Bolt protocol, `bolt://` URI as in scenarios.md SC-US-7-1). Reasons:
    - Bolt URI is already implied by the scenario fixtures.
    - First-class Cypher MERGE provides upsert idempotency naturally.
    - Wide LLM-agent ecosystem support (LangChain Neo4j chains, Cypher generation).
  - **Driver abstraction:** `graphdb/driver.py` defines a `GraphDriver` Protocol:
    ```python
    class GraphDriver(Protocol):
        def connect(self, uri: str) -> None: ...
        def upsert_nodes(self, batch: list[Node]) -> int: ...
        def upsert_edges(self, batch: list[Edge]) -> int: ...
        def close(self) -> None: ...
    ```
    A Cognee driver can be added later by implementing the same Protocol; no tool/exporter code changes.
  - **Idempotency (OQ-9):** every node carries its libclang **USR** as primary key. Cypher: `MERGE (n:NodeKind {usr: $usr}) SET n += $props`. Edges: `MERGE (a)-[r:EDGE_TYPE {source_usr,target_usr,edge_type}]->(b)`. Re-export updates `props`, never duplicates.
  - **No transaction across files** (US-7/AC-5 partial-success): each file is one Bolt transaction. Failures are caught and recorded into the response's `errors[]` list; previously-committed files stay committed.
  - **Connection failure:** if `driver.connect(uri)` raises (timeout, auth fail, dns fail), the tool returns `{code:"DB_UNREACHABLE", ...}` immediately — no file is parsed.

Alternatives considered:
  - Cognee MVP: rejected for v1 — Cognee is the user's general-purpose memory; using it as the C++ knowledge graph couples two different data lifecycles and conflates "agent memory" with "code knowledge". Add as a driver later.
  - Abstract only (no concrete backend in v1): rejected — would mean US-7 is undeliverable, and the scenarios reference a concrete bolt URI.
  - SQLite + graph emulation: rejected — Cypher patterns in agent prompts are valuable; SQLite kills that.
  - Per-file transaction commit deferred to end-of-call (all-or-nothing): rejected — US-7/AC-5 explicitly forbids this.

Consequences:
  - Positive: standard tool, agents can query via Cypher; driver Protocol keeps the door open for Cognee/Memgraph/etc.
  - Negative: operator must run Neo4j (docker run -p 7687:7687 neo4j); documented in runbook.
  - Follow-up: add Cognee driver in v1.x once Cognee's graph API stabilizes for arbitrary node schemas.

References:
  - requirements.md US-7 (all AC), OQ-8, OQ-9
  - scenarios.md SC-US-7-1..11
  - design.md §2 (graphdb/), §7
  - Neo4j Python driver: https://neo4j.com/docs/python-manual/current/
