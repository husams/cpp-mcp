---
run_id: graphdb-multi-v3
stage: senior-developer
mode: plan
date: 2026-05-16
deliverable: /Users/husam/workspace/cpp-mcp/.claude/handoff/v3/plan.md
---

# senior-developer log — plan mode

## Inputs read

- CHARTER.md — confirmed invariants I1/I2/I3; project lang=python; uv.lock present.
- requirements.md — 6 stories US-G1..US-G6 with ACs; compatibility constraints C-G1..C-G8.
- scenarios.md — Gherkin coverage for all ACs including BDD live-daemon gating.
- design.md — module map, dispatch sketch, IndraDB class shape, error wiring, packaging.
- adr-12.md (dispatch), adr-13.md (DEPENDENCY_MISSING), adr-14.md (USR→UUID), adr-15.md (props). All Status: accepted (I2 satisfied).
- pyproject.toml — current state: single `graphdb` extra with `neo4j>=5.0`; ruff line-length=100; mypy strict.

## Plan structure rationale

Split into 6 stories matching the 6 user stories with explicit dependency edges:

1. S1 (DEPENDENCY_MISSING code) — foundation; both drivers need this exception class. Also fixes the v2 miswire at neo4j_driver.py:51-54.
2. S2 (IndraDBDriver) — net-new module; depends on S1's exception class. Uses fake `indradb` shim for unit tests (no live daemon).
3. S3 (select_driver + tool wiring) — replaces the v2 `make_driver` with scheme-dispatch; reorders validation so unknown-scheme INVALID_ARGUMENT fires before path checks.
4. S4 (extras split) — packaging hygiene; parallel-safe with S1/S2.
5. S5 (BDD) — feature file + step impls + docker compose fragment; depends on S2+S3.
6. S6 (docs) — README/runbook/wiki; last stage.

Parallel-safe count = 2 (S1+S4 or S2+S4 early; subsequent stories serialized).

## Exit-criteria discipline

Every story has explicit:
- `ruff format --check` (formatter gate → BUILD_FAIL signal)
- `ruff check` (lint gate → LINT_FAIL signal)
- `mypy` on touched src/ files (strict mode per pyproject)
- `pytest -q` on new tests + full suite (test gate → TEST_FAIL signal)

S4 additionally runs `uv sync` + `uv pip list | grep` to enforce C-G5 (default install pulls neither neo4j nor indradb).

S6 uses `grep -q` checks against runbook/README/wiki for the documentation ACs.

## Open notes for developer

- S3 must grep `make_driver` across repo before deleting it (no live callers expected per design §4, but verify).
- S2 must keep `import indradb` lazy inside `connect()` — at-module-top import would violate C-G5.
- `NS_CPPMCP_USR` UUID literal must be copied verbatim from adr-14.md to avoid drift.
- Exception class ordering in `_EXC_TO_CODE` (DependencyMissingError above DBUnreachableError) is enforced by a dedicated unit test in S1.

## Validation against MISSING_EXIT_CRITERIA failure code

Every one of the 6 stories has at least 3 exit-criteria commands. No story is left without a measurable gate. No `MISSING_EXIT_CRITERIA` signal raised.

## Return

deliverable written; ready for coordinator → developer dispatch.
