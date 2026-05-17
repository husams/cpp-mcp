Files written:
  /Users/husam/workspace/wiki/pages/code/cpp-mcp-v6.md  (enriched from stub — doc-writer stage)
  /Users/husam/workspace/wiki/index.md                   (v6 entry updated: sources 3→10, pin counts added)
  /Users/husam/workspace/wiki/log.md                     (enrichment entry prepended)
  /Users/husam/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md  (status: draft → active, S1 shipped)

Verification:
  IndraDB verb set cross-checked: adr-23.md + src/cpp_mcp/graphdb/indradb_query_executor.py
  (_ALLOWED_VERBS frozenset matches ADR-23 table — 7 verbs: all_vertices, all_edges,
  vertex_with_type, edge_with_type, vertex_with_property_equal, edge_with_property_equal, pipe)
  ADR files confirmed present: .claude/handoff/v6/adr-22.md, adr-23.md, adr-24.md
  Test counts sourced from test-report.md: 880 unit+BDD passed, 10 integration passed
  Integration pins sourced from requirements.md AC-Q3-1/Q3-2 + test-report.md scenario table

Corrections made (not propagated):
  runbook.md GitHub release notes block lists wrong IndraDB verb names
  (vertex_with_id, edge_with_id, edge_between_vertices). Authoritative source is adr-23.md
  and the implementation. The wiki and docs-changes.md use the correct 7-verb set.
  The devops runbook.md error is noted here but not fixed (outside doc-writer scope).

  Stub test counts were stale: "642+ passed, 18+ integration" corrected to
  "880 passed, 10 integration" per test-report.md.

Cross-links:
  [[pages/code/cpp-mcp-v6]] → [[pages/code/cpp-mcp-v5]] → [[pages/code/cpp-mcp]]
  [[pages/code/cpp-mcp-v6]] → [[pages/planning/cpp-mcp-codexgraph-gap]]
  [[pages/planning/cpp-mcp-codexgraph-gap]] → [[pages/research/codexgraph]]

References:
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/requirements.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/design.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/test-report.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/deploy-notes.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/runbook.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/adr-22.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/adr-23.md
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/adr-24.md
  /Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/indradb_query_executor.py
  Cognee tags: task:cpp-mcp-v6, role:doc-writer
