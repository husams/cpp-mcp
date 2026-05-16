run_id: cpp-mcp-1
story: defect-fix QD-TRANS-001
date: 2026-05-16
role: developer
model: claude-sonnet-4-6

## Skills loaded
- python-conventions: considered but not loaded — task was a 2-file lint/format fix; no new code written.
- cpp-conventions: not loaded — no C++ files touched.

## Skills considered but not loaded
- python-conventions: the defect fix required no new code structure or test patterns; formatter/linter commands already known from plan.md exit-criteria.

## Orientation

- Read CHARTER.md, logs/qa-engineer-transport.md, tests/unit/test_foundation_property.py, src/cpp_mcp/core/path_guard.py.
- Finding: test_valid_path_inside_root_always_passes at line 286-287 already contained the QD-TRANS-001 fix (`_os.path.realpath(tmp)` → `tmp_real`). The QA engineer identified and applied the fix in the same session but filed the defect as open.
- The hypothesis cache (.hypothesis/examples/) held a stale replay entry; cleared it to confirm determinism.

## Root-cause analysis

QD-TRANS-001 was a macOS-specific flakiness: `tempfile.TemporaryDirectory()` returns `/var/folders/...` which is a symlink to `/private/var/folders/...`. The test was constructing `allowed_root` from the unresolved tmp string, while `validate_path()` resolves via `os.path.realpath()`, so the prefix check failed.

Fix: build `allowed_root` from `os.path.realpath(tmp)` so both sides are resolved before the prefix comparison. The fix was already present in the file when this developer pass began.

## Commands run

| Command | Outcome |
|---------|---------|
| `uv run pytest tests/unit/test_foundation_property.py::test_valid_path_inside_root_always_passes -v` | PASSED |
| `uv run pytest tests/unit/test_foundation_property.py -v` | 21 passed |
| `rm -rf .hypothesis/examples && pytest ... --hypothesis-seed=0` | PASSED — no replay flakiness |
| `uv run ruff format --check .` | FAIL — 2 files needed reformatting |
| `uv run ruff format tests/unit/test_foundation_property.py tests/unit/test_graphdb_additions.py` | reformatted |
| `uv run ruff check --fix tests/unit/ ` | 5 auto-fixed; 2 F841 remaining in test_graphdb_additions.py |
| Manual edit: remove `n1 =` and `e1 =` assignments | fixed F841 |
| `uv run ruff format --check .` | PASS — 58 files formatted |
| `uv run ruff check .` | PASS — all checks passed |
| `uv run mypy --strict src/cpp_mcp` | PASS — no issues in 28 files |
| `uv run pytest -q` | 327 passed, 1 skipped, 2 warnings |

## Files changed

- `tests/unit/test_foundation_property.py` — ruff format reformatted (import sort, unused imports `re`, `typing.Any` removed by --fix)
- `tests/unit/test_graphdb_additions.py` — ruff format reformatted; unused imports `socketserver`, `unittest.mock.patch` removed; unused variables `n1`, `e1` assignments removed (F841 fix)

## Deviations from plan

- The QD-TRANS-001 fix (`os.path.realpath(tmp)`) was already present in test_foundation_property.py; no additional edit to that specific logic was required.
- Two additional lint issues found and fixed in test_graphdb_additions.py (unrelated to QD-TRANS-001 but required to clear LINT_FAIL gate).

## Exit gate results

| Gate | Result |
|------|--------|
| ruff format --check | PASS |
| ruff check | PASS |
| mypy --strict src/cpp_mcp | PASS |
| pytest -q | 327 passed, 1 skipped |

QD-TRANS-001 status: RESOLVED — test passes deterministically with cleared hypothesis cache.

## Follow-ups (open items for sr-dev/qa)

1. Advisory: 2 PytestUnknownMarkWarning for @SC_US_14_CALL_ENVELOPE and @SC_US_11_1_ALL_TOOLS — register both marks in [tool.pytest.ini_options].markers in pyproject.toml (noted by QA engineer; not blocking).
