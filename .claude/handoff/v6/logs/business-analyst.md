# Business Analyst Log — cpp-mcp-v6
# role: business-analyst
# date: 2026-05-17
# run_id: cpp-mcp-v6

## Inputs read
- CHARTER.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/CHARTER.md
- requirements.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/requirements.md
- wiki index: ~/workspace/wiki/index.md (cpp-mcp-v4, cpp-mcp-v5, cpp-mcp pages referenced)

## Output
- scenarios.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/scenarios.md

## Coverage summary
- US-V6-Q1 (query_graphdb): 30 scenarios covering happy paths (Neo4j + IndraDB all query types), row-cap boundaries (under/at/above/exceeds cap, clamp to 500), read-only enforcement (9 allowed clauses, 7 rejected write verbs, mutating CALL proc, CALL subquery read-only inner pass, CALL subquery write inner reject), IndraDB-no-write-symbols check, Cypher-to-IndraDB parse error, unsupported IndraDB query type, malformed Cypher, malformed IndraDB JSON, timeout exceeded, timeout env-var clamp low/high, CONNECTION_FAILED, DEPENDENCY_MISSING (both backends), tool registration count=9 + no cpp_ prefix.
- US-V6-Q2 (describe_graph_schema): 12 scenarios covering Neo4j happy path (db.labels/db.relationshipTypes, no apoc), IndraDB happy path (6 types/2 edge types), stable ordering (count desc then name asc), sample_size clamp low/high/default, empty graph, credential non-echo, schema-version mismatch note (needs-clarification), CONNECTION_FAILED, DEPENDENCY_MISSING.

## Open questions flagged
- OQ-Q1-1: Cypher AST enforcement strategy (needs-clarification — architect, ADR-22)
- OQ-Q1-2: Cypher string on IndraDB URI (needs-clarification — confirmed as QUERY_PARSE_ERROR per PM; scenario tagged "assumed")
- OQ-Q2-1: schema_version mismatch note behavior (needs-clarification — architect, constant name + storage location)

## Edge cases with no further cases identified
- No additional boundary conditions beyond those in requirements.md and dispatch notes.
