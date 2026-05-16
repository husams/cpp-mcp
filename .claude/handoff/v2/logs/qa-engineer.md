---
run_id: fastmcp-migration-v2
stage: qa-engineer
date: 2026-05-16
task-slug: fastmcp-migration
---

# QA Engineer Log: FastMCP Migration (v2)

## Session summary

Executed full acceptance + regression test pass across stories S1–S7 for the FastMCP migration.

## Gates checked

- ruff format --check: PASS
- ruff check: PASS
- mypy --strict src/ (29 files): PASS
- uv lock --check: PASS
- Structural invariants (stdio_transport.py absent, http_transport.py absent, schemas.py absent, no async def in tools/, no _TOOL_SPECS/_HANDLERS, ADR-10 superseded, runbook present): ALL PASS
- Full pytest suite: 472 passed, 4 skipped (baseline 327+1 exceeded)

## QA additions

Added `tests/unit/test_warn_non_loopback_qa.py` (15 mutation/boundary tests) covering adversarial non-loopback address spellings not present in the developer's test set (SC_USM2_3, SC_USM2_3b). All 15 pass.

## Defects

None (0 open QA_DEFECT entries). I4 gate is clear.

## Observations forwarded to test-report.md

1. PytestUnknownMarkWarning for 5 scenario-tag marks not registered in pyproject.toml.
2. SC_USM7_3 lacks explicit parse_count==1 cache stats assertion (advisory).
3. SC_USM1_3 covered via individual BDD files rather than outline form (coverage equivalent).
