---
run_id: cpp-mcp-v4
role: devops
date: 2026-05-17
---

# Devops Log — cpp-mcp v4

## Context

Target is local macOS (stdio MCP server, not Kubernetes). DEPLOY_DRIFT check is N/A;
context verification = `which uv && uv --version && uv run python -c "import cpp_mcp"`.

## Pre-flight result

sysctl hw.memsize=34359738368 (32 GiB), hw.ncpu=10. df / Avail=66 GiB. All thresholds clear.

## Inputs confirmed

- CHARTER.md: read, I4 checked — test-report.md has no open QA_DEFECT entries.
- plan.md: seven stories S1–S7, exit criteria verified.
- design.md: ADR-16/17/18 accepted; in-process fastmcp.Client harness; cargo install IndraDB path.
- test-report.md: Gate 1 = 618/0 passed/failed; Gate 2 (daemon) = 18/0.
- implementation-notes.md: S1–S7 all documented; key deviations noted.

## Decisions made

1. Entry point form: `uv run cpp-mcp` (not `uv run python -m cpp_mcp`) — confirmed from
   `[project.scripts]` in pyproject.toml.
2. Existing `~/.claude.json` cpp-mcp entry is correct; no config change required.
3. Daemon AUTOSTART conflict documented: running daemon externally and using
   INDRADB_AUTOSTART=1 simultaneously will fail to bind on port 27615.
4. Rollback covers both committed and uncommitted scenarios.
5. `free -m` replaced with `sysctl hw.memsize hw.ncpu` for macOS pre-flight.

## Outputs

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/deploy-notes.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/runbook.md`

No manifest, CI, Vault, or Cilium changes (local install — none apply).

## Cognee tags

task:cpp-mcp-v4, role:devops
