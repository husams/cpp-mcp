# Deploy notes — cpp-mcp v0.3.0 (task: cpp-mcp-v5-rename)

**Date:** 2026-05-17
**Target context:** local Python process — NO Kubernetes cluster involved
**DEPLOY_DRIFT check:** N/A (not a cluster workload; `kubectl config current-context` is irrelevant)

---

## What is being released

Pure tool-rename release. Zero behavior change in server logic.

- 6 tools: `cpp_get_*` → `get_*` (drop prefix)
- 1 tool: `cpp_export_to_graphdb` → `ingest_code`
- Version bump: `0.1.0` (actual in pyproject.toml pre-v5) → `0.3.0`
- No PyPI publish. Local install only (uv-managed).

## Pre-conditions satisfied

- `test-report.md` has no open QA_DEFECT entries (CHARTER I4 satisfied).
- All S1–S4 exit criteria passed (see `implementation-notes.md` and `test-report.md`).
- Final suite: 642 passed, 6 skipped, 0 failures; lint clean.

## Current state (working tree, not yet committed)

All v5 changes are staged/unstaged in the working tree at HEAD `1ac03ad`. The v5 work has NOT been committed yet. See `git status` output which shows ~60 modified/renamed files.

## Build artifact

Run from project root:

```bash
cd /Users/husam/workspace/cpp-mcp
uv build
```

Expected output:
```
Building source distribution...
Building wheel from source distribution...
Successfully built dist/cpp_mcp-0.3.0.tar.gz
Successfully built dist/cpp_mcp-0.3.0-py3-none-any.whl
```

Artifact paths after build:
- `dist/cpp_mcp-0.3.0.tar.gz`
- `dist/cpp_mcp-0.3.0-py3-none-any.whl`

## Git tag (do NOT execute — for reference only)

After committing all v5 changes:

```bash
git -C /Users/husam/workspace/cpp-mcp tag -a v0.3.0 -m "v0.3.0: drop cpp_ prefix; export_to_graphdb → ingest_code"
```

Do not push tag to remote until PR is merged.

## No PyPI publish

`uv publish` is explicitly out of scope. Do not run it.

## MCP client migration

### Tool name diff (0.2.x → 0.3.0)

| 0.2.x name (old)            | 0.3.0 name (new)        |
|-----------------------------|-------------------------|
| `cpp_get_ast`               | `get_ast`               |
| `cpp_get_definition`        | `get_definition`        |
| `cpp_get_references`        | `get_references`        |
| `cpp_get_type_info`         | `get_type_info`         |
| `cpp_get_header_info`       | `get_header_info`       |
| `cpp_get_preprocessor_state`| `get_preprocessor_state`|
| `cpp_export_to_graphdb`     | `ingest_code`           |

**Breaking:** no compatibility aliases exist. A 0.2.x client calling an old tool name receives MCP `tool not found`.

### Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)

No changes to the server invocation command are needed. The `mcpServers` entry for cpp-mcp stays identical — the server binary/path does not change.

After upgrading, existing tool-call references in saved conversations using old names will produce `tool not found`. Users must call the new names going forward.

### Cursor (`.cursor/mcp.json` or `~/.cursor/mcp.json`)

Same as Claude Desktop: server command unchanged; tool names in prompts/rules referencing `cpp_*` must be updated to unprefixed names.

### Generic `.mcp.json`

```json
{
  "mcpServers": {
    "cpp-mcp": {
      "command": "uv",
      "args": ["run", "--project", "/Users/husam/workspace/cpp-mcp", "python", "-m", "cpp_mcp"]
    }
  }
}
```

The `command`/`args` block is unchanged from 0.2.x. No config file edit required unless a project `.mcp.json` hard-codes old tool names in `allowed_tools` or similar filtering keys.

## Rollback

To revert to the last good v4 commit (`1ac03ad`):

```bash
git -C /Users/husam/workspace/cpp-mcp checkout 1ac03ad -- .
uv sync --project /Users/husam/workspace/cpp-mcp
```

Then reinstall into any MCP client that was updated. The old tool names (`cpp_*`) will be available again.

If the v5 commit has already been tagged `v0.3.0`, the rollback commit should be re-tagged `v0.2.x-rollback` locally for traceability (do not push).

## References

- `implementation-notes.md`: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/implementation-notes.md`
- `test-report.md`: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/test-report.md`
- `plan.md`: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/plan.md`
- ADR-20 (no shims): `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-20.md`
- ADR-21 (grep gate): `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-21.md`
- Wiki: `~/workspace/wiki/pages/code/cpp-mcp.md`
