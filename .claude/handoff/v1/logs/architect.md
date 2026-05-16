# Architect log — cpp-mcp v1

run_id: cpp-mcp-1
date: 2026-05-16
role: architect

## Inputs read
- CHARTER.md
- requirements.md (14 stories, 17 OQs)
- scenarios.md (BA-authored, 2 additional OQs: OQ-NEW-1, OQ-NEW-2)

## Deliverables written
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/design.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-1.md   (tool surface + per-tool scope)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-2.md   (concurrency: single libclang worker)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-3.md   (allowed roots = list via env var)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-4.md   (symlinks: resolve-then-check)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-5.md   (AST cap: 5000 nodes + 1 MiB)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-6.md   (TU cache: OrderedDict LRU + mtime poll)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-7.md   (GraphDB: Neo4j MVP, Driver Protocol)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-8.md   (Error envelope shape + closed enum)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-9.md   (OQ-NEW-1, OQ-NEW-2 semantics)
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-10.md  (Transport: MCP SDK + loopback-only HTTP, no auth v1)

All 10 ADRs Status: accepted. Invariant I2 satisfied.

## OQ resolution coverage
- All 17 OQ-N from product-manager: resolved in design.md §7 (table) with ADR citations.
- OQ-NEW-1: ADR-9 (INVALID_ARGUMENT for file-typed build_path).
- OQ-NEW-2: ADR-9 (PARSE_ERROR only on zero-node TU + fatal diagnostics; malformed compile_commands.json → silent default fallback).

## Key decisions (3 bullets)
1. Concurrency: single-process, single libclang worker thread + asyncio for HTTP — chosen because libclang Index is not concurrent-parse-safe and per-thread indexes would defeat the shared TU cache.
2. GraphDB MVP = Neo4j via Bolt, isolated behind a `GraphDriver` Protocol so a Cognee driver can be added later without touching tool code.
3. Allowed roots = colon-separated list via `CPP_MCP_ALLOWED_ROOTS` env var; symlinks are resolved with `os.path.realpath` then required to stay under at least one configured root (rejects escape, supports legitimate symlinked build trees).

## Next role hint
→ senior-developer: read design.md + all adr-*.md, produce plan.md mapping each US to a sequenced set of files-to-touch with exit-criteria commands (pytest selectors per scenario tag, ruff/mypy invocations).

## Notes for senior-developer
- BDD scenario tags in scenarios.md (`@SC-US-N-M`) are intended pytest-bdd markers — preserve them.
- The single libclang worker invariant (ADR-2) means `core/clang_session.py` is the only module importing `clang.cindex`; keep it that way.
- `path_guard.validate_path` is the only place that does symlink resolution; downstream code uses the returned realpath.
- Error envelope is enforced by a decorator `error_envelope.wrap_tool` applied at registration time; tool bodies should raise typed exceptions, not return error dicts directly.
