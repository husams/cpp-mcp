---
run_id: graphdb-multi-v3
stage: devops
date: 2026-05-16
task-slug: graphdb-multi
target: local-install (no cluster)
---

# Deploy Notes: graphdb-multi (v3) — Pluggable GraphDB Backends

## Trigger

Release `cpp-mcp v0.2.0` adding `IndraDBDriver` alongside the existing `Neo4j` driver,
URI-scheme-based dispatch via `select_driver`, the `DEPENDENCY_MISSING` error code,
and split optional extras (`graphdb-neo4j`, `graphdb-indradb`, `graphdb`).

This is a local-only packaging release. No Kubernetes, no ArgoCD, no manifests.
DEPLOY_DRIFT: not applicable — local install only; no cluster context.

---

## Prerequisites

- Python 3.11+ available (`python --version`).
- `uv` installed: <https://docs.astral.sh/uv/getting-started/installation/>.
- libclang system library present (`apt install libclang-dev` / `brew install llvm`).
- `CPP_MCP_ALLOWED_ROOTS` set to at least one existing absolute directory path.
- All exit-gate commands pass — verified by QA; test-report.md: **590 passed / 0 failed / 6 skipped**.
- Docker available if you intend to run live integration tests (see runbook.md §3).

---

## Steps

### 1. Bump version in pyproject.toml

v3 adds the IndraDB backend as a new additive feature — semver-minor bump:

```
0.1.0 → 0.2.0
```

Edit `[project]` in `pyproject.toml`:

```toml
version = "0.2.0"
```

Commit:

```bash
git commit -m "chore: bump version to 0.2.0"
git tag v0.2.0
```

### 2. Verify lock file is consistent

```bash
uv lock --check
```

If the lock is stale (e.g. after editing `pyproject.toml`):

```bash
uv lock
uv sync --frozen
```

### 3. Install into target environment

**Option A — editable dev install (contributor workflow)**

```bash
uv pip install -e ".[dev]"
```

**Option B — wheel install (user workflow)**

First build:

```bash
uv build
# Produces: dist/cpp_mcp-0.2.0-py3-none-any.whl
#           dist/cpp_mcp-0.2.0.tar.gz
```

Then install:

```bash
uv pip install dist/cpp_mcp-0.2.0-py3-none-any.whl
```

**Option C — install with a specific backend extra**

Neo4j only:
```bash
pip install "cpp-mcp[graphdb-neo4j]==0.2.0"
# or from local wheel:
pip install "dist/cpp_mcp-0.2.0-py3-none-any.whl[graphdb-neo4j]"
```

IndraDB only:
```bash
pip install "cpp-mcp[graphdb-indradb]==0.2.0"
# or from local wheel:
pip install "dist/cpp_mcp-0.2.0-py3-none-any.whl[graphdb-indradb]"
```

Both backends (meta-extra):
```bash
pip install "cpp-mcp[graphdb]==0.2.0"
# or from local wheel:
pip install "dist/cpp_mcp-0.2.0-py3-none-any.whl[graphdb]"
```

See runbook.md §2 for the full install matrix including `uv sync --extra` forms.

### 4. Verify console script resolves

```bash
which cpp-mcp       # must return a path inside the active venv/bin
cpp-mcp --version   # must exit cleanly
```

### 5. Smoke-test: stdio JSON-RPC handshake

```bash
export CPP_MCP_ALLOWED_ROOTS="/path/to/your/cpp/project"
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | cpp-mcp
```

Expected: a JSON-RPC response frame on stdout, no `Traceback` on stderr.

### 6. Smoke-test: DEPENDENCY_MISSING error fires with actionable message

Confirm the new error code is visible before installing a backend:

```bash
# In an environment WITHOUT neo4j or indradb installed:
export CPP_MCP_ALLOWED_ROOTS="/path/to/your/cpp/project"
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"cpp_export_to_graphdb","arguments":{"source_file":"/path/to/your/cpp/project/main.cpp","build_path":"/path/to/your/cpp/project","db_uri":"bolt://localhost:7687"}}}' \
  | cpp-mcp
```

Expected response `code` field: `"DEPENDENCY_MISSING"`.
Expected message fragment: `pip install "cpp-mcp[graphdb-neo4j]"`.

### 7. Optional: start a backend daemon and run live tests

See runbook.md §3 for daemon bring-up commands for both Neo4j and IndraDB.

Neo4j quick-start:
```bash
docker run --rm -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=none neo4j:5
export NEO4J_TEST_URI="bolt://localhost:7687"
uv run pytest -q tests/bdd/test_export_to_graphdb.py
```

IndraDB quick-start:
```bash
docker compose -f tests/fixtures/indradb-compose.yml up -d
export INDRADB_TEST_URI="indradb://localhost:27615"
uv run pytest -q tests/bdd/test_export_to_indradb.py
```

### 8. Wire into Claude Code (MCP user-scope registration)

Re-registration is only required if the venv path changed after the v3 install.
v3 introduces no MCP tool-surface breaking change (`cpp_export_to_graphdb` tool
name and schema are unchanged — C-G1 invariant). If the venv path is stable,
the existing registration continues to work.

To register or update, edit `~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "cpp-mcp": {
      "command": "/path/to/venv/bin/cpp-mcp",
      "env": {
        "CPP_MCP_ALLOWED_ROOTS": "/absolute/path/to/your/cpp/project"
      }
    }
  }
}
```

For project-scope registration, use `.claude/settings.json` in the project root
instead of the global `~/.claude/settings.json`.

After editing the settings file, restart the Claude Code session for the updated
MCP server configuration to take effect.

---

## Verification

After install, all of the following must pass:

