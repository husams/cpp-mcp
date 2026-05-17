# Architect log — cpp-mcp v7 S1

run_id: cpp-mcp-v7-s1
date: 2026-05-17

## Inputs read
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/scenarios.md
- src/cpp_mcp/graphdb/{exporter,schema,schema_version,schema_introspector,neo4j_driver,indradb_driver}.py

## Outputs written
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md (Status: accepted)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/design.md

## Open questions resolved
- OQ-1 (Variable transition): deprecate on write, tolerate on read. Both
  backends are single-label/single-type; multi-label is a refactor out of
  S1 scope.
- OQ-2 (anonymous struct/union): emit fields as Field, MEMBER_OF to nearest
  named enclosing class.
- OQ-3 (union default access): public per C++ spec; libclang verification in
  implementation-notes.
- OQ-4 (access on all MEMBER_OF or only Field): all MEMBER_OF edges.
- OQ-5 (storage_class on Field): "none" string.
- OQ-6 (Field is_static invariant): enforce at classification; static field
  → GlobalVariable unconditionally.
- OQ-7 (describe lists Variable if retained): no special case; live
  introspector surfaces whatever is in the graph.

## Gaps surfaced during architectural review
- PARM_DECL has no clean target in S1; kept as Variable transitionally.
  Removal lands in S2 with Parameter node.
- schema_version constant is a string ("v1"). Bump to "v2", NOT integer 2.
  Requirements/scenarios prose uses "2"; design.md flags this for QA.

## Charter typo
CHARTER.md and dispatch reference src/cpp_mcp/graphdb_export/. Actual path
is src/cpp_mcp/graphdb/. Flagged in ADR-25 and design.md.
