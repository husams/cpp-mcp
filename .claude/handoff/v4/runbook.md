---
run_id: cpp-mcp-v4
role: devops
date: 2026-05-17
target: local macOS — stdio MCP server (no cluster)
---

# Runbook — cpp-mcp v4 Local Install

## Trigger

Use this runbook when installing or upgrading the `cpp-mcp` stdio MCP server on a
local macOS machine after a v4 code drop. Also use for re-instating the Claude Code
MCP config entry after a Python env rebuild.

## Prerequisites

1. macOS with Homebrew available.
2. `uv` installed: `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`.
3. Rust toolchain available if running IndraDB e2e tests: `rustup` installed and
   `~/.cargo/bin` on `$PATH`.
4. Claude Code CLI installed (for MCP config reload).
5. Pre-flight resource check passed:
   ```bash
   sysctl hw.memsize hw.ncpu && df -h /
   ```
   Stop if RAM < 4 GiB free or disk (`/`) < 10 GiB available.

---

## Steps

### Step 1 — Commit v4 working-tree changes

The v4 working tree contains stories S2–S7 uncommitted. Commit before any test run
so rollback is a clean revert.

```bash
cd /Users/husam/workspace/cpp-mcp

# Stage all v4 changes (verify scope with git diff --stat first)
git diff --stat
git add -A
git commit -m "v4: protobuf pin, insert-count metrics, harness, e2e tests, README"
```

If the coordinator has already committed, skip to Step 2.

### Step 2 — Sync the virtual environment with all extras

```bash
cd /Users/husam/workspace/cpp-mcp

# Resolve all optional dependencies (dev + all graphdb backends)
uv sync --all-extras
```

This installs:
- `indradb>=3.0,<4` and `protobuf<4` (graphdb-indradb extra, protobuf pin is v4 fix)
- `neo4j>=5,<6` (graphdb-neo4j extra)
- All dev tools: ruff, mypy, pytest, pytest-bdd, pytest-asyncio, pytest-cov

For a **runtime-only** install (no dev tools, one backend):

```bash
# IndraDB backend only
uv sync --extra graphdb-indradb

# Neo4j backend only
uv sync --extra graphdb-neo4j

# Both backends, no dev tools
uv sync --extra graphdb
```

See `README.md §Install` for the full option table.

### Step 3 — Verify import and tool registration

```bash
uv run python -c "import cpp_mcp; print('import ok')"
uv run python -c "import indradb; print('indradb import ok')"
uv run python -c "import cpp_mcp.graphdb.indradb_driver; print('driver import ok')"
```

All three should print without error. If `indradb` import fails, the protobuf pin
may not have resolved — run `uv sync --extra graphdb-indradb` again.

### Step 4 — Run Gate 1: default test suite

```bash
cd /Users/husam/workspace/cpp-mcp
uv run pytest -q
```

Expected result: **618 passed, 6 skipped, 18 deselected, 1 warning**

Acceptable skips (all environment-gated):
- `tests/bdd/test_export_to_indradb.py` — `INDRADB_TEST_URI` not set
- `tests/unit/test_cognee_driver.py` (x3) — `COGNEE_BASE_URL` not set
- `tests/unit/test_graphdb_additions.py` — `NEO4J_TEST_URI` not set

The 1 warning is a pre-existing `neo4j` DeprecationWarning (Driver destructor). Advisory only.

### Step 5 — Bring up the IndraDB daemon (in-memory, for e2e tests)

This step is required only to run the integration suite (Gate 2). Skip if you only
need the MCP server running.

**One-time Rust/cargo setup (if not already installed):**

```bash
# Install rustup
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# Install the IndraDB server binary
cargo install indradb
```

Build time: approximately 2–5 minutes on first install. `~/.cargo/bin/indradb-server`
is the resulting binary.

If `cargo install indradb` fails with a protobuf compile error, install `protoc` first:

```bash
brew install protobuf
cargo install indradb
```

**Start the daemon (runs in foreground; open a separate terminal):**

```bash
indradb-server memory
```

The daemon listens on `0.0.0.0:27615` by default. Verify it is up:

```bash
nc -z 127.0.0.1 27615 && echo "daemon ready" || echo "daemon not ready"
```

The daemon holds all graph data in RAM. State is wiped when the process exits. No
disk cleanup is needed after shutdown.

### Step 6 — Run Gate 2: integration suite against live IndraDB daemon

With the daemon running in a separate terminal:

```bash
cd /Users/husam/workspace/cpp-mcp
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 \
  uv run pytest -m integration -q
```

Expected result: **18 passed, 624 deselected** (run time approximately 43 seconds)

The `INDRADB_AUTOSTART=1` flag instructs the fixture to (re)start its own managed
daemon process. If the daemon from Step 5 is already running on that port, the
fixture's autostart daemon will fail to bind — either stop the Step 5 daemon first,
or omit `INDRADB_AUTOSTART=1` and rely on the already-running instance:

