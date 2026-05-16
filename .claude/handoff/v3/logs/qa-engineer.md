---
run_id: graphdb-multi-v3
stage: qa-engineer
date: 2026-05-16
status: complete
---

# QA Engineer Log — graphdb-multi v3

## Inputs read

- `CHARTER.md` — confirmed I4 (test-report.md required before devops dispatch)
- `scenarios.md` — 6 features, scenario-IDs US-G1/AC-1..4 through US-G6/AC-1..3
- `implementation-notes.md` — all 6 stories completed by developer; final count was 556 passed before QA additions
- `plan.md` — story sequencing, exit criteria, traceability matrix

## Baseline run

```
uv run pytest -q
→ 556 passed, 6 skipped in 7.98s
```

6 skips: 2 @indradb (INDRADB_TEST_URI not set), 3 @cognee (COGNEE_BASE_URL not set, pre-existing from v2), 1 @neo4j (NEO4J_TEST_URI not set). Plan deviation acknowledged in implementation-notes.md §S5.

## Source files inspected

- `src/cpp_mcp/graphdb/__init__.py` — `select_driver` uses `urlparse(db_uri).scheme` (lowercase-normalising) + frozenset lookup. Key finding: uppercase URIs dispatch correctly per RFC 3986.
- `src/cpp_mcp/graphdb/indradb_driver.py` — `_normalise_prop` helper for ADR-15; `_strip_scheme` for default port 27615. Neither was covered by boundary tests for types beyond happy-path scalars.
- `tests/unit/test_driver_dispatch.py` — 9 parametrised scheme tests (all lowercase), unconnected-instance checks. No uppercase, no IPv6, no default-port test.
- `tests/unit/test_indradb_driver.py` — 26 tests with `importlib.reload` pattern causing module identity issue for downstream isinstance checks.

## Test additions

New file: `tests/unit/test_select_driver_boundaries.py`  
Category: parametrised / boundary (Category 2)  
Tests added: 34

Key boundaries exercised:
1. Uppercase URI schemes — RFC 3986 §3.1 case-insensitivity (US-G3/AC-1)
2. IPv6 host addresses in Neo4j URIs (US-G3/AC-1)
3. IndraDB default port 27615 when no port in URI (US-G2/AC-2)
4. _normalise_prop: all 9 scalar types, 6 non-scalar types, sort_keys determinism, circular-reference fallback (US-G2/AC-6, ADR-15)

## Module identity issue encountered and resolved

`test_indradb_driver.py` uses `importlib.reload(drv_mod)` to force lazy imports to see the monkeypatched sys.modules. This creates a new `IndraDBDriver` class object at runtime. Any `isinstance(driver, IndraDBDriver)` where `IndraDBDriver` was imported at module-level fails after the reload runs in a prior test.

Fix: in `test_select_driver_boundaries.py`, tests that check `isinstance(driver, IndraDBDriver)` for IndraDB paths call `importlib.reload(drv_mod)` themselves and reference `drv_mod.IndraDBDriver` post-reload.

## Final run

```
uv run pytest -q
→ 590 passed, 6 skipped in 8.09s
```

## Defects

None open.

## Outputs

- `test-report.md`: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/test-report.md`
- New test file: `/Users/husam/workspace/cpp-mcp/tests/unit/test_select_driver_boundaries.py`
