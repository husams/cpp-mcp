# Deploy Notes: C++ Semantic Analysis MCP Server (cpp-mcp)

run_id: cpp-mcp-1
stage: devops
date: 2026-05-16
target-context: NONE (local stdio tool — no Kubernetes, no container)
DEPLOY_DRIFT: N/A — no cluster target; `kubectl config current-context` check skipped by design.

---

## 1. Summary

`cpp-mcp` is a local Python stdio MCP server. There is no cluster deployment, no container,
and no Helm chart. The release pipeline is GitHub Actions. On push/PR: lint + type-check +
test. On tag: build wheel + sdist and publish to PyPI.

The workflow file is written at:
  `/Users/husam/workspace/cpp-mcp/.github/workflows/ci.yml`

---

## 2. CI/CD pipeline — GitHub Actions

### Workflow file

`.github/workflows/ci.yml` (see file written by this devops run).

### Trigger rules

| Event | Jobs run |
|---|---|
| `push` to any branch | `lint`, `test` |
| `pull_request` targeting `main` | `lint`, `test` |
| `push` of a tag matching `v*.*.*` | `lint`, `test`, then `release` (gated) |

### Job: lint

Runs `ruff format --check` and `ruff check` on Python 3.11 (single version — formatting
is not version-dependent). Also runs `mypy --strict`.

### Job: test

Matrix: Python **3.11** and **3.12**.

Steps per matrix leg:
1. Install system libclang (via `apt install libclang-dev` on the `ubuntu-latest` runner).
2. `uv sync --extra dev` (includes hypothesis, pytest-bdd, pytest-asyncio, pytest-cov).
3. `uv run pytest -q --cov=cpp_mcp --cov-report=xml` — full test suite.
4. Upload coverage XML as artifact (advisory; no gate).

Neo4j scenarios are skipped automatically (`@pytest.mark.neo4j` requires `NEO4J_TEST_URI`
which is not set in standard CI). To enable: add a Neo4j service container and set
`NEO4J_TEST_URI` as a secret / env in the workflow.

`CPP_MCP_ALLOWED_ROOTS` is set to `${{ github.workspace }}` so path-guard tests that need
an allowed root can operate without a full tmp-path setup. Individual test fixtures create
sub-paths under this root.

### Job: release (tag-gated)

Depends on `lint` and `test` (both matrix legs must pass).

Steps:
1. `uv build` — produces `dist/cpp_mcp-<version>-py3-none-any.whl` and
   `dist/cpp_mcp-<version>.tar.gz`.
2. Publish to PyPI via `pypa/gh-action-pypi-publish`.
3. Create a GitHub Release with the dist assets attached.

PyPI trusted publisher (OIDC) is the recommended auth mechanism — no API token stored.
Configure at https://pypi.org/manage/project/cpp-mcp/settings/publishing/ with:
- Publisher: GitHub Actions
- Repository: `<org>/cpp-mcp`
- Workflow: `ci.yml`
- Environment: `pypi`

---

## 3. Version bumping

The single source of truth for the version is `src/cpp_mcp/__init__.py`:

```python
__version__: str = "0.1.0"
```

`pyproject.toml` delegates to `hatchling`; the `version` field in `[project]` must match.
To bump:

1. Edit `src/cpp_mcp/__init__.py` — update `__version__`.
2. Edit `pyproject.toml` — update `version = "..."` under `[project]`.
3. Commit: `git commit -m "chore: bump version to X.Y.Z"`.
4. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The `release` job in CI triggers on the tag push and publishes to PyPI.

---

## 4. Local build verification

Before pushing a release tag, verify the build locally:

```bash
cd /Users/husam/workspace/cpp-mcp

# Full lint + type check
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy --strict src

# Full test suite (327 expected passing, 1 skipped without NEO4J_TEST_URI)
uv run pytest -q

# Build distributions
uv build
ls dist/
# cpp_mcp-0.1.0-py3-none-any.whl
# cpp_mcp-0.1.0.tar.gz

# Smoke-install the wheel in a clean venv
python3 -m venv /tmp/cpp-mcp-smoke
/tmp/cpp-mcp-smoke/bin/pip install dist/cpp_mcp-0.1.0-py3-none-any.whl
CPP_MCP_ALLOWED_ROOTS=/tmp /tmp/cpp-mcp-smoke/bin/cpp-mcp --help 2>&1 | head -5
```

---

## 5. CI environment notes

- Runner: `ubuntu-latest` (GitHub-hosted).
- libclang: installed via `apt install libclang-dev` in the test job; the `clang` Python
  package auto-discovers the system library.
- `uv` is installed using the official `astral-sh/setup-uv@v4` action.
- No secrets are required for the `lint` and `test` jobs.
- The `release` job requires the `pypi` GitHub Actions environment and a PyPI trusted
  publisher configured (no stored API token).

---

## 6. Rollback

This is a PyPI package, not a running service. "Rollback" means:
- Do not yank unless the release is actively harmful (yanked versions still install with
  `pip install cpp-mcp==X.Y.Z`).
- If a broken release is published: yank via PyPI UI or `twine` / `uv publish --yank`.
- Users pin via `pip install cpp-mcp==X.Y.Z` or lockfiles.

---

## 7. On-call / maintenance notes

- libclang ABI: `clang>=17,<20` pin in `pyproject.toml`. If a new LLVM major release breaks
  the ABI, update the pin and re-test. The Python `clang` package version must match the
  system libclang major version.
- Memory: cache capacity `CPP_MCP_CACHE_CAPACITY` (default 128). Operators on
  memory-constrained hosts should set to 16. See design.md §10.
- No long-running process to monitor; the server is spawned by the MCP host and exits when
  the host disconnects.
- HTTP transport (P1) is not yet implemented. When implemented, bind defaults to `127.0.0.1`
  only; no auth in v1 (ADR-10).

---

References:
- design.md §5 (transport), §6 (config), §10 (memory note)
- plan.md (Story 1 — packaging, pyproject.toml shape)
- implementation-notes.md (Story 1 — hatchling build backend, version)
- test-report.md (327 passing, 1 skipped — pre-release baseline)
- Cognee tags: task:cpp-mcp, role:devops