```bash
# With daemon already running externally — omit AUTOSTART
INDRADB_TEST_URI=grpc://127.0.0.1:27615 \
  uv run pytest -m integration -q
```

### Step 7 — (Re)install in Claude Code MCP config if needed

The existing `~/.claude.json` entry (confirmed present):

```json
"cpp-mcp": {
  "type": "stdio",
  "command": "uv",
  "args": ["--directory", "/Users/husam/workspace/cpp-mcp", "run", "cpp-mcp"],
  "env": {"CPP_MCP_ALLOWED_ROOTS": "/"}
}
```

This entry is correct and requires no change for v4. The `uv run cpp-mcp` command
invokes `cpp_mcp.server.app:main` (declared in `[project.scripts]` in `pyproject.toml`).

To narrow the allowed root to a specific project (optional, more secure):

```json
"env": {"CPP_MCP_ALLOWED_ROOTS": "/Users/husam/workspace/your-cpp-project"}
```

After any `~/.claude.json` edit, restart Claude Code to reload the MCP server process.

**No restart needed** if only Python source files changed — `uv run` resolves fresh
each time Claude Code launches the stdio process.

---

## Verification

After completing Steps 1–4, the install is verified. Summarised pass counts:

| Gate | Command | Expected |
|---|---|---|
| Gate 1 (default) | `uv run pytest -q` | 618 passed, 6 skipped, 18 deselected |
| Gate 2 (integration) | `INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m integration -q` | 18 passed, 624 deselected |

Deviation from these exact counts indicates a dependency or environment mismatch.

Smoke-check the MCP server itself (in-process, no daemon required):

```bash
uv run python -c "
from cpp_mcp.server.app import build_server
s = build_server()
print('server tools:', [t.name for t in s.list_tools()])
"
```

Expected: 7 tool names printed without error.

---

## Rollback

**Scenario A: all v4 stories committed in one or more commits after 2d9a7ac.**

Identify the v4 commit range:
```bash
git log --oneline 2d9a7ac..HEAD
```

Revert in reverse order (most-recent first):
```bash
git revert --no-edit <newest-v4-commit>
# repeat for each v4 commit
uv sync --all-extras   # re-resolve deps after toml revert
uv run pytest -q       # confirm returns to v3 pass count
```

**Scenario B: v4 changes not yet committed (working tree only).**

Discard all uncommitted v4 changes:
```bash
git restore .
git clean -fd tests/integration/ tests/unit/test_indradb_driver_insert_counts.py \
               tests/unit/test_indradb_driver_insert_boundary.py \
               tests/unit/test_no_broken_docker_image.py
uv sync --all-extras
```

After either scenario, the test suite should return to the v3 baseline:
```
590 passed, 6 skipped
```
(v3 figure from memory file `project_graphdb_multi.md`).

---

## On-call notes

- **`uv sync` fails to resolve protobuf**: the `graphdb-indradb` extra pins `protobuf<4`.
  If another package in the venv requires `protobuf>=4`, resolution will fail. Inspect
  with `uv pip compile -o /dev/stdout --extra graphdb-indradb`. Fix: audit conflicting
  package and file a v5 story to relax the pin when indradb ships protobuf-4 stubs.

- **`indradb-server memory` exits immediately**: usually missing `protoc` during cargo
  build, or the binary is built against an incompatible glibc on non-macOS systems.
  On macOS, `brew install protobuf` then `cargo install --force indradb`.

- **Gate 1 count drops below 618**: likely a missing `uv sync --all-extras`. Run
  `uv sync --all-extras` and retry.

- **Gate 2 count < 18**: check `INDRADB_TEST_URI` is set, daemon is running on port
  27615, and `uv sync --extra graphdb-indradb` has been applied.

- **Claude Code does not see updated MCP tools**: restart Claude Code (Cmd+Q, reopen).
  The stdio process is launched fresh per session; no manual signal is needed.

- **22,989 silently-dropped edge attempts on os.cc**: expected and documented in
  ADR-17 §Follow-ups. `edges_attempted=23169`, `edges_written=180` is correct v4
  behaviour. Not a bug.

---

## References

- `handoff/v4/deploy-notes.md` — deployment context and working-tree state
- `handoff/v4/test-report.md` — QA sign-off; gate commands; exact pass counts
- `handoff/v4/implementation-notes.md` — per-story deviation log
- `README.md §Install` — uv sync option table
- `README.md §Local development (IndraDB)` — cargo install + daemon start
- `README.md §Integrate with Claude Code` — MCP config JSON
- `handoff/v3/runbook.md` — v3 URI scheme table, error-code reference (updated by S4)
- ADR-16: `handoff/v4/adr-16.md` (cargo install decision)
- ADR-17: `handoff/v4/adr-17.md` (insert-vs-attempt contract)
- ADR-18: `handoff/v4/adr-18.md` (in-process test harness)
- Cognee tags: `task:cpp-mcp-v4`, `role:devops`
