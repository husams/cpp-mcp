run_id: cpp-mcp-v7-s2
story: P1 — Schema constants (Type, Parameter, 5 edges)
date: 2026-05-17
role: developer

## Skills loaded
- python-conventions (pyproject.toml present)

## Skills considered but not loaded
- cpp-conventions: not applicable (Python project)
- implement-story: plan.md provided full spec; no additional story scaffolding needed

## Commands run + outcomes

| Command | Outcome |
|---|---|
| `uv run ruff format src tests` | 14 files reformatted (pre-existing), 0 errors |
| `uv run ruff check src tests` | 2 errors: I001 (import sort in new test, auto-fixed), E501 in test_graphdb_additions.py (pre-existing line, fixed by rewrite) |
| `uv run ruff check src tests --fix` | 1 fixed, 1 remaining (E501 at test_graphdb_additions.py:95) |
| Rewrote count-test functions to fix E501 and update counts | |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/graphdb/test_s2_schema_constants.py -x -q` | 15 passed |
| `uv run pytest tests/unit -x -q` | 923 passed, 4 skipped, 0 failed |

## Files changed

- `src/cpp_mcp/graphdb/schema.py` — added `NODE_TYPE`, `NODE_PARAMETER`, `EDGE_RETURNS`, `EDGE_HAS_PARAM`, `EDGE_OF_TYPE`, `EDGE_POINTS_TO`, `EDGE_REFERS_TO`; extended `ALL_NODE_TYPES` (9→11) and `ALL_EDGE_TYPES` (7→12); updated module docstring
- `tests/unit/test_graphdb_additions.py` — updated count test `test_all_node_types_exactly_9` → `test_all_node_types_exactly_11` (9→11) and `test_all_edge_types_exactly_7` → `test_all_edge_types_exactly_12` (7→12); fixed pre-existing E501 at line 95 by rewriting function docstrings

## New files

- `tests/unit/graphdb/test_s2_schema_constants.py` — 15 tests covering all new constants, uniqueness invariants, and NODE_VARIABLE read-compat (ADR-26 D9)

## Deviations from plan

`test_graphdb_additions.py` count tests (lines 94-105) required update. ADR-26 D9 table says "Inspect at impl time; update if it asserts PARM_DECL emission, keep if it tests v1 compat." These tests assert schema cardinality (not PARM_DECL emission), so they require updating per additive schema growth. This is expected churn — not a regression.

## Follow-ups

None for P1. P2 (Type node + dedup + POINTS_TO/REFERS_TO chain) is next in sequence.

## References
- plan.md story P1
- adr-26.md D8, D9
- design.md §1.1, §1.2
- CHARTER §"S2 schema additions"