```bash
# Static gates
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/

# Lock integrity
uv lock --check

# Full test suite
uv run pytest -q
# Expected: 590 passed, 6 skipped (2 @indradb + 1 @neo4j + 3 @cognee)
# All 6 skips are env-gated (see test-report.md skip classification); not defects.

# Wheel build reflects new version
uv build
ls dist/cpp_mcp-0.2.0-py3-none-any.whl   # must exist after version bump

# Exit-gate checks from plan.md S4 (extras pin correctness)
uv sync
test -z "$(uv pip list 2>/dev/null | grep -E '^(neo4j|indradb) ')"   # no backend installed by default

# Runbook content checks
grep -q "DEPENDENCY_MISSING" .claude/handoff/v3/runbook.md
grep -q "GPLv3" .claude/handoff/v3/runbook.md
grep -q "MPL-2.0" .claude/handoff/v3/runbook.md
grep -q "Graph database backends" README.md
```

---

## Rollback

### Roll back to v0.1.0 (previous release)

```bash
pip install "cpp-mcp==0.1.0"
# or
uv pip install "cpp-mcp==0.1.0"
```

### Roll back via uv.lock revert

```bash
git checkout <good-commit> -- uv.lock
uv sync --frozen
```

### Roll back the version bump

If the version was bumped in `pyproject.toml` but not yet pushed or tagged:

```bash
git revert HEAD   # reverts the chore: bump version to 0.2.0 commit
# or manually restore pyproject.toml version = "0.1.0"
```

---

## On-call notes

- **DEPLOY_DRIFT**: not applicable — local install only; no cluster context.

- **`[graphdb]` meta-extra behavior change from v2**: In v2, `pip install cpp-mcp[graphdb]`
  installed only the `neo4j` package. In v3, `[graphdb]` is a meta-extra that pulls both
  `neo4j>=5,<6` AND `indradb>=3.0,<4` (plus transitive `grpcio`/`protobuf`). Operators
  upgrading from v2 who relied on `[graphdb]` for a lean Neo4j-only install should switch
  to `[graphdb-neo4j]` to avoid the IndraDB transitive deps.

- **MCP re-registration**: Only needed if the venv path changed. The `cpp_export_to_graphdb`
  tool name and wire schema are unchanged (C-G1 invariant). No client-side changes needed
  for existing Claude Code users unless the binary path moved.

- **6 skipped tests are not defects**: 2 @indradb (INDRADB_TEST_URI not set), 1 @neo4j
  (NEO4J_TEST_URI not set), 3 @cognee (COGNEE_BASE_URL not set — pre-existing from v2).
  Do not block a release because of them.

- **DEPENDENCY_MISSING ordering**: `DependencyMissingError` is mapped **above**
  `DBUnreachableError` in the exception dispatch table (ADR-13). This ordering is
  tested in `tests/unit/test_dependency_missing.py`; if you ever edit `_EXC_TO_CODE`,
  preserve the order.

- **select_driver fires before path validation**: Unknown URI scheme raises
  `INVALID_ARGUMENT` before `PATH_VIOLATION` or `FILE_NOT_FOUND`. This is intentional
  (ADR-12 ordering, design §2) and tested in `tests/bdd/test_export_to_graphdb.py`
  scenarios SC_US_G3_4a/4b.

- **All transport config is env-var driven**: `CPP_MCP_TRANSPORT=http` enables HTTP
  transport. No CLI flags. Lifespan owns all state — no persistent data to migrate on
  upgrade. See v2 runbook §4 for transport details.

- **Live idempotency proxy caveat** (IndraDB, from QA observation 1): The live `@indradb`
  "Re-exporting idempotent" scenario asserts `result.get("nodes_written", 0) == 0` which
  trivially passes because the tool response does not emit `nodes_written`. Acceptable in
  v3 (live tests are not CI-wired per US-G5/AC-3); fix before wiring `INDRADB_TEST_URI` to CI.

---

## Version bump policy

The project uses `pyproject.toml` `version = "0.x.y"` (updated manually):

| Change type | Bump |
|---|---|
| Backwards-compatible new feature (e.g. new backend, new error code) | minor: `0.1.0 → 0.2.0` |
| Bug fix, internal refactor, no API change | patch: `0.2.0 → 0.2.1` |
| Breaking API change (tool schema change, removed field) | minor: `0.2.0 → 0.3.0` (pre-1.0 policy) |

1. Edit `version` in `[project]` section of `pyproject.toml`.
2. Run `uv build` — the wheel name reflects the new version.
3. Commit: `git commit -m "chore: bump version to 0.x.y"`.
4. Tag: `git tag v0.x.y && git push origin v0.x.y`.

`fastmcp~=3.1.0` remains pinned. Before bumping to a new FastMCP minor, follow
the upgrade-check procedure in v2 `runbook.md §4`.

---

## References

- Runbook (v3, operations detail): `.claude/handoff/v3/runbook.md`
- v2 deploy-notes (FastMCP baseline): `.claude/handoff/v2/deploy-notes.md`
- v2 runbook (startup, transport, upgrade-check): `.claude/handoff/v2/runbook.md`
- CHARTER: `.claude/handoff/v3/CHARTER.md`
- Plan: `.claude/handoff/v3/plan.md`
- Implementation notes: `.claude/handoff/v3/implementation-notes.md`
- Test report: `.claude/handoff/v3/test-report.md`
- ADR-12 (URI dispatch): `.claude/handoff/v3/adr-12.md`
- ADR-13 (DEPENDENCY_MISSING): `.claude/handoff/v3/adr-13.md`
- Cognee tags: `task:graphdb-multi`, `role:devops`
