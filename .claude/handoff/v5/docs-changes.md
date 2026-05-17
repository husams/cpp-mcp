Files written:
  /Users/husam/workspace/wiki/pages/code/cpp-mcp-v5.md          (new wiki delta page)
  /Users/husam/workspace/wiki/index.md                           (1 entry added for cpp-mcp-v5; cpp-mcp-codexgraph-gap description fixed)
  /Users/husam/workspace/wiki/log.md                             (1 entry appended)
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/docs-changes.md  (this file)

Verification:
  Commands quoted verbatim from runbook.md and deploy-notes.md — no invented flags or paths.
  Operator runbook section reproduces shell commands from /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/runbook.md §Steps 1–6 and §Verification.
  Rollback commit sha `1ac03ad` taken verbatim from deploy-notes.md line 109 / runbook.md line 169.
  Test counts sourced from test-report.md: 618/6 parity baseline, 642/6 unit total, 16/2 integration (no daemon), 18/0 with live IndraDB.
  Version field discrepancy noted: pyproject.toml was 0.1.0 pre-v5 (not 0.2.0); documented in wiki page.

Cross-links:
  [[pages/code/cpp-mcp]]                          (base page — updated by S3 dev, not touched here)
  [[pages/code/cpp-mcp-v4]]                       (predecessor — updated by S3 dev, not touched here)
  [[pages/planning/cpp-mcp-codexgraph-gap]]       (roadmap — index description fixed here; page body updated by S3 dev)
  /Users/husam/workspace/cpp-mcp/README.md        (Migration from 0.2.x section — updated by S3 dev)
  /Users/husam/workspace/cpp-mcp/CHANGELOG.md     (created by S4 dev)
  /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/runbook.md

Index fix noted:
  Line 27 of index.md previously read `S1 'cpp_query_graphdb'` — stale from before S3 updated the planning page body.
  Updated to `'query_graphdb'` and `'translate_query'` to match the unprefixed scheme confirmed in implementation-notes.md §S3 wiki pages.

Cognee ingest:
  SKIPPED — cognee returned HTTP 503 (no healthy upstream) on two attempts (devops run + doc-writer retry).
  No action required; wiki page and docs-changes.md are durable on disk.

References:
  Handoff inputs: /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/{CHARTER,requirements,implementation-notes,test-report,deploy-notes,runbook}.md
  Cognee tags: task:cpp-mcp-v5-rename, role:doc-writer
