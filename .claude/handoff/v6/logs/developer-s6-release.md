# Developer Log — S6 Release (cpp-mcp-v6)

Date: 2026-05-17
Story: S6 — Docs, CHANGELOG, version bump
Run: cpp-mcp-v6

## Skills loaded

- `python-conventions` — loaded before writing; confirmed uv + ruff + mypy + pytest toolchain, src/ layout, style rules.

## Skills considered but not loaded

- `implement-story` — S6 is pure doc/config work; no new Python source files to implement.
- `simplify` — no code written; not applicable.

## Commands run and outcomes

```
uv run pytest -q
→ 867 passed, 6 skipped in 19.47s   [PASS]

uv build
→ dist/cpp_mcp-0.4.0.tar.gz + cpp_mcp-0.4.0-py3-none-any.whl   [PASS]

test "$(uv run python -c 'import importlib.metadata as m; print(m.version("cpp-mcp"))')" = "0.4.0"
→ VERSION OK   [PASS]

grep -q '^## 0.4.0' CHANGELOG.md
→ CHANGELOG OK   [PASS]

grep -q 'query_graphdb' README.md && grep -q 'describe_graph_schema' README.md
→ README OK   [PASS]

test -f ~/workspace/wiki/pages/code/cpp-mcp-v6.md
→ WIKI PAGE OK   [PASS]
```

## Files changed

| File | Change |
|---|---|
| `pyproject.toml` | version 0.3.0 → 0.4.0 |
| `CHANGELOG.md` | Added `## 0.4.0` section |
| `README.md` | Tool count 7→9; "Query surface" section; config table; test count updated |
| `~/workspace/wiki/pages/code/cpp-mcp-v6.md` | Created (new wiki page) |
| `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md` | S1 marked as shipped |
| `~/workspace/wiki/index.md` | cpp-mcp + v6 entries updated |
| `~/workspace/wiki/log.md` | v6 ingest entry appended |

## Deviations from plan

None.

## Tool failures / retries

None. All exit-gate commands passed on first run.

## Named signals

- BUILD_FAIL: cleared (uv build → 0.4.0 clean)
- LINT_FAIL: n/a (no new Python source files in S6)
- TEST_FAIL: cleared (867 passed)
