---
story: S1 — DEPENDENCY_MISSING error code (US-G1)
role: developer
date: 2026-05-16
status: complete
signals: clear
---

# Session Log

## Skills loaded
- `python-conventions` — loaded before writing any code for style/test/build conventions.

## Skills considered but not loaded
- `implement-story` — task was directly dispatched with a concrete plan; no user-story decomposition needed.
- `simplify` — no refactoring sweep required; changes are purely additive.

## Commands run + outcomes

| Command | Outcome |
|---------|---------|
| `uv sync --extra dev` | Installed pytest into venv (was missing; homebrew pytest 3.13 was shadowing). Required to make module-level `cpp_mcp` imports work in tests. |
| `uv run ruff format --check ...` | FAIL (test_dependency_missing.py); auto-fixed with `ruff format`. |
| `uv run ruff check ... --fix` | Fixed I001 (import sort) in test_dependency_missing.py. |
| `uv run ruff check ...` | Pass after fixes. |
| `uv run mypy src/cpp_mcp/core/error_envelope.py src/cpp_mcp/graphdb/neo4j_driver.py` | Pass. |
| `uv run pytest -q tests/unit/test_dependency_missing.py tests/unit/test_envelope_codes.py` | 26 passed. |
| `uv run pytest -q` (full suite) | First run: 491 passed, 4 failed. Failures were pre-existing tests hardcoding "8 error codes" + the neo4j import-error mis-classification. Fixed all four. Second run: 495 passed, 6 skipped. |

## Files changed
- `src/cpp_mcp/core/error_envelope.py` — added `ErrorCode.DEPENDENCY_MISSING`; added `DependencyMissingError` class; inserted `(DependencyMissingError, ErrorCode.DEPENDENCY_MISSING)` in `_EXC_TO_CODE` before `DBUnreachableError`.
- `src/cpp_mcp/graphdb/neo4j_driver.py` — fixed v2 miswire: `ImportError` now raises `DependencyMissingError` with `graphdb-neo4j` install hint instead of `DBUnreachableError`.
- `tests/unit/test_dependency_missing.py` — new; 26 tests covering AC-1..4 and ADR-13 ordering invariant.
- `tests/unit/test_envelope_codes.py` — added `DependencyMissingError` pair; updated stale "8 codes" comment.
- `tests/unit/test_runbook_present.py` — added v3 runbook guards (skip when file absent, pending S6).
- `tests/unit/test_error_envelope.py` — updated `EXPECTED_CODES` set and count assertion (8→9).
- `tests/unit/test_server_app.py` — updated `VALID_ERROR_CODES` set to include `DEPENDENCY_MISSING`.
- `tests/unit/test_graphdb_additions.py` — updated `test_db_unreachable_closed_port` to accept `(DependencyMissingError, DBUnreachableError)` since test env has no `neo4j` installed.

## Deviations from plan
- Plan listed only `test_envelope_codes.py` as the existing test to update. Additionally updated `test_error_envelope.py`, `test_server_app.py`, and `test_graphdb_additions.py` — all of which hardcoded the previous 8-code set and broke when `DEPENDENCY_MISSING` was added. These are correct updates, not scope creep.
- Had to run `uv sync --extra dev` to install pytest into the venv. The project's `pyproject.toml` has pytest under `[project.optional-dependencies].dev`, but `uv sync` (default) does not install it. This was a pre-existing environment gap; the fix is a prerequisite for any test run via `uv run pytest`.

## Open items / follow-ups
None for S1. Tagged for sr-dev awareness:
- Pre-existing: `uv sync --extra dev` is required before `uv run pytest` works. Consider adding `pythonpath = ["src"]` to `[tool.pytest.ini_options]` so tests work even when the package isn't installed in the active interpreter (currently 29 tests fail collection under system Python 3.13). This is environment hygiene, not a S1 regression.

## References
- `plan.md` S1 (L47–83)
- `adr-13.md`
- `scenarios.md`
