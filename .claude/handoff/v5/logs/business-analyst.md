role: business-analyst
run_id: cpp-mcp-v5-rename
date: 2026-05-17
status: complete

## Summary

Drafted /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/scenarios.md covering:
- 4 stories (US-V5-R1..R4), 17 scenarios total, all AC IDs tagged.
- Scenario Outline for all 7 old→new wire-name renames (AC-R1-1/R1-4, AC-R4-3).
- Hard-gate scenarios: pytest parity (618/6 unit, 18 integration), grep gate (zero cpp_ hits in src/tests/).
- Negative path: client calling old name gets MCP "tool not found".
- Boundary: test count ceiling (no phantom additions), argument schema identity check.
- 3 open questions flagged (cache keys, source file path scope, grep scope vs exception list).
- 2 assumptions recorded (no-compat-alias tension resolved, parity counts sourced from v4 baseline).

## Open questions raised

- OQ-1: Cache key scope (NFR "untouched" ambiguity) — needs-clarification, architect.
- OQ-2: Source file path rename scope (file vs symbol) — needs-clarification, architect.
- OQ-3: Grep gate command vs exception list scope mismatch — needs-clarification, QA.

## Artifacts

- scenarios.md written at handoff/v5/scenarios.md
- No source code read or modified.
