---
task: graphdb-multi
story: S4 — Optional dependency extras split (US-G4)
date: 2026-05-16
role: developer
signals: clear
---

## Skills loaded

- python-conventions (pyproject.toml present)

## Skills considered but not loaded

- cpp-conventions: no C++ changes in S4
- implement-story: plan.md already provided with precise instructions; direct implementation faster

## Commands run

| Command | Outcome |
|---------|---------|
| `uv run ruff format --check tests/unit/test_pyproject_extras.py` | 1 file already formatted |
| `uv run ruff check tests/unit/test_pyproject_extras.py` | All checks passed |
| `uv run pytest -q tests/unit/test_pyproject_extras.py` | 7 passed in 0.08s |
| `uv lock --check` | Resolved 104 packages — lock valid |
| `uv sync --group dev` | Clean sync; 72 packages audited |
| `uv pip list | grep -E '^(neo4j\|indradb) '` | Empty — C-G5 confirmed |

## Files changed

- `pyproject.toml`: replaced single `graphdb = ["neo4j>=5.0"]` with three entries (`graphdb-neo4j`, `graphdb-indradb`, `graphdb` meta-extra).
- `tests/unit/test_pyproject_extras.py`: new file — 7 assertions covering key existence and pin values.

## Deviations from plan

None.

## Exit-criteria signals

- BUILD_FAIL: clear
- LINT_FAIL: clear
- TEST_FAIL: clear

## Follow-ups

None — S4 is self-contained and parallel-safe with S1/S2.
