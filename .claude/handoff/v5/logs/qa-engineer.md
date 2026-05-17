---
role: qa-engineer
task-slug: cpp-mcp-v5-rename
date: 2026-05-17
model: claude-sonnet-4-6
---

# QA Engineer Log — cpp-mcp-v5-rename

## Summary

QA consolidated all 4 stories (S1-S4) in a single pass per the dispatch contract.

## Hard gates verified

All 6 cross-story gates passed:
- ruff format --check: 98 files formatted
- ruff check: 0 errors
- ADR-21 grep gate (grep -RIE cpp_(get|export)_ src/ tests/): exit 1, no matches
- pytest (unit): 618 passed, 6 skipped (v4 parity confirmed)
- pytest -m integration: 16 passed, 2 skipped (INDRADB_TEST_URI not set — env-gated, not regression)
- pyproject.toml version: 0.3.0
- CHANGELOG.md: 0.3.0 + ingest_code confirmed
- Registry shape: 7 tools, no cpp_ prefix, ingest_code present

## Defects

None. 0 open QA_DEFECT entries.

## Additions made

New file: tests/unit/test_rename_invariant.py (24 tests)
Category: parametrised/mutation + grep-gate-as-pytest

Key coverage added:
1. AC-R4-3 / EC-1: parametrised dispatch rejection of all 7 old cpp_* names via fastmcp.exceptions.NotFoundError
2. EC-3: property invariant — no registered name contains "cpp_" substring
3. AC-R2-4 / EC-5: ADR-21 grep gate surfaced as pytest assertion (regression-detectable in test suite)

All 24 new tests pass. Full suite: 642 passed, 6 skipped (18 deselected), 1 warning.

## Key finding: integration parity

Integration count is 16 passed + 2 skipped (not 18 passed) because INDRADB_TEST_URI is not set.
The v4 baseline of 18 was measured with a live IndraDB daemon. This is an environment constraint,
not a regression. Recorded as obs-1 in test-report.md (advisory, non-blocking).

## References

- test-report.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/test-report.md
- new test file: /Users/husam/workspace/cpp-mcp/tests/unit/test_rename_invariant.py
- implementation-notes.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/implementation-notes.md
