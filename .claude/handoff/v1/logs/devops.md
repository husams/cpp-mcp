run_id: cpp-mcp-1
stage: devops
date: 2026-05-16
model: claude-sonnet-4-6

---

## Pre-conditions verified

- CHARTER invariant I4: test-report.md checked; only defect QD-TRANS-001 listed, status=resolved. No open QA_DEFECT entries. Dispatch authorized.
- target-context: NONE (local stdio MCP server; no Kubernetes cluster). DEPLOY_DRIFT check: N/A.
- No `kubectl` commands issued; no cluster resources touched.

---

## Inputs read

- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/CHARTER.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/design.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/plan.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/implementation-notes.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/test-report.md
- /Users/husam/workspace/cpp-mcp/pyproject.toml

---

## Outputs written

1. /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/runbook.md
   - Prerequisites: Python 3.11+, libclang (Xcode CLT / brew install llvm / apt install libclang-dev)
   - Install: uv sync or pip install -e .
   - Config: CPP_MCP_ALLOWED_ROOTS (required) + 7 optional env vars
   - Run: python -m cpp_mcp or cpp-mcp entry point
   - Claude Code integration: ~/.claude/mcp.json snippet
   - Claude Desktop integration: claude_desktop_config.json snippet
   - Neo4j optional config: graphdb extra, Bolt URI, docker example
   - Troubleshooting: libclang not found, CPP_MCP_ALLOWED_ROOTS absent, PATH_VIOLATION, parse errors, high memory, PARSE_ERROR
   - Tool catalogue: 7 tools, all read-only

2. /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/deploy-notes.md
   - No Kubernetes, no container, no Helm — local stdio tool
   - CI pipeline: GitHub Actions .github/workflows/ci.yml
   - Jobs: lint (ruff + mypy), test (matrix 3.11/3.12 + coverage), release (tag-gated, PyPI OIDC)
   - Version bump procedure: __init__.py + pyproject.toml, git tag vX.Y.Z
   - Local build verification commands
   - Rollback: PyPI yank procedure

3. /Users/husam/workspace/cpp-mcp/.github/workflows/ci.yml
   - Triggers: push (all branches), pull_request (main), tag (v*.*.*)
   - lint job: ruff format check, ruff check, mypy --strict (Python 3.11)
   - test job: matrix [3.11, 3.12]; apt install libclang-dev; uv sync --extra dev --extra graphdb; pytest -q --cov; upload coverage artifact
   - release job: gated on lint+test passing AND tag push; uv build; pypa/gh-action-pypi-publish (OIDC trusted publisher); softprops/action-gh-release with dist assets

---

## Key decisions / deviations from dispatch brief

- GitHub Actions chosen (project has no remote yet; GitHub is the standard default for open-source Python packages)
- libclang installed via `apt install libclang-dev` in CI (ubuntu-latest runner provides this without version pinning to avoid ADR mismatch)
- CPP_MCP_ALLOWED_ROOTS set to ${{ github.workspace }} in test job so path-guard tests operate against a valid root
- OIDC trusted publisher used for PyPI (no stored API token); requires one-time setup at pypi.org
- Neo4j job omitted from standard CI matrix; @pytest.mark.neo4j scenarios auto-skip without NEO4J_TEST_URI
- hypothesis added to dev deps in pyproject.toml by QA; already captured; no changes needed here

---

## Follow-ups for doc-writer

- Publish runbook.md to BookStack under a "cpp-mcp" page
- Register the PyPI trusted publisher (one-time, human action): https://pypi.org/manage/project/cpp-mcp/settings/publishing/
- Add SC_US_14_CALL_ENVELOPE and SC_US_11_1_ALL_TOOLS to pyproject.toml markers (advisory PytestUnknownMarkWarning from test-report observation 3)

---

## References

- handoff inputs: design.md, plan.md, implementation-notes.md, test-report.md, pyproject.toml
- Cognee tags: task:cpp-mcp, role:devops
