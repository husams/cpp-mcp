role: business-analyst
task-slug: cpp-mcp-v7-s2
date: 2026-05-17
status: complete

## Inputs read

- /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md
- wiki: pages/planning/cpp-mcp-v7-full-ast-schema (index lookup)
- wiki: pages/code/cpp-mcp-v7-s1 (index lookup)

## Deliverable

/Users/husam/workspace/cpp-mcp/.claire/handoff/v8/scenarios.md

Actual path: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/scenarios.md

## Summary

- 8 stories (S2-A through S2-H) covered.
- 41 AC tags mapped across scenarios.
- 8 dispatch-named edge cases included (EC-1 through EC-11 relevant ones; SC-A-03/04, SC-B-05, SC-C-02, SC-C-03, SC-E-04/05, SC-F-10/11, SC-F-06/07, SC-G-03).
- 1 failure-mode scenario (SC-FM-01, assumed tag).
- 3 open questions flagged with needs-clarification (OQ1: ctor/dtor RETURNS, OQ2: int** depth, OQ3: signature source) — all require ADR-26.
- Deferred items (is_template, is_virtual, is_override, OVERRIDES, INSTANTIATES, Enum, IndraDB verb) explicitly excluded.
- Backward-compat scenarios SC-H-04 and SC-H-05 cover v1 and v2-from-S1 graph loading.
- record_kind uses Scenario Outline (class/struct/union) for conciseness.

## Open questions count: 3

1. Constructor/destructor RETURNS rule — ADR-26 required (S2-E.AC4, SC-E-04, SC-E-05).
2. int** POINTS_TO chain depth — ADR-26 required (S2-B.AC4, SC-B-05).
3. Canonical signature string source — ADR-26 required (S2-F.AC1, SC-F-01-sig).
