run_id: cpp-mcp-v7-s2
handoff_dir: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/

Blackboard paths (authoritative):
  requirements:   /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements.md
  scenarios:      /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/scenarios.md
  design:         /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/design.md
  adrs:           /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-<n>.md   (next free n=26)
  plan:           /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/plan.md
  impl-notes:     /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/implementation-notes.md
  impl-notes-per: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/logs/developer-<story-slug>.md
  test-report:    /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/test-report.md
  deploy-notes:   /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/deploy-notes.md
  runbook:        /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/runbook.md
  docs-changes:   /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/docs-changes.md
  logs:           /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/logs/<role>.md

Project context:
  project-root: /Users/husam/workspace/cpp-mcp
  language: python (toolchain: uv, ruff, pytest; libclang for AST extraction)
  current state after S1 (commit 774cd66): schema_version="v2", 1020 unit / 6 skip / 0 fail
  pyproject: 0.4.0 (target after S6: 0.5.0; S2 alone does NOT bump pyproject)
  upstream PRD: ~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md
  prior stage: ~/workspace/cpp-mcp/.claude/handoff/v7/ (S1 — Variable split + MEMBER_OF.access)
  prior stage wiki: ~/workspace/wiki/pages/code/cpp-mcp-v7-s1.md
  scope this run: STAGE S2 ONLY (Type node + RETURNS/OF_TYPE/HAS_PARAM edges + Parameter node + function signature props)
  out of scope: S3–S6 (Templates/Concept, Virtual/Override/Friend, Enums/Namespaces/Aliases, IndraDB ordered traversal)

Cross-stage invariants (same as v7):
  I1. requirements.md MUST contain acceptance criteria before architect dispatch.
  I2. All adr-*.md Status MUST NOT be "proposed" before developer dispatch.
  I3. plan.md MUST list exit-criteria commands before any developer dispatch.
  I4. test-report.md MUST exist with no open QA_DEFECT entries before devops dispatch.

Traceability chain:
  story → ADR → code (plan.md files-to-touch) → test (test-report.md)
  Every plan.md story MUST reference the AC IDs it satisfies.
  Every test in test-report.md MUST reference the scenario ID it covers.

Failure taxonomy (same as v7):
  MISSING_ACCEPTANCE_CRITERIA · ADR_UNRESOLVED · MISSING_EXIT_CRITERIA
  TEST_FAIL · LINT_FAIL · BUILD_FAIL · REVIEW_BLOCK · QA_DEFECT · DEPLOY_DRIFT

Retry termination rule: max 3 retry passes per signal set; surface to user if not resolved.
Handoff rule: all cross-agent data passes as file paths; never inline content from one agent into another dispatch.

S2 deployment note:
  cpp-mcp is a Python MCP server library; "devops" scope = packaging/version-tag checks only,
  no k8s context required. CHARTER "n/a — library package, no cluster target" applies.

S2 schema additions (from PRD §"New node types" and §"New / refined edge types"):
  New nodes:
    - Type (canonical type spelling; pointer/ref/qualified/template-instantiation)
    - Parameter (positional function/template parameter; props: index, name, default_value)
  New edges:
    - RETURNS — Function → Type
    - HAS_PARAM — Function → Parameter (ordered by index)
    - OF_TYPE — Parameter/Variable/Field → Type
    - POINTS_TO — Type → Type (pointer pointee)
    - REFERS_TO — Type → Type (reference referent)
  New Function properties:
    - signature (canonical), is_template, is_virtual, is_override, is_constexpr,
      is_noexcept, is_deleted, is_defaulted, cv_qualifiers, ref_qualifier
  Class properties (S2-scoped):
    - is_template, is_final, is_abstract, record_kind (class/struct/union)
    NOTE: is_template, is_virtual, is_override may overlap with S3/S4; mark which are S2 vs deferred.

Backward compat:
  - schema_version stays "v2" (already bumped in S1); S2 enriches v2 additively.
  - v1 graphs still readable (already proven by S1).
  - v2-from-S1 graphs missing the new Type/Parameter nodes must not cause read errors.
