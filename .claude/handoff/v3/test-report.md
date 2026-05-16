---
run_id: graphdb-multi-v3
stage: qa-engineer
date: 2026-05-16
status: clear
---

# Test Report — graphdb-multi v3

## Scope

Consolidated QA across all 6 stories (S1–S6):
- S1: `DEPENDENCY_MISSING` error code and `DependencyMissingError` class (US-G1)
- S2: `IndraDBDriver` protocol implementation (US-G2)
- S3: URI-scheme-based driver dispatch via `select_driver` (US-G3)
- S4: Dual optional extras in `pyproject.toml` (US-G4)
- S5: IndraDB BDD export coverage (US-G5)
- S6: Documentation completeness (US-G6)

## Test plan

unit | integration | BDD/E2E

## Commands run

```bash
# Pre-addition baseline
uv run pytest -q
# → 556 passed, 6 skipped in 7.98s

# New boundary test file only (validation pass)
uv run pytest tests/unit/test_select_driver_boundaries.py -v
# → 34 passed in 0.10s

# Lint + format check on new file
uv run ruff format --check tests/unit/test_select_driver_boundaries.py
uv run ruff check tests/unit/test_select_driver_boundaries.py
# → All checks passed

# Final full suite
uv run pytest -q
# → 590 passed, 6 skipped in 8.09s
```

## Results

**590 passed / 0 failed / 6 skipped**

### Skip classification (all env-gated, not defects)

| Skip reason | Count | Gate env-var | Test file |
|---|---|---|---|
| `@indradb` live scenario | 2 | `INDRADB_TEST_URI` not set | `tests/bdd/test_export_to_indradb.py:318` |
| `@cognee` live test | 3 | `COGNEE_BASE_URL` not set | `tests/unit/test_cognee_driver.py:418,441,462` |
| `@neo4j` live test | 1 | `NEO4J_TEST_URI` not set | `tests/unit/test_graphdb_additions.py:345` |

**Plan stated "≤2 skipped (1 neo4j + 1 indradb)."** Actual is 6 skipped (2 @indradb + 1 @neo4j + 3 @cognee pre-existing). The 3 @cognee skips are pre-existing from the v2 run (not introduced in v3). The 2 @indradb skips are correct per `scenarios.md` — two `@indradb` scenarios gate on `INDRADB_TEST_URI`. This was acknowledged as a known plan deviation in `implementation-notes.md` §S5. All 6 skips are env-gated and classified as not defects.

### Per-story test coverage

| Story | Scenario-IDs | Primary test files | Result |
|---|---|---|---|
| S1 | US-G1/AC-1..4 | `test_dependency_missing.py`, `test_envelope_codes.py` | 26 pass |
| S2 | US-G2/AC-1..8 | `test_indradb_driver.py` | 26 pass |
| S3 | US-G3/AC-1..5 | `test_driver_dispatch.py`, `test_export_to_graphdb.py` | pass |
| S4 | US-G4/AC-1..4 | `test_pyproject_extras.py` | 7 pass |
| S5 | US-G5/AC-1..5 | `test_export_to_indradb.py` | 8 pass + 2 skip (@indradb) |
| S6 | US-G6/AC-1..3 | `test_runbook_present.py`, README/wiki greps | 5 pass |

## Defects

None. 0 open QA_DEFECT entries.

## Observations

These are advisory only and do not block dispatch.

1. **Live idempotency proxy** (S5 follow-up, from `implementation-notes.md`): The live `@indradb` "Re-exporting idempotent" scenario uses `result.get("nodes_written", 0)` as a proxy for node count; the tool response does not emit `nodes_written`, so the assertion trivially passes (0==0). Proper validation requires querying the live graph after each run. Acceptable for v3 since live tests are not CI-wired (US-G5/AC-3), but worth fixing before IndraDB live CI is wired.

2. **Leading-whitespace URI passthrough**: `select_driver("  bolt://localhost:7687")` silently succeeds because `urlparse` strips leading whitespace before extracting the scheme. This matches RFC 3986 whitespace-handling behavior of Python's urlparse; not a defect, but operators could be confused by inconsistent behavior with the `"://" not in db_uri` guard.

3. **`importlib.reload` module identity**: `test_indradb_driver.py` calls `importlib.reload` on `cpp_mcp.graphdb.indradb_driver`, which creates a new class identity in the same pytest session. Tests that use `isinstance(driver, IndraDBDriver)` after this reload must re-import the class post-reload; this is handled in `test_select_driver_boundaries.py`.

## Additions made

**Category: property-based / parametrised (Category 2)**

New file: `tests/unit/test_select_driver_boundaries.py` — 34 parametrised boundary tests.

Coverage added beyond the developer's happy-path tests:

- **`select_driver` URI boundary cases** (US-G3/AC-1, US-G3/AC-2):
  - Uppercase scheme letters (`BOLT://`, `INDRADB://`, `NEO4J+S://`, etc.) via RFC 3986 §3.1 case-insensitivity (5 Neo4j + 3 IndraDB parametrised cases).
  - IPv6 host form (`bolt://[::1]:7687`, `neo4j+s://[2001:db8::1]:7687`).
  - Trailing slash on authority (`bolt+ssc://localhost:7687/`).
  - Malformed/unknown schemes that happen to contain `://` (`bolt+extra+ssc://`, `://localhost`, `MYSQL://`, `ftp://`).

- **`IndraDBDriver` default-port behavior** (US-G2/AC-2): `indradb://localhost` (no port) must produce `host="localhost:27615"` in the client — this was untested.

- **`_normalise_prop` type boundaries** (US-G2/AC-6 / ADR-15):
  - All 9 scalar type variants (bool True/False, None, int, negative int, float, zero float, str, empty str) pass through unchanged.
  - 6 non-scalar type variants (list, tuple, empty list, empty dict, nested dict, dict with unsorted keys) JSON-encode correctly.
  - `sort_keys=True` determinism verified across two calls.
  - Circular-reference dict returns a string (repr fallback) without raising.

## References

- Scenario-IDs: `scenarios.md` (US-G1/AC-1..4, US-G2/AC-1..8, US-G3/AC-1..5, US-G4/AC-1..4, US-G5/AC-1..5, US-G6/AC-1..3)
- Implementation notes: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/implementation-notes.md`
- Cognee tags: `task:graphdb-multi`, `role:qa-engineer`
