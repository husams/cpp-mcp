run_id: cpp-mcp-v6
handoff_dir: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/

Blackboard paths (authoritative):
  requirements:   /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/requirements.md
  scenarios:      /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/scenarios.md
  design:         /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/design.md
  adrs:           /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/adr-<n>.md   (one per decision)
  plan:           /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/plan.md
  impl-notes:     /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/implementation-notes.md
  impl-notes-per: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/logs/developer-<story-slug>.md
  test-report:    /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/test-report.md
  test-report-per:/Users/husam/workspace/cpp-mcp/.claude/handoff/v6/logs/qa-engineer-<story-slug>.md
  deploy-notes:   /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/deploy-notes.md
  runbook:        /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/runbook.md
  docs-changes:   /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/docs-changes.md
  logs:           /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/logs/<role>.md

Project: cpp-mcp (Python / FastMCP). Language: python. Project-root: /Users/husam/workspace/cpp-mcp.

Cross-stage invariants:
  I1. requirements.md MUST contain acceptance criteria before architect dispatch.
  I2. All adr-*.md Status MUST NOT be "proposed" before developer dispatch.
  I3. plan.md MUST list exit-criteria commands before any developer dispatch.
  I4. test-report.md MUST exist with no open QA_DEFECT entries before devops dispatch.

Traceability chain:
  story (requirements.md) → ADR (adr-N.md) → code (plan.md files-to-touch) → test (test-report.md)
  Every plan.md story MUST reference the AC IDs it satisfies.
  Every test in test-report.md MUST reference the scenario ID it covers.

Failure taxonomy (named codes; ownership in parentheses):
  MISSING_ACCEPTANCE_CRITERIA  — requirements.md has a story without AC (product-manager)
  ADR_UNRESOLVED               — adr-*.md Status == "proposed" at dev dispatch time (architect)
  MISSING_EXIT_CRITERIA        — plan.md story has no exit-criteria commands (senior-developer)
  TEST_FAIL                    — exit-gate test command non-zero (developer)
  LINT_FAIL                    — exit-gate lint command non-zero (developer)
  BUILD_FAIL                   — exit-gate build/formatter command non-zero (developer)
  REVIEW_BLOCK                 — review.md verdict == changes-requested with open finding-ids (senior-developer)
  QA_DEFECT                    — test-report.md lists unresolved defect IDs (qa-engineer)
  DEPLOY_DRIFT                 — deploy-notes.md context != current-context at apply time (devops)

Retry termination rule:
  - Developer retry: exits when all LINT_FAIL/TEST_FAIL/BUILD_FAIL codes clear (max 3 passes inside developer).
  - Developer-from-review retry: exits when all REVIEW_BLOCK finding-ids are addressed.
  - Developer-from-qa retry: exits when all QA_DEFECT ids in test-report.md are resolved.
  Max 3 retry passes per signal set; surface to user if not resolved after exhaustion.

Handoff rule: all cross-agent data passes as file paths; never inline content from one agent into another dispatch.

Notes for this run:
  - v6 is additive (no breaking changes). Adds `query_graphdb` + `describe_graph_schema` MCP tools.
  - Existing v5 requirements.md was already drafted ready-for-architect (now mirrored as requirements-raw.md).
  - Target version: pyproject 0.3.0 → 0.4.0. Closes S1 of [[pages/planning/cpp-mcp-codexgraph-gap]].
  - Deploy target: NOT a kubernetes deploy. This is a PyPI-shaped library; devops scope is local install + version bump verification only. No cluster context required.
