# Scenarios — v6 Graph Query Surface
# run_id: cpp-mcp-v6
# business-analyst output; upstream: requirements.md; downstream: design.md

---

## Requirements

### In-scope

- `query_graphdb` MCP tool (US-V6-Q1 / AC-Q1-1..AC-Q1-10)
- `describe_graph_schema` MCP tool (US-V6-Q2 / AC-Q2-1..AC-Q2-8)
- Tool registration invariants (9 tools, no `cpp_` prefix)

### Out-of-scope

- Integration test authorship (US-V6-Q3) — tests are derived from these scenarios; BA does not author them
- Docs, ADR content, version bump (US-V6-Q4)
- `translate_query` (S2 of gap roadmap — future handoff)
- Neo4j live integration test (deferred per requirements out-of-scope)
- PyPI publish

### Assumptions

- "confirmed" — traceable directly to requirements.md
- "assumed" — inferred from PM recommendations or precedent in prior handoffs (v3/v4/v5)
- "needs-clarification" — requires architect or PM decision before implementation

### Open Questions

| ID | Question | Tag |
|---|---|---|
| OQ-Q1-1 | Cypher read-only enforcement strategy: (a) maintained AST library, (b) `EXPLAIN`-based via Neo4j's own parser, or (c) minimal recursive-descent. PM recommends (b). Architect must decide; ADR-22 records the decision. | needs-clarification |
| OQ-Q1-2 | Cypher-shaped string sent to IndraDB backend — attempt translation or return `QUERY_PARSE_ERROR`? PM recommends `QUERY_PARSE_ERROR` for v6. Architect confirms. | needs-clarification |
| OQ-Q2-1 | Schema-version mismatch (graph ingested under older writer schema vs current code): should `notes` array include a warning? PM recommends yes. Architect confirms and pins the constant name. | needs-clarification |

### Edge Cases (summary)

| Edge case | Tag |
|---|---|
| row_limit supplied above 500 — clamp to 500 | confirmed (AC-Q1-1) |
| row_limit supplied as 0 or negative — validate/reject or clamp | needs-clarification |
| Result count exactly at row_limit — truncated=false | confirmed (AC-Q1-6) |
| Result count exceeds row_limit — truncated=true, len==row_limit, no raise | confirmed (AC-Q1-6) |
| Timeout env-var below 1 — clamp to 1 | confirmed (AC-Q1-8) |
| Timeout env-var above 120 — clamp to 120 | confirmed (AC-Q1-8) |
| Cypher CALL {...} with read-only inner — passes | confirmed (AC-Q1-3) |
| Cypher CALL {...} with write inner — rejected READ_ONLY_VIOLATION | confirmed (AC-Q1-3) |
| Cypher string sent to IndraDB URI — QUERY_PARSE_ERROR | assumed (OQ-Q1-2 recommendation) |
| IndraDB query type outside subset — QUERY_UNSUPPORTED | confirmed (AC-Q1-5) |
| Empty graph — node_types:[], edge_types:[], totals:0 | confirmed (AC-Q2-7) |
| sample_size below 10 — clamp to 10 | confirmed (AC-Q2-1) |
| sample_size above 1000 — clamp to 1000 | confirmed (AC-Q2-1) |
| db_uri with embedded credentials — URI never echoed in response | confirmed (AC-Q2-6) |
| schema_version mismatch between writer and live code | needs-clarification (OQ-Q2-1) |

### Stakeholders

- MCP-client agent (primary consumer — drives query + schema-discovery workflows)
- Server maintainer (regression guard — rename-invariant, read-only enforcement)
- Downstream user (safety surface — read-only boundary, URI credential non-echo)

---

## Gherkin

