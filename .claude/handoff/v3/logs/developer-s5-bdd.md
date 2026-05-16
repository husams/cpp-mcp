---
task: graphdb-multi
story: S5 — IndraDB BDD coverage (US-G5)
role: developer
date: 2026-05-16
model: claude-sonnet-4-6
---

## Skills loaded

- `python-conventions` — toolchain, style, typing, test layout
- `bdd-e2e-testing` — pytest-bdd patterns, step scoping, feature file layout

## Skills considered but not loaded

- `cpp-conventions` — no C++ source code modified
- `implement-story` — task was dispatched directly with plan.md context; skill would add overhead without benefit for a single-story BDD implementation

## Orientation reads

- `CHARTER.md` — run_id, paths, invariants
- `plan.md` — S5 section L206-240; verified exit-criteria commands
- `scenarios.md` — "Feature: IndraDB BDD export coverage" full gherkin
- `tests/fixtures/fake_indradb.py` — confirmed `_fail_on_ping`, `node_count`, `edge_count` already present (no changes needed)
- `tests/bdd/test_export_to_graphdb.py` — shape reference for step duplication pattern
- `tests/bdd/features/export_to_graphdb.feature` — confirmed Gherkin tag/marker style
- `src/cpp_mcp/graphdb/__init__.py` — `select_driver` dispatch; confirmed `_INDRADB_SCHEMES`
- `src/cpp_mcp/graphdb/indradb_driver.py` — `IndraDBDriver.connect` lazy-import pattern
- `src/cpp_mcp/tools/export_to_graphdb.py` — tool signature; confirmed `select_driver` import path
- `pyproject.toml` — existing markers; confirmed `graphdb-indradb` extra and marker list
- `tests/bdd/conftest.py` — ctx fixture; step sharing patterns

## Advisor call — before implementation

Called advisor after orientation. Key guidance acted on:
1. Confirmed `fake_indradb.py` already complete — zero edits needed.
2. Chose `sys.modules["indradb"]` patching for single-invocation tests; `patch("select_driver")` with shared driver for idempotency test.
3. Duplicated given steps (not moved to conftest) per existing pattern.
4. Noted Background @indradb conflict; resolved by making fake-install step a flag-only no-op.
5. Noted 2 @indradb live scenarios → <=2 skip count will be exceeded. Documented as deviation.

## Commands run

```bash
# Baseline suite check
uv run pytest -q 2>&1 | tail -5
# → 548 passed, 4 skipped

# After implementation — S5 only
uv run pytest -q tests/bdd/test_export_to_indradb.py -v
# → 8 passed, 2 skipped (INDRADB_TEST_URI not set)

# Formatter
uv run ruff format --check tests/bdd/test_export_to_indradb.py tests/fixtures/fake_indradb.py
# → 1 file would be reformatted (test_export_to_indradb.py)

uv run ruff format tests/bdd/test_export_to_indradb.py
# → 1 file reformatted

uv run ruff format --check tests/bdd/test_export_to_indradb.py tests/fixtures/fake_indradb.py
# → All formatted

# Linter
uv run ruff check tests/bdd/test_export_to_indradb.py tests/fixtures/fake_indradb.py
# → All checks passed

# Full suite — exit gate
uv run pytest -q 2>&1 | tail -5
# → 556 passed, 6 skipped
```

Note: `ruff format --check tests/bdd/features/export_to_indradb.feature` fails (Gherkin is not Python). The plan's exit-criteria command includes the .feature file in the format check — this is a plan error; ruff cannot parse Gherkin. Existing `.feature` files in the project are not included in ruff format checks. Exit-criteria ran on the two Python files only; feature file format is valid Gherkin.

## Deviations from plan.md

1. `fake_indradb.py` — no changes (already complete from S2).
2. Skip count: 6 total (2 @indradb + 1 @neo4j + 3 @cognee), not <=2.
3. Idempotency patching uses `patch(select_driver)` not pure `sys.modules`, as the sys.modules approach creates separate Client stores per call.
4. ruff format check on .feature file skipped (Gherkin not parseable by ruff).

## Tool failures / retries

Pass 1: `ruff format --check` reported `tests/bdd/test_export_to_indradb.py` needed reformatting (trailing-comma and string-concat normalization). Fixed by running `uv run ruff format tests/bdd/test_export_to_indradb.py`.
Pass 2: All gates cleared.

## Open items

- [sr-dev] Live idempotency test's `nodes_written` proxy always 0==0; real assertion needs post-export graph query.
- [sr-dev] Verify `indradb/indradb:5.0.0` Docker image tag before live CI.
