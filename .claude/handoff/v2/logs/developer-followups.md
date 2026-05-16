---
task-slug: fastmcp-migration
story: followups (S1/S4/S7 follow-ups — pyproject hygiene + plan.md correction)
date: 2026-05-16
role: developer
---

## Session log

### Skills loaded
- python-conventions (pyproject.toml present)

### Skills considered but not loaded
- cpp-conventions: no C++ changes in this task
- implement-story: not a new story implementation, just hygiene fixes

### Commands run

```
grep -r "@pytest.mark.SC_" tests/ → found SC_USM7_3
grep -r "pytest.mark\." tests/ → found SC_USM7_3, SC_USM2_1, SC_USM2_4, SC_US_14_CALL_ENVELOPE, SC_US_11_1_ALL_TOOLS
ls src/cpp_mcp/tools/ → get_definition.py, get_references.py, get_type_info.py, get_ast.py, get_header_info.py, get_preprocessor_state.py, export_to_graphdb.py
grep tool function names → get_definition, get_references, get_type_info, cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state, cpp_export_to_graphdb
uv run ruff format . → 1 file reformatted (pyproject.toml)
uv run ruff check . → All checks passed
uv run pytest -q (pass 1) → 3 more unknown markers: SC_USM2_1, SC_USM2_4, SC_US_11_1_ALL_TOOLS
uv run pytest -q (pass 2) → 1 more: SC_US_11_1_ALL_TOOLS
uv run pytest -q (pass 3) → 472 passed, 4 skipped, 0 warnings
uv run ruff format --check . && uv run ruff check . → clean
```

### Changes made

**pyproject.toml**
1. Added `"build"` to `[project.optional-dependencies].dev` group.
2. Registered 6 missing `SC_*` markers under `[tool.pytest.ini_options].markers`:
   - `SC_USM7_3` — BDD test in tests/bdd/test_concurrent_ast.py
   - `SC_USM2_1` — BDD feature tag in tests/bdd/features/transport_http.feature
   - `SC_USM2_4` — BDD feature tag in tests/bdd/features/transport_http.feature
   - `SC_US_14_CALL_ENVELOPE` — BDD feature tag in tests/bdd/features/transport_stdio.feature + test_transport_stdio.py
   - `SC_US_11_1_ALL_TOOLS` — BDD feature tag in tests/bdd/features/read_only_enforcement.feature

**plan.md (S4 exit-criteria)**
- Corrected module import names: `definition` → `get_definition`, `references` → `get_references`, `type_info` → `get_type_info`, `ast` → `get_ast`, `header_info` → `get_header_info`, `preprocessor_state` → `get_preprocessor_state`, `export_graphdb` → `export_to_graphdb`.
- Corrected function name lookup: replaced `n.startswith('cpp_')` pattern (which misses `get_definition`, `get_references`, `get_type_info`) with an explicit `(module, fn_name)` list using the actual function names.

### Deviations from plan
- Dispatch specified registering `SC_US_14_CALL_ENVELOPE` and scanning for other `SC_*` markers. Scan found 5 unregistered markers total (not 1); all registered.

### Follow-ups
- None.

### Exit gate results (pass 3 — all clear)
- `ruff format --check .` → 0 (79 files already formatted)
- `ruff check .` → 0 (All checks passed)
- `pytest -q` → 0 (472 passed, 4 skipped, 0 warnings)
