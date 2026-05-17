run_id: cpp-mcp-v7-s1
story: P2 — Classifier: FIELD_DECL/VAR_DECL split + static-member invariant
role: developer
date: 2026-05-17

---

## Skills loaded
- python-conventions (loaded before writing code; toolchain: uv + ruff + pytest)

## Skills considered but not loaded
- implement-story: task arrived with a fully specified plan.md + design.md; no story derivation needed.
- cpp-conventions: project is Python (no CMakeLists.txt / *.cpp build target).

---

## Orientation steps

1. Read CHARTER.md, plan.md (Story P2), design.md §3, adr-25.md — confirmed scope: classifier helpers only, no property population (P3/P4), no MEMBER_OF change.
2. Read implementation-notes.md — confirmed P1 is complete (schema.py has NODE_FIELD, NODE_GLOBAL_VARIABLE; schema_version.py is "v2").
3. Read exporter.py — confirmed current state: `_KIND_TO_NODE_TYPE` still maps FIELD_DECL and VAR_DECL to `NODE_VARIABLE`.
4. Read test_schema_version_stamp.py — found the canonical fake-cursor / fake-TU pattern (MagicMock-based, no real libclang parse).

## Libclang capability probe (ADR-25 F-3)

Command:
```
uv run python -c "
from clang.cindex import Cursor, StorageClass
print('is_static_member on Cursor:', hasattr(Cursor, 'is_static_member'))
print('StorageClass.STATIC:', StorageClass.STATIC)
print('StorageClass values:', [x for x in dir(StorageClass) if not x.startswith('_')])
"
```

Result:
- `is_static_member on Cursor: False` — primary path unavailable.
- `StorageClass.STATIC: StorageClass.STATIC` — fallback available.
- Available StorageClass values: AUTO, EXTERN, INVALID, NONE, OPENCLWORKGROUPLOCAL, PRIVATEEXTERN, REGISTER, STATIC.
- **No THREAD_LOCAL** — noted as follow-up for P4.

Decision: `_is_static_member` always reaches the StorageClass.STATIC fallback on this libclang. Documented in implementation-notes.md and in test docstrings.

---

## Commands run

| Command | Outcome |
|---|---|
| `uv run ruff format exporter.py test_field_classification.py test_global_variable_classification.py` | 2 files reformatted (test files), exporter unchanged |
| `uv run ruff check --fix ...` | Fixed 2 I001 import-sort issues; 1 E501 fixed manually |
| `uv run ruff check src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/` | All checks passed |
| `uv run pytest tests/unit/graphdb/test_field_classification.py tests/unit/graphdb/test_global_variable_classification.py -x -q` | 15 passed |
| `uv run pytest tests/unit -x -q` | 791 passed, 4 skipped (zero regressions) |

---

## Deviations from plan.md

None. Implemented exactly `_classify_node`, `_classify_field`, `_is_static_member` per design §3. Did not touch property-population or MEMBER_OF block (reserved for P3/P4).

---

## Exit-gate results (P2)

- BUILD/FORMAT: pass (ruff format — 0 files changed after fix)
- LINT: pass (ruff check — all checks passed)
- TEST (P2 files): pass (15/15)
- TEST (full unit baseline): pass (791 passed, 4 skipped)

---

## Tool failures / retries

- ruff check: first run found 2 I001 (import sort) + 1 E501 (line too long). Fixed in 2 passes (auto-fix + manual docstring trim). All green on third run.

---

## Follow-ups filed in implementation-notes.md

- No THREAD_LOCAL StorageClass enum on pinned libclang — P4 design §4.3 must use token-scan fallback.
