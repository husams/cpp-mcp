---
run_id: cpp-mcp-v4
role: devops
date: 2026-05-17
target: local (macOS, stdio MCP server — no Kubernetes cluster)
DEPLOY_DRIFT: N/A — this is a local user install. No kubectl context exists.
  Context verification = `which uv && uv --version && uv run python -c "import cpp_mcp; print('ok')"`.
---

# Deploy Notes — cpp-mcp v4

## Target

Local macOS machine. `cpp-mcp` is a **stdio MCP server** launched by Claude Code; it is
not deployed to Kubernetes. There is no cluster context, no ArgoCD app, no Helm chart.

## Pre-flight resource check (macOS)

Run before committing any install step:

```bash
sysctl hw.memsize hw.ncpu && df -h /
```

Thresholds:
- RAM (`hw.memsize`) < 4 GiB → stop, free memory or use a remote machine.
- Disk (`/` Avail column) < 10 GiB → stop, free disk before proceeding.
- 10+ CPUs and 66 GiB+ free disk confirmed on the author's machine (2026-05-17).

## Working-tree state at v4 ship

`git log --oneline` at QA sign-off:

```
c17f9ec S1: commit Identifier→str patch, fix fake_indradb compat, add grep test
2d9a7ac Add pluggable graphdb backends: Neo4j + IndraDB (handoff/v3)
```

Stories S2–S7 are in the working tree **uncommitted** as of handoff. The coordinator
must commit all changes before rollback is meaningful. Recommended commit order per
plan.md dependency graph:

```
S2 → S1 (already committed) → S3 → S4 → S5 → S7 → S6
```

Or a single "v4 ship" commit bundling all working-tree changes.

## Install steps

See `runbook.md` for the numbered, copy-pasteable procedure.

## MCP server entry point

The installed entry point is:

```
uv run cpp-mcp
```

mapping to `cpp_mcp.server.app:main` (declared in `[project.scripts]` in `pyproject.toml`).

The existing `~/.claude.json` MCP entry for `cpp-mcp` already uses:

```json
{
  "type": "stdio",
  "command": "uv",
  "args": ["--directory", "/Users/husam/workspace/cpp-mcp", "run", "cpp-mcp"],
  "env": {"CPP_MCP_ALLOWED_ROOTS": "/"}
}
```

This is the correct form. No change is needed unless `CPP_MCP_ALLOWED_ROOTS` should be
narrowed to a specific project root.

## Verification gates (from test-report.md)

Gate 1 — default suite (integration skipped by addopts):
```
618 passed, 6 skipped, 18 deselected, 1 warning
```

Gate 2 — integration suite against live IndraDB daemon:
```
18 passed, 624 deselected in 43.38s
```

A successful local install reproduces these numbers exactly. Deviation indicates an
environment or dependency mismatch.

## v4 scope summary

| Story | Change | Files |
|---|---|---|
| S1 | `Identifier→str` patch committed; structural grep test | `indradb_driver.py`, test |
| S2 | `protobuf<4` pin in `graphdb-indradb` extra | `pyproject.toml`, `uv.lock` |
| S3 | Insert-vs-attempt metrics; `nodes_attempted`/`edges_attempted` fields | 4 src files, fake, BDD step |
| S4 | Delete broken Docker compose; README Local dev section | deleted `indradb-compose.yml`, `README.md` |
| S5 | In-process `fastmcp.Client` test harness; `integration` marker | `conftest.py`, `pyproject.toml`, 2 new test files |
| S6 | Live IndraDB e2e test (env-gated) | `tests/integration/conftest.py`, `test_indradb_e2e.py` |
| S7 | README install extras; `DEPENDENCY_MISSING` wording | `README.md`, 2 driver files |

## Known advisory items (no action required for v4)

1. 22,989 edge attempts silently dropped by IndraDB (external-symbol edges) — ADR-17 §Follow-ups.
2. Neo4j `DeprecationWarning` on Driver destructor — pre-existing; v5 cleanup.
3. `SC-V4-1-04` validated implicitly (18 deselected), not by subprocess assertion — v5 belt-and-suspenders.

## References

- `handoff/v4/runbook.md` — numbered install procedure
- `handoff/v4/test-report.md` — QA sign-off, no open QA_DEFECT entries
- `README.md` §Install, §Local development (IndraDB), §Integrate with Claude Code
- `handoff/v4/implementation-notes.md` — per-story deviations
- Cognee tags: `task:cpp-mcp-v4`, `role:devops`
