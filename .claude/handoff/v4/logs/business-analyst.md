---
role: business-analyst
run_id: cpp-mcp-v4
date: 2026-05-17
status: complete
---

## Sources read

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/CHARTER.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/requirements.md`
- `/Users/husam/.claude/projects/-Users-husam-workspace-cpp-mcp/memory/project_graphdb_v3_post_ship_findings.md`
- Wiki `[[pages/code/cpp-mcp]]` (index grep)
- Skill: `bdd-e2e-testing`

## Deliverable

`/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/scenarios.md`

- 17 scenarios across 7 features (one feature per story)
- Scenario IDs: SC-V4-1-01 through SC-V4-7-02
- All 7 stories covered; all AC IDs mapped (see scenario-to-AC table in scenarios.md)

## Open questions flagged (3)

- OQ-2-1 (needs-clarification): Pinned vertex/edge counts for os.cc post US-V4-3/5; placeholders `<EXPECTED_VERTICES>` / `<EXPECTED_EDGES>` in SC-V4-2-03
- OQ-3-1 (needs-clarification): Neo4j MERGE live-daemon test vs code-review-only; no scenario written; architect/stakeholder to resolve
- OQ-6-1 (needs-clarification): Docker fixture: cargo-only vs senussi registry image; SC-V4-6-01 written for cargo-only outcome; update if ADR chooses registry

## Edge cases covered

- `INDRADB_TEST_URI` unset → skip (SC-V4-2-01)
- `INDRADB_AUTOSTART=0` + daemon unreachable → skip not fail (SC-V4-2-02)
- Idempotent re-export → both counts == 0 (SC-V4-2-04)
- Missing graphdb extras → DEPENDENCY_MISSING with --extra flag (SC-V4-7-02)
- Fresh venv import → no TypeError (SC-V4-4-02)
- `uv run pytest` no env → zero failures (SC-V4-1-04)

## Decisions / assumptions

- US-V4-3 AC-3-3 (Neo4j MERGE code-review): no Gherkin scenario written; out of scope for BDD
- US-V4-6 BDD is a poor fit for "README contains string X"; two structural-grep scenarios used instead
- AC-2-5 pinned counts deferred to QA engineer post US-V4-3/5 landing
- Seven tool smoke tests collapsed into Scenario Outline (SC-V4-1-03)
