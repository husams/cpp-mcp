# Deploy Notes — cpp-mcp v0.4.0

Run: cpp-mcp-v6
Date: 2026-05-17
Devops agent: devops (stage 7 of 8)
Target: python library release — no cluster deploy, no kubectl, no ArgoCD

---

## Context check

DEPLOY_DRIFT is not applicable. This is a Python library release (PyPI-shaped),
not a cluster workload. No `kubectl config current-context` check required.
Target is `github.com/husams/cpp-mcp` + optional PyPI publish.

---

## Pre-release state (verified)

| Check | Result |
|---|---|
| `pyproject.toml version` | `0.4.0` |
| `uv build` | `dist/cpp_mcp-0.4.0.tar.gz` (521K) + `dist/cpp_mcp-0.4.0-py3-none-any.whl` (81K) — PASS |
| Installed version (`importlib.metadata`) | `0.4.0` |
| `CHANGELOG.md` has `## 0.4.0` section | PASS |
| `README.md` documents `query_graphdb` | PASS |
| `README.md` documents `describe_graph_schema` | PASS |
| wiki page `pages/code/cpp-mcp-v6.md` | EXISTS |
| All QA_DEFECT entries | resolved (QD-1, QD-2, QD-3 — see test-report.md) |

---

## Uncommitted changes (user commits manually)

The following changes are staged/unstaged but NOT committed. Do not auto-commit.

**Modified files (M):**
- `CHANGELOG.md` — 0.4.0 section added
- `README.md` — Query surface section added
- `pyproject.toml` — version bumped 0.3.0 → 0.4.0
- `src/cpp_mcp/core/error_envelope.py` — new error codes (S1)
- `src/cpp_mcp/graphdb/exporter.py` — schema_version stamp on File nodes (S1)
- `src/cpp_mcp/graphdb/neo4j_driver.py` — noqa cleanup (QD-2 fix)
- `src/cpp_mcp/server/app.py` — registered query_graphdb + describe_graph_schema (QD-1 fix)
- `tests/fixtures/fake_indradb.py` — updated for S2/S5
- `tests/unit/test_envelope_codes.py` — new error codes coverage
- `tests/unit/test_envelope_decorator_order.py` — coverage update
- `tests/unit/test_error_envelope.py` — coverage update
- `tests/unit/test_rename_invariant.py` — 9-tool count + line-length fix (QD-3)
- `tests/unit/test_server_app.py` — registration update
- `tests/unit/test_tool_registration.py` — count 7→9, new tool names

**New files (??):**
- `src/cpp_mcp/core/query_config.py`
- `src/cpp_mcp/graphdb/indradb_query_executor.py`
- `src/cpp_mcp/graphdb/neo4j_query_executor.py`
- `src/cpp_mcp/graphdb/query_executor.py`
- `src/cpp_mcp/graphdb/schema_introspector.py`
- `src/cpp_mcp/graphdb/schema_version.py`
- `src/cpp_mcp/tools/describe_graph_schema.py`
- `src/cpp_mcp/tools/query_graphdb.py`
- `tests/bdd/features/query_graphdb.feature`
- `tests/bdd/test_query_graphdb_bdd.py`
- `tests/integration/test_describe_graph_schema_e2e.py`
- `tests/integration/test_query_graphdb_e2e.py`
- `tests/unit/core/` (directory of new unit tests)
- `tests/unit/graphdb/` (directory of new unit tests)
- `tests/unit/tools/` (directory of new unit tests)
- `.claude/handoff/v6/` (handoff dir — exclude from release commit)

---

## Manual release steps (user executes in order)

See runbook.md for copy-pasteable commands with exact flags.

1. Review `git diff` and `git status`
2. Stage all source + test changes (exclude `.claude/handoff/v6/`)
3. Commit: `v6: add query_graphdb + describe_graph_schema (0.4.0)`
4. Tag: `git tag -a v0.4.0 -m "Release 0.4.0 — graph query surface"`
5. Push branch + tag: `git push origin main && git push origin v0.4.0`
6. Create GitHub release: `gh release create v0.4.0 dist/cpp_mcp-0.4.0.tar.gz dist/cpp_mcp-0.4.0-py3-none-any.whl`
7. (Optional) Publish to PyPI: `uv publish`

---

## Rollback

If the commit must be reverted before push: `git reset HEAD~1` (unstages, keeps files).
If tag was pushed: `git push origin --delete v0.4.0` then re-tag after fix.
No cluster state to roll back; library is additive (no breaking changes to existing 7 tools).

---

## References

- plan.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/plan.md
- test-report.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/test-report.md
- CHARTER.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/CHARTER.md
- wiki: pages/code/cpp-mcp-v6.md, pages/planning/cpp-mcp-codexgraph-gap.md
