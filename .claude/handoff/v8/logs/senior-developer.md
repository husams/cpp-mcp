# senior-developer log — cpp-mcp v7 S2 plan

Date: 2026-05-17
Role: senior-developer (plan mode)
Task: cpp-mcp-v7-s2

## Inputs read
- CHARTER.md
- requirements.md (S2-A..S2-H, deferred items)
- design.md (helpers, walk-cursor integration §3, file map §5)
- adr-26.md (Status: accepted; D1–D11)
- scenarios.md (SC-A-01..SC-FM-01, AC coverage index)

## Decomposition rationale
7 stories chosen, sequenced P1→P7. Tightly coupled `exporter.py` edits split by feature surface:
- P1 schema constants (no behavior)
- P2 Type node + helper + chain (foundational helper before any caller)
- P3 Parameter + PARM_DECL reclassification (must precede OF_TYPE wiring on Parameter)
- P4 OF_TYPE + RETURNS (finalizes function-block emissions atomically)
- P5 Function signature props (independent prop bag; cleanly slotted after P4)
- P6 Class props + UNION_DECL (independent of P5)
- P7 schema surface + compat + live smoke (no src/ edits; can run parallel to P6)

Parallel-safe: P6 ∥ P7 after P5 lands. Disjoint file surface.

## Exit-criteria pattern
Every story has identical 3-command baseline (ruff format, ruff check, pytest unit -x -q) plus a story-scoped pytest subset to fail-fast during dev. P7 adds integration tests.

## ADR-bound expected churn
ADR-26 D9 enumerates 4 test files needing updates (PARM_DECL → Parameter migration) and 3 files that MUST remain unchanged (v1 read-compat). Plan calls these out under P3 + P7 so QA does not flag as regression.

## Open issues flagged (non-blocking)
- SC-D-02 label literal: local VAR_DECL emits as `GlobalVariable` per ADR-25 (NOT reclassified in S2). Plan documents this under P4 with a test-side comment.
- Live smoke risks (P7): IndraDB executor may surface INTERNAL_ERROR on new edge types (parallel to v6 findings); plan instructs to file into log, not block S2 close.

## Deliverable
`/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/plan.md` — 7 stories, parallel-safe:2.
