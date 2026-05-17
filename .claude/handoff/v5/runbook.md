# Runbook — cpp-mcp v0.3.0 operator guide

**task-slug:** cpp-mcp-v5-rename
**scope:** local Python MCP server — NOT a Kubernetes workload
**audience:** operator responding to user reports after upgrading to 0.3.0

---

## Trigger

User reports one of:
- "Tool `cpp_get_ast` (or any `cpp_*` tool) not found after upgrade"
- "MCP client says tool not found after restarting server"
- "My Claude Desktop / Cursor stopped finding C++ tools"

---

## Prerequisites

- Access to the machine running `cpp-mcp`
- `uv` available (`uv --version`)
- Project root at `/Users/husam/workspace/cpp-mcp` (adjust if installed elsewhere)
- MCP client config location known (see Step 3)

---

## Steps

### 1. Confirm server version

```bash
grep -E '^version' /Users/husam/workspace/cpp-mcp/pyproject.toml
```

Expected: `version = "0.3.0"`

If it reads `0.1.0` or `0.2.0`, the upgrade did not land — stop here and follow the "upgrade from old commit" path in deploy-notes.md.

### 2. Confirm tool registry (server must not be running)

```bash
cd /Users/husam/workspace/cpp-mcp
uv run python -c "
import asyncio
from cpp_mcp.server.app import build_server
mcp = build_server()
tools = asyncio.run(mcp.list_tools())
names = [t.name for t in tools]
print(names)
assert len(names) == 7, f'expected 7, got {len(names)}'
assert 'ingest_code' in names
assert not any('cpp_' in n for n in names)
print('REGISTRY OK')
"
```

Expected output:
```
['get_definition', 'get_references', 'get_type_info', 'get_ast', 'get_header_info', 'get_preprocessor_state', 'ingest_code']
REGISTRY OK
```

If `cpp_` names appear, source files were not updated — check git status and re-run the v5 install.

### 3. Locate and inspect MCP client config

#### Claude Desktop

```bash
cat "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

#### Cursor

```bash
# Project-local first, then user-global
ls .cursor/mcp.json 2>/dev/null || ls "$HOME/.cursor/mcp.json" 2>/dev/null
cat .cursor/mcp.json 2>/dev/null || cat "$HOME/.cursor/mcp.json" 2>/dev/null
```

#### Generic `.mcp.json`

```bash
ls .mcp.json 2>/dev/null && cat .mcp.json
```

**What to look for:** any `allowed_tools` or `tool_names` filter key that lists old `cpp_*` names. The server invocation command itself does not need to change.

### 4. Diagnose the broken tool name

Ask the user which exact tool name they called. Map it to the new name using this table:

| User reported (old)          | Correct name (new)       |
|------------------------------|--------------------------|
| `cpp_get_ast`                | `get_ast`                |
| `cpp_get_definition`         | `get_definition`         |
| `cpp_get_references`         | `get_references`         |
| `cpp_get_type_info`          | `get_type_info`          |
| `cpp_get_header_info`        | `get_header_info`        |
| `cpp_get_preprocessor_state` | `get_preprocessor_state` |
| `cpp_export_to_graphdb`      | `ingest_code`            |

There are NO aliases. The old names will always return `tool not found` on v0.3.0. This is intentional per ADR-20 and ADR-21.

### 5. Restart the MCP server in the client

In Claude Desktop: quit and relaunch the application.

In Cursor: run `Developer: Reload Window` from the command palette.

For a stdio server started manually:

```bash
# Kill any running instance
pkill -f "python -m cpp_mcp" 2>/dev/null || true
# Restart
cd /Users/husam/workspace/cpp-mcp
uv run python -m cpp_mcp
```

### 6. Smoke-test the new names

With the server running (HTTP transport) or via a test invocation:

```bash
cd /Users/husam/workspace/cpp-mcp
uv run pytest tests/bdd/test_ingest_code.py -q --no-header -m "not integration"
uv run pytest tests/unit/test_rename_invariant.py -q --no-header
```

Both must pass. If either fails, there is a source-level regression — escalate by opening an issue in the project repo.

---

## Verification (post-fix check)

All of these must pass before closing the report:

```bash
# 1. Version
grep -E '^version = "0\.3\.0"' /Users/husam/workspace/cpp-mcp/pyproject.toml

# 2. No old names in source
! grep -RIE 'cpp_(get|export)_' /Users/husam/workspace/cpp-mcp/src/ /Users/husam/workspace/cpp-mcp/tests/

# 3. Registry shape
cd /Users/husam/workspace/cpp-mcp && uv run python -c "
import asyncio; from cpp_mcp.server.app import build_server
mcp = build_server()
tools = asyncio.run(mcp.list_tools())
names = [t.name for t in tools]
assert len(names) == 7 and 'ingest_code' in names and not any('cpp_' in n for n in names)
print('PASS')
"

# 4. Unit suite
cd /Users/husam/workspace/cpp-mcp && uv run pytest -q --no-header --ignore=tests/integration
# Expected: 642 passed, 6 skipped (or higher if additional tests added)
```

---

## Rollback

If rollback is required (user cannot migrate to new names and needs immediate relief):

```bash
# Revert working tree to v4 commit
git -C /Users/husam/workspace/cpp-mcp checkout 1ac03ad -- .
uv sync --project /Users/husam/workspace/cpp-mcp
```

This restores all `cpp_*` tool names. Old names become callable again. No MCP client config changes needed.

Document the rollback reason and notify the user that v0.3.0 tool names are a hard breaking change — 0.2.x and 0.3.0 cannot coexist in the same server process.

---

## On-call notes

- There are NO shims, aliases, or fallback routes. Old names are gone. This is by design (ADR-20, ADR-21).
- The server startup command and all argument shapes are identical between 0.2.x and 0.3.0.
- IndraDB integration tests require `INDRADB_TEST_URI` env var; 2 tests will skip without it — this is normal.
- If the user reports exactly 16 integration tests passing (not 18), that is expected when no live IndraDB daemon is running.
- Wiki page for this project: `~/workspace/wiki/pages/code/cpp-mcp.md`
- Migration guide in README: `/Users/husam/workspace/cpp-mcp/README.md` (section "Migration from 0.2.x")
- CHANGELOG: `/Users/husam/workspace/cpp-mcp/CHANGELOG.md`

---

## References

- `deploy-notes.md`: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/deploy-notes.md`
- `test-report.md`: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/test-report.md`
- ADR-20 (no shims): `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-20.md`
- ADR-21 (grep gate): `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-21.md`
- Wiki: `~/workspace/wiki/pages/code/cpp-mcp.md`
- Cognee tags: `task:cpp-mcp-v5-rename`, `role:devops`
