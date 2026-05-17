run_id: cpp-mcp-v6
story-slug: qa-fix-ruff
role: developer
date: 2026-05-17

## Skills loaded
- python-conventions (considered; skipped — no style ambiguity in these fixes)

## Commands run

| Command | Outcome |
|---|---|
| `uv run ruff check src/ tests/unit/` | PASS — 0 errors (post-fix) |
| `uv run pytest tests/unit -q` | PASS — 768 passed, 4 skipped |

## Fixes applied

### QD-1 — app.py I001 (import sort)
File: `src/cpp_mcp/server/app.py` lines 79–89
Action: merged standalone `from cpp_mcp.tools import describe_graph_schema` into the existing
import block and sorted alphabetically (describe_graph_schema first, then existing names).

### QD-2 — neo4j_driver.py RUF100 (unused noqa)
File: `src/cpp_mcp/graphdb/neo4j_driver.py` line 51
Action: removed `# noqa: PLC0415` comment. PLC0415 is not in the ruff ruleset
(E,F,I,UP,B,SIM,RUF), so the directive was dead and ruff rejected it.

### QD-3 — test_rename_invariant.py E501 (line too long)
File: `tests/unit/test_rename_invariant.py` line 111
Action: split the 108-char docstring into a short summary line + detail paragraph,
keeping all content; line lengths now within 100-char limit.

## Deviations from plan
None.

## Exit gate results (pass 1)
- `uv run ruff check src/ tests/unit/` — exit 0 (All checks passed)
- `uv run pytest tests/unit -q` — exit 0 (768 passed, 4 skipped)

All named signals clear on first pass.

## Follow-ups
None. QD-1/QD-2/QD-3 resolved; test-report.md updated to status: resolved for all three.