```gherkin
Feature: query_graphdb — execute read-only graph queries via MCP tool
  # Maps to US-V6-Q1 (AC-Q1-1..AC-Q1-10)
  # Tool registered in src/cpp_mcp/tools/query_graphdb.py

  # ---------------------------------------------------------------------------
  # Happy paths — Neo4j backend
  # ---------------------------------------------------------------------------

  # AC-Q1-1, AC-Q1-2 (confirmed)
  Scenario: Execute a simple MATCH query against Neo4j and receive well-formed rows
    Given the MCP server is running with the Neo4j driver importable
    And a Neo4j database is reachable at "bolt://localhost:7687"
    And the database contains at least one Function node
    When I call "query_graphdb" with:
      | db_uri    | bolt://localhost:7687                        |
      | query     | MATCH (n:Function) RETURN n.name LIMIT 5     |
    Then the response contains a "rows" array with at most 5 entries
    And each entry is JSON-serializable
    And the response contains "stats" with keys "backend", "ms", "rows_returned", "truncated"
    And "stats.backend" equals "neo4j"
    And the response contains a non-empty string "request_id"

  # AC-Q1-1, AC-Q1-2 (confirmed)
  Scenario: Execute a parameterized Cypher query with bound parameters
    Given a Neo4j database reachable at "bolt://localhost:7687" with Function nodes
    When I call "query_graphdb" with:
      | db_uri     | bolt://localhost:7687                          |
      | query      | MATCH (n:Function) WHERE n.name = $fn RETURN n |
      | parameters | {"fn": "vformat"}                              |
    Then the response "rows" contains only Function nodes where name equals "vformat"
    And Neo4j Node objects are coerced to dicts containing "_labels" key

  # AC-Q1-2 (confirmed)
  Scenario: Neo4j Relationship objects are coerced to dicts with _type key
    Given a Neo4j database reachable at "bolt://localhost:7687" with CALLS edges
    When I call "query_graphdb" with:
      | db_uri | bolt://localhost:7687                             |
      | query  | MATCH (a)-[r:CALLS]->(b) RETURN r LIMIT 1         |
    Then each row entry for "r" is a dict containing "_type" key equal to "CALLS"

  # ---------------------------------------------------------------------------
  # Happy paths — IndraDB backend
  # ---------------------------------------------------------------------------

  # AC-Q1-1, AC-Q1-2, AC-Q1-5 (confirmed)
  Scenario: Query all vertices from IndraDB
    Given an IndraDB server is reachable at "indradb://localhost:27615"
    And the database contains vertices
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615         |
      | query  | {"query": "all_vertices", "args": {}} |
    Then the response "rows" contains dicts each with keys "id", "t", and "properties"
    And "stats.backend" equals "indradb"

  # AC-Q1-5 (confirmed)
  Scenario: Query all edges from IndraDB
    Given an IndraDB server is reachable at "indradb://localhost:27615"
    And the database contains edges
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615        |
      | query  | {"query": "all_edges", "args": {}} |
    Then the response "rows" contains dicts representing edges

  # AC-Q1-5 (confirmed)
  Scenario: Query IndraDB vertices filtered by type
    Given an IndraDB server populated with Function and Namespace vertices
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                               |
      | query  | {"query": "vertex_with_type", "args": {"t": "Function"}} |
    Then every row in "rows" has "t" equal to "Function"

  # AC-Q1-5 (confirmed)
  Scenario: Query IndraDB edges filtered by type
    Given an IndraDB server populated with DEFINES and REFERENCES edges
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                                |
      | query  | {"query": "edge_with_type", "args": {"t": "DEFINES"}}    |
    Then every row in "rows" has "t" equal to "DEFINES"

  # AC-Q1-5 (confirmed)
  Scenario: Query IndraDB vertices by property equality
    Given an IndraDB server with Function vertices including one named "vformat"
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                                                                 |
      | query  | {"query": "vertex_with_property_equal", "args": {"name": "name", "value": "vformat"}}    |
    Then all returned rows have property "name" equal to "vformat"

  # AC-Q1-5 (confirmed)
  Scenario: Query IndraDB edges by property equality
    Given an IndraDB server with edges carrying a "kind" property
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                                                              |
      | query  | {"query": "edge_with_property_equal", "args": {"name": "kind", "value": "direct"}}    |
    Then all returned rows have property "kind" equal to "direct"

  # AC-Q1-5 (confirmed)
  Scenario: One-hop outbound traversal via IndraDB pipe query
    Given an IndraDB server with vertex "v1" connected outbound to "v2"
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                                                                  |
      | query  | {"query": "pipe", "args": {"direction": "outbound", "vertex_id": "<v1-id>"}}               |
    Then the response "rows" contains the vertex or edge entries reachable outbound from "v1"

  # AC-Q1-5 (confirmed)
  Scenario: One-hop inbound traversal via IndraDB pipe query
    Given an IndraDB server with vertex "v2" having inbound edge from "v1"
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                                                                 |
      | query  | {"query": "pipe", "args": {"direction": "inbound", "vertex_id": "<v2-id>"}}               |
    Then the response "rows" contains the vertex or edge entries reaching inbound to "v2"

  # ---------------------------------------------------------------------------
  # Row cap and truncation boundary conditions
  # ---------------------------------------------------------------------------

  # AC-Q1-1, AC-Q1-6 (confirmed)
  Scenario: row_limit defaults to 200 and result under cap — truncated false
    Given an IndraDB server with 50 vertices total
    When I call "query_graphdb" with db_uri and query for all_vertices, no row_limit specified
    Then "stats.rows_returned" equals 50
    And "stats.truncated" is false
    And "rows" has length 50

  # AC-Q1-1, AC-Q1-6 (confirmed)
  Scenario: Result exceeds row_limit — rows capped, truncated true, no error raised
    Given an IndraDB server with 99 vertices
    When I call "query_graphdb" with:
      | db_uri    | indradb://localhost:27615             |
      | query     | {"query": "all_vertices", "args": {}} |
      | row_limit | 50                                    |
    Then "stats.truncated" is true
    And "rows" has exactly 50 entries
    And no error envelope is returned

  # AC-Q1-6 (confirmed) — result count exactly at limit
  Scenario: Result count equals row_limit exactly — truncated false
    Given an IndraDB server with exactly 50 vertices
    When I call "query_graphdb" with row_limit 50 and query for all_vertices
    Then "stats.truncated" is false
    And "rows" has exactly 50 entries

  # AC-Q1-1 (confirmed) — server-side clamp upper bound
  Scenario: row_limit above hard cap of 500 is clamped to 500
    Given an IndraDB server with 600 vertices
    When I call "query_graphdb" with:
      | db_uri    | indradb://localhost:27615             |
      | query     | {"query": "all_vertices", "args": {}} |
      | row_limit | 999                                   |
    Then at most 500 rows are returned
    And "stats.truncated" is true

  # ---------------------------------------------------------------------------
  # Read-only enforcement — Neo4j Cypher allowlist
  # ---------------------------------------------------------------------------

  # AC-Q1-3 (confirmed) — allowed clauses
  Scenario Outline: Read-only Cypher clauses are accepted
    Given a Neo4j database at "bolt://localhost:7687"
    When I call "query_graphdb" with a query using clause <clause>
    Then no READ_ONLY_VIOLATION error is returned

    Examples:
      | clause        |
      | MATCH         |
      | OPTIONAL MATCH|
      | WITH          |
      | RETURN        |
      | WHERE         |
      | UNWIND        |
      | ORDER BY      |
      | SKIP          |
      | LIMIT         |

  # AC-Q1-3 (confirmed) — rejected write verbs
  Scenario Outline: Write-mutating Cypher verbs are rejected with READ_ONLY_VIOLATION
    Given a Neo4j database at "bolt://localhost:7687"
    When I call "query_graphdb" with a query containing the verb <verb>
    Then the response is an error envelope with code "READ_ONLY_VIOLATION"
    And no graph mutation occurs

    Examples:
      | verb       |
      | CREATE     |
      | MERGE      |
      | DELETE     |
      | SET        |
      | REMOVE     |
      | DROP       |
      | LOAD CSV   |

  # AC-Q1-3 (confirmed) — mutating CALL procedure
  Scenario: CALL to a mutating apoc procedure is rejected with READ_ONLY_VIOLATION
    Given a Neo4j database at "bolt://localhost:7687"
    When I call "query_graphdb" with query "CALL apoc.create.node(['Foo'], {})"
    Then the response is an error envelope with code "READ_ONLY_VIOLATION"

  # AC-Q1-3 (confirmed) — CALL subquery with read-only inner body passes
  Scenario: CALL subquery with read-only inner clauses is accepted
    Given a Neo4j database at "bolt://localhost:7687"
    When I call "query_graphdb" with query:
      """
      MATCH (n:Function)
      CALL {
        WITH n
        MATCH (n)-[:CALLS]->(m)
        RETURN m
      }
      RETURN n, m
      """
    Then no READ_ONLY_VIOLATION error is returned

  # AC-Q1-3 (confirmed) — CALL subquery with write inner body is rejected
  Scenario: CALL subquery containing a write clause is rejected with READ_ONLY_VIOLATION
    Given a Neo4j database at "bolt://localhost:7687"
    When I call "query_graphdb" with query:
      """
      MATCH (n:Function)
      CALL {
        WITH n
        CREATE (n)-[:NEW_EDGE]->(:Dummy)
      }
      RETURN n
      """
    Then the response is an error envelope with code "READ_ONLY_VIOLATION"

  # ---------------------------------------------------------------------------
  # Read-only enforcement — IndraDB driver layer
  # ---------------------------------------------------------------------------

  # AC-Q1-4 (confirmed)
  Scenario: IndraDB executor module exports no write symbols
    Given the module "cpp_mcp.graphdb.indradb_query_executor" is imported
    When the module's namespace is inspected for symbols starting with "set_" or "delete"
    Then no such symbols are present

  # ---------------------------------------------------------------------------
  # Cypher string sent to IndraDB — parse error
  # ---------------------------------------------------------------------------

  # AC-Q1-5 (assumed — OQ-Q1-2 PM recommendation)
  Scenario: Cypher-shaped string sent to IndraDB URI returns QUERY_PARSE_ERROR
    Given an IndraDB server at "indradb://localhost:27615"
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                      |
      | query  | MATCH (n:Function) RETURN n.name LIMIT 5       |
    Then the response is an error envelope with code "QUERY_PARSE_ERROR"
    # Tag: assumed — OQ-Q1-2; architect may override if translation is added for v6

  # ---------------------------------------------------------------------------
  # Unsupported IndraDB query type
  # ---------------------------------------------------------------------------

  # AC-Q1-5 (confirmed)
  Scenario: IndraDB query type outside the supported subset returns QUERY_UNSUPPORTED
    Given an IndraDB server at "indradb://localhost:27615"
    When I call "query_graphdb" with:
      | db_uri | indradb://localhost:27615                                   |
      | query  | {"query": "shortest_path", "args": {"from": "v1", "to": "v2"}} |
    Then the response is an error envelope with code "QUERY_UNSUPPORTED"

  # ---------------------------------------------------------------------------
  # Parse errors
  # ---------------------------------------------------------------------------

  # AC-Q1-7 (confirmed) — malformed Cypher
  Scenario: Malformed Cypher syntax returns QUERY_PARSE_ERROR
    Given a Neo4j database at "bolt://localhost:7687"
    When I call "query_graphdb" with query "MATCH (n RETURN n"
    Then the response is an error envelope with code "QUERY_PARSE_ERROR"

  # AC-Q1-7 (confirmed) — malformed IndraDB JSON
  Scenario: Malformed IndraDB JSON query returns QUERY_PARSE_ERROR
    Given an IndraDB server at "indradb://localhost:27615"
    When I call "query_graphdb" with query "{query: all_vertices}"
    Then the response is an error envelope with code "QUERY_PARSE_ERROR"

  # ---------------------------------------------------------------------------
  # Timeout boundary conditions
  # ---------------------------------------------------------------------------

  # AC-Q1-8 (confirmed) — query exceeds timeout
  Scenario: Query exceeding the configured timeout returns QUERY_TIMEOUT
    Given a Neo4j database at "bolt://localhost:7687"
    And "CPP_MCP_QUERY_TIMEOUT_SECONDS" is set to "1"
    And the query is artificially delayed beyond 1 second (mocked)
    When I call "query_graphdb" with a valid MATCH query
    Then the response is an error envelope with code "QUERY_TIMEOUT"

  # AC-Q1-8 (confirmed) — clamp low end
  Scenario: CPP_MCP_QUERY_TIMEOUT_SECONDS below 1 is clamped to 1
    Given "CPP_MCP_QUERY_TIMEOUT_SECONDS" is set to "0"
    When the server resolves the effective timeout
    Then the effective timeout is 1 second

  # AC-Q1-8 (confirmed) — clamp high end
  Scenario: CPP_MCP_QUERY_TIMEOUT_SECONDS above 120 is clamped to 120
    Given "CPP_MCP_QUERY_TIMEOUT_SECONDS" is set to "999"
    When the server resolves the effective timeout
    Then the effective timeout is 120 seconds

  # ---------------------------------------------------------------------------
  # Connection and dependency failure modes
  # ---------------------------------------------------------------------------

  # AC-Q1-7 (confirmed)
  Scenario: Unreachable database URI returns CONNECTION_FAILED
    When I call "query_graphdb" with db_uri "bolt://192.0.2.1:7687" (unreachable)
    Then the response is an error envelope with code "CONNECTION_FAILED"

  # AC-Q1-7 (confirmed) — missing graphdb optional dependency
  Scenario: query_graphdb called when Neo4j driver package is not installed returns DEPENDENCY_MISSING
    Given the "neo4j" Python package is not importable in this environment
    When I call "query_graphdb" with db_uri "bolt://localhost:7687"
    Then the response is an error envelope with code "DEPENDENCY_MISSING"

  Scenario: query_graphdb called when IndraDB driver package is not installed returns DEPENDENCY_MISSING
    Given the "indradb" Python package is not importable in this environment
    When I call "query_graphdb" with db_uri "indradb://localhost:27615"
    Then the response is an error envelope with code "DEPENDENCY_MISSING"

  # ---------------------------------------------------------------------------
  # Tool registration invariants
  # ---------------------------------------------------------------------------

  # AC-Q1-9, AC-Q1-10, AC-Q2-8 (confirmed)
  Scenario: Server registers exactly 9 tools including query_graphdb and describe_graph_schema
    Given the MCP server is started
    When the tool registry is inspected
    Then exactly 9 tools are registered
    And the tool named "query_graphdb" is present
    And the tool named "describe_graph_schema" is present
    And no registered tool name starts with "cpp_"


Feature: describe_graph_schema — live schema discovery via MCP tool
  # Maps to US-V6-Q2 (AC-Q2-1..AC-Q2-8)
  # Tool registered in src/cpp_mcp/tools/describe_graph_schema.py

  # ---------------------------------------------------------------------------
  # Happy path — Neo4j backend
  # ---------------------------------------------------------------------------

  # AC-Q2-1, AC-Q2-2, AC-Q2-3 (confirmed)
  Scenario: Describe schema of a populated Neo4j graph
    Given a Neo4j database at "bolt://localhost:7687" with Function and CALLS data
    When I call "describe_graph_schema" with:
      | db_uri | bolt://localhost:7687 |
    Then the response contains "backend" equal to "neo4j"
    And the response contains "schema_version" equal to "v1"
    And "node_types" is a list of objects each with "name", "count", "property_keys", "sample_ids"
    And "edge_types" is a list of objects each with "name", "count", "property_keys"
    And "totals" contains "vertices" and "edges" as integers
    And "notes" is a non-empty list of strings
    And "request_id" is a non-empty string

  # AC-Q2-3 (confirmed) — no apoc dependency
  Scenario: Neo4j schema discovery uses only db.labels and db.relationshipTypes procedures
    Given the neo4j driver is instrumented to record Cypher calls
    When I call "describe_graph_schema" against Neo4j
    Then the calls include "CALL db.labels()" and "CALL db.relationshipTypes()"
    And no call references an "apoc." procedure

  # ---------------------------------------------------------------------------
  # Happy path — IndraDB backend
  # ---------------------------------------------------------------------------

  # AC-Q2-1, AC-Q2-2, AC-Q2-4 (confirmed)
  Scenario: Describe schema of a populated IndraDB graph
    Given an IndraDB server with 99 vertices (6 types) and 180 edges (2 types)
    When I call "describe_graph_schema" with:
      | db_uri | indradb://localhost:27615 |
    Then "backend" equals "indradb"
    And "node_types" lists exactly 6 entries (Variable, TypeAlias, Function, Class, Namespace, File)
    And "edge_types" lists exactly 2 entries (DEFINES, REFERENCES)
    And "totals.vertices" equals 99 and "totals.edges" equals 180

  # ---------------------------------------------------------------------------
  # Stable ordering
  # ---------------------------------------------------------------------------

  # AC-Q2-5 (confirmed)
  Scenario: node_types and edge_types are ordered by count descending then name ascending
    Given an IndraDB server with Function(21), Variable(33), TypeAlias(28) and two edge types DEFINES(98) REFERENCES(82)
    When I call "describe_graph_schema"
    Then "node_types" order is: Variable(33), TypeAlias(28), Function(21), ... (count desc)
    And when two types have equal count, they appear alphabetically by name
    And "edge_types" order is: DEFINES(98), REFERENCES(82)

  # ---------------------------------------------------------------------------
  # sample_size boundary conditions
  # ---------------------------------------------------------------------------

  # AC-Q2-1 (confirmed) — clamp low end
  Scenario: sample_size below 10 is clamped to 10
    Given an IndraDB server
    When I call "describe_graph_schema" with sample_size 5
    Then the server uses sample_size 10 for property enumeration

  # AC-Q2-1 (confirmed) — clamp high end
  Scenario: sample_size above 1000 is clamped to 1000
    Given an IndraDB server
    When I call "describe_graph_schema" with sample_size 5000
    Then the server uses sample_size 1000 for property enumeration

  # AC-Q2-1 (confirmed) — default
  Scenario: sample_size defaults to 100 when not supplied
    Given an IndraDB server
    When I call "describe_graph_schema" with no sample_size parameter
    Then the server uses sample_size 100 for property enumeration

  # ---------------------------------------------------------------------------
  # Empty graph
  # ---------------------------------------------------------------------------

  # AC-Q2-7 (confirmed)
  Scenario: describe_graph_schema against an empty graph returns empty lists with no error
    Given an IndraDB server containing no vertices or edges
    When I call "describe_graph_schema" with:
      | db_uri | indradb://localhost:27615 |
    Then the response is not an error envelope
    And "node_types" equals []
    And "edge_types" equals []
    And "totals.vertices" equals 0
    And "totals.edges" equals 0

  # ---------------------------------------------------------------------------
  # Credential non-echo
  # ---------------------------------------------------------------------------

  # AC-Q2-6 (confirmed)
  Scenario: db_uri containing embedded credentials is not echoed in the response
    Given a Neo4j database at "bolt://admin:s3cr3t@localhost:7687"
    When I call "describe_graph_schema" with that db_uri
    Then the response does not contain the string "s3cr3t"
    And the response does not contain the full db_uri string

  # ---------------------------------------------------------------------------
  # Schema-version mismatch note
  # ---------------------------------------------------------------------------

  # OQ-Q2-1 (needs-clarification) — architect must confirm constant name and mismatch detection logic
  Scenario: Schema version mismatch between writer schema and live graph surfaces a warning note
    Given a graph ingested under writer schema-version "v0"
    And the current server schema-version constant is "v1"
    When I call "describe_graph_schema"
    Then "notes" contains a string indicating the graph was ingested under a different schema version
    # Tag: needs-clarification — OQ-Q2-1; implementation depends on architect's choice of constant name
    #   and how version is stored in the graph (node property, graph metadata, etc.)

  # ---------------------------------------------------------------------------
  # Failure modes shared with query_graphdb
  # ---------------------------------------------------------------------------

  # AC-Q2-1, AC-Q1-7 reuse (confirmed)
  Scenario: describe_graph_schema against unreachable URI returns CONNECTION_FAILED
    When I call "describe_graph_schema" with db_uri "bolt://192.0.2.1:7687" (unreachable)
    Then the response is an error envelope with code "CONNECTION_FAILED"

  Scenario: describe_graph_schema when driver package missing returns DEPENDENCY_MISSING
    Given the "neo4j" Python package is not importable
    When I call "describe_graph_schema" with db_uri "bolt://localhost:7687"
    Then the response is an error envelope with code "DEPENDENCY_MISSING"
```

---

## References

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v6/requirements.md` — primary source (US-V6-Q1..Q4, all ACs)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v6/CHARTER.md` — traceability rules
- `[[pages/planning/cpp-mcp-codexgraph-gap]]` — gap roadmap (S1 = this handoff)
- `[[pages/code/cpp-mcp-v5]]` — predecessor; rename-invariant and tool-count baseline
- `[[project-v4-live-verification]]` — pinned graph counts (99V/180E, 21 Function, 6 node types, 2 edge types)
- Cognee tags: `task:cpp-mcp-v6`, `role:business-analyst`
