# architect log — cpp-mcp-v6
Date: 2026-05-17

## Inputs read
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/CHARTER.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/requirements.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/scenarios.md
- src/cpp_mcp/graphdb/{driver,indradb_driver,neo4j_driver,exporter,schema,__init__}.py
- src/cpp_mcp/tools/ingest_code.py
- src/cpp_mcp/core/error_envelope.py
- .claude/handoff/v3/adr-12.md (URI dispatch precedent)

## Outputs
- design.md (14 sections; module layout, protocols, validation order, coercion, timeouts, tests)
- adr-22.md — Cypher read-only via Neo4j EXPLAIN plan inspection (accepted; OQ-Q1-1 resolved)
- adr-23.md — IndraDB JSON query subset, 7 verbs (accepted; OQ-Q1-2 resolved — no translation in v6)
- adr-24.md — Live schema discovery + writer-stamped SCHEMA_VERSION on File nodes (accepted; OQ-Q2-1 resolved)

## Key decisions
- Parallel `QueryExecutor` / `SchemaIntrospector` protocols (not extensions of `GraphDriver`) so write surface stays write-only and AC-Q1-4 module purity is a 1-line assertion.
- New ErrorCodes added to error_envelope.py: READ_ONLY_VIOLATION, QUERY_PARSE_ERROR, QUERY_UNSUPPORTED, QUERY_TIMEOUT. CONNECTION_FAILED is aliased to existing DB_UNREACHABLE in tool docstrings (no enum bloat).
- Writer side (exporter.py) gets one additive change: stamp `schema_version = SCHEMA_VERSION` on every File node. Existing graphs without the prop surface a "pre-v6" warning.
- IndraDB timeout enforced via `session.executor.submit(...).result(timeout=...)` (reuse existing single-worker pool from clang_session).
- Neo4j EXPLAIN-plan walk uses prefix-matching on write operator names + small allowlist for `db.*` read procedures; fail-closed on unknown operators.

## Open questions surfaced for downstream
- IndraDB Python client v3.x exact class names for `VertexWithPropertyValueQuery` / `PipeQuery` need verification at implementation time against the pinned version (noted in design §13).
- Neo4j operator name set across 4.x/5.x — record fixture in CI to catch drift (noted in design §13).

## Return
deliver: design.md, adr-22.md, adr-23.md, adr-24.md
status:  clear (all 3 ADRs Status: accepted)
adr-count: 3
