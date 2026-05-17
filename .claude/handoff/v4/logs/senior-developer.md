# senior-developer log — cpp-mcp-v4

Date: 2026-05-17
Mode: plan
Deliverable: /Users/husam/workspace/cpp-mcp/.claude/handoff/v4/plan.md

Decomposed v4 into 7 stories per dispatch hint, preserving suggested order:
- S1 commit Identifier→str + docstring (bundled per hint)
- S2 pin protobuf<4
- S3 fix inserts-vs-attempts in both drivers (+ ADR-17 Neo4j ResultSummary.counters)
- S4 replace Docker fixture per ADR-16
- S5 in-memory Client harness + tests/integration scaffold (ADR-18)
- S6 live IndraDB e2e against test-repo/fmt/src/os.cc
- S7 README install fix + DEPENDENCY_MISSING wording

Each story carries: explicit absolute file paths, AC IDs, ADR refs, parallel-safe flag, exit-criteria commands (ruff/mypy/pytest plus structural grep guards).

Parallel-safe stories: S2, S4, S7 (S7 after S4 due to README contention).
Sequential chain: S1 → S2 → S3 → S5 → S6.

No MISSING_EXIT_CRITERIA — every story has at least one ruff, one pytest, and one structural assertion.
