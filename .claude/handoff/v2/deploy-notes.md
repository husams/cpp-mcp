---
run_id: fastmcp-migration-v2
stage: devops
date: 2026-05-16
task-slug: fastmcp-migration
target: local-install (no cluster)
---

# Deploy Notes: FastMCP Migration (v2)

## Trigger

Release `cpp-mcp v0.1.0` with FastMCP 3.x transport replacing the hand-rolled
stdio/HTTP glue. This is a local-only packaging release; no Kubernetes, no ArgoCD, no
manifests.

---

## Prerequisites

- Python 3.11+ available (`python --version`).
- `uv` installed: <https://docs.astral.sh/uv/getting-started/installation/>.
- libclang system library present (`apt install libclang-dev` / `brew install llvm`).
- `CPP_MCP_ALLOWED_ROOTS` set to at least one existing absolute directory path.
- All exit-gate commands pass (verified by QA; test-report.md: 472 passed / 0 failed).

---

## Steps

### 1. Clone / update the repository

```bash
git clone <repo-url> cpp-mcp   # or: git pull origin main
cd cpp-mcp
```

### 2. Build wheel and sdist

```bash
uv build
```

Artifacts produced (verified 2026-05-16):

```
dist/cpp_mcp-0.1.0-py3-none-any.whl
dist/cpp_mcp-0.1.0.tar.gz
```

### 3. Install into target environment

**Option A — editable dev install (contributor workflow)**

```bash
uv pip install -e ".[dev]"
```

**Option B — wheel install (user / CI workflow)**

```bash
pip install dist/cpp_mcp-0.1.0-py3-none-any.whl
# or
uv pip install dist/cpp_mcp-0.1.0-py3-none-any.whl
```

**Option C — install optional graphdb extra**

```bash
pip install "dist/cpp_mcp-0.1.0-py3-none-any.whl[graphdb]"
```

### 4. Verify console script resolves

```bash
which cpp-mcp      # must return a path inside the active venv/bin
cpp-mcp --version  # FastMCP prints version on startup or exits cleanly
```

### 5. Smoke-test: stdio JSON-RPC handshake

```bash
export CPP_MCP_ALLOWED_ROOTS="/path/to/your/cpp/project"
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | cpp-mcp
```

Expected: a JSON-RPC response frame on stdout, no `Traceback` on stderr.

### 6. Smoke-test: HTTP /health endpoint

```bash
export CPP_MCP_ALLOWED_ROOTS="/path/to/your/cpp/project"
export CPP_MCP_TRANSPORT=http
cpp-mcp &
SERVER_PID=$!
sleep 1
curl -sf http://127.0.0.1:8000/health   # must print: OK
kill $SERVER_PID
unset CPP_MCP_TRANSPORT
```

### 7. Wire into Claude Code (`claude_desktop_config.json` or MCP settings)

Add to your MCP client configuration (paths below are illustrative):

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

For Claude Code CLI, update `~/.claude/settings.json` or the project-level
`.claude/settings.json` under `mcpServers`.

---

## Version bump policy

The project uses `pyproject.toml` `version = "0.x.y"` (no version plugin; update manually
before each release):

1. Edit `version` in `[project]` section of `pyproject.toml`.
2. Run `uv build` — the wheel name reflects the new version.
3. Commit: `git commit -m "chore: bump version to 0.x.y"`.
4. Tag: `git tag v0.x.y && git push origin v0.x.y`.

FastMCP is pinned `fastmcp~=3.1.0` (`>=3.1.0, <3.2.0`). Before bumping to a new FastMCP
minor, follow the upgrade-check procedure in `runbook.md §4`.

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
# Expected: 472 passed, 4 skipped (or higher)
# The 4 skips are env-optional: 3x COGNEE_BASE_URL not set, 1x NEO4J_TEST_URI not set

# Wheel build
uv build
ls dist/cpp_mcp-0.1.0-py3-none-any.whl   # must exist
```

---

## Rollback

### Roll back to a previous installed version

If the installed wheel is from PyPI or a private index:

```bash
pip install "cpp-mcp==<prev-version>"
# or
uv pip install "cpp-mcp==<prev-version>"
```

### Roll back via uv.lock (lock file revert)

If a `uv update` pulled in a bad FastMCP patch version before a release was cut:

```bash
# Restore known-good lock from git history
git checkout <good-commit> -- uv.lock

# Reinstall exactly what the lock says — no resolution
uv sync --frozen
```

### Roll back the FastMCP pin

To revert to an older FastMCP minor, edit `pyproject.toml`:

```toml
fastmcp~=3.0.0   # or whichever working minor
```

Then:

```bash
uv lock
uv sync --frozen
uv run pytest -q   # must pass before releasing
```

---

## On-call notes

- **`DEPLOY_DRIFT` taxonomy**: not applicable — local install only; no cluster context.
- **All transport config is env-var driven** — `main()` in `server/app.py` has no CLI flags.
  There is no `cpp-mcp http` subcommand. Set `CPP_MCP_TRANSPORT=http` to enable HTTP.
- **Lifespan owns all state** — there is no persistent data to migrate on upgrade. A fresh
  install is always clean.
- **The `mcp>=1.0` dependency** in `pyproject.toml` coexists with `fastmcp~=3.1.0`; FastMCP
  pulls its own compatible `mcp` version transitively. This is intentional (see plan.md §S1
  note: "keep `mcp>=1.0` for now; S7 may remove it"). No action needed unless a conflict
  surfaces during `uv lock`.
- **4 skipped tests** are environment-optional and not a defect. Do not block a release
  because of them.

---

## References

- Handoff inputs: `design.md`, `plan.md`, `implementation-notes.md`, `test-report.md`
- Runbook: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/runbook.md`
- CHARTER: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/CHARTER.md`
- Cognee tags: `task:fastmcp-migration`, `role:devops`
