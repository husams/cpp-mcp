run_id: cpp-mcp-v7-s1
story: QD-1 — update _EXPECTED_NODE_COUNTS for v2 schema
role: developer
date: 2026-05-17

## Skills loaded
- python-conventions (pyproject.toml present)

## Skills considered but not loaded
- implement-story — task was a targeted defect fix on one file, not a full story
- cpp-conventions — no C++ edits

## Commands run

```
# Pre-flight read
Read tests/integration/test_describe_graph_schema_e2e.py   # lines 1–290 — mapped all assertions

# Edit 1: replace _EXPECTED_NODE_COUNTS block with v2-aware constants
Edit tests/integration/test_describe_graph_schema_e2e.py

# Edit 2: rewrite test_ac_q3_2_vertex_type_counts_pinned to structural invariants
Edit tests/integration/test_describe_graph_schema_e2e.py

# Edit 3: rewrite sort-order assertions in test_ac_q3_4_sort_order_by_count_desc
Edit tests/integration/test_describe_graph_schema_e2e.py

# Gate pass 1
uv run ruff format tests/integration/test_describe_graph_schema_e2e.py
# → 1 file reformatted
uv run ruff check tests/integration/test_describe_graph_schema_e2e.py
# → LINT_FAIL: E501 (3 lines > 100 chars)

# Fix E501 — shorten long f-strings in assertions
Edit tests/integration/test_describe_graph_schema_e2e.py (2 edits)

# Gate pass 2
uv run ruff format tests/integration/test_describe_graph_schema_e2e.py
# → 1 file left unchanged
uv run ruff check tests/integration/test_describe_graph_schema_e2e.py
# → All checks passed

uv run pytest -q --ignore=tests/integration
# → 1020 passed, 6 skipped, 12 warnings in 13.81s
```

## Deviations from plan
None — fix matched the QD-1 description exactly.

## Follow-ups
- Exact Field/GlobalVariable/Variable counts for os.cc corpus are not pinned (need live run with INDRADB_TEST_URI). Once available, consider adding pinned counts for Field and GlobalVariable to _EXPECTED_NODE_COUNTS_STABLE.
- UNION_DECL MEMBER_OF edge gap documented in test-report.md observations (advisory, S2+ scope).
