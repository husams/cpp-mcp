# Architect log — cpp-mcp-v5-rename

Date: 2026-05-17

## Inputs read
- CHARTER.md, requirements.md, scenarios.md (this handoff)
- Verified: `src/cpp_mcp/tools/` layout (6 of 7 files already unprefixed; only `export_to_graphdb.py` mismatches)
- Verified: `src/cpp_mcp/core/tu_cache.py` — cache key is `(file, build, flags_hash)`; tool-name not a dimension

## Decisions
- ADR-19 (OQ-1, cache scope): schema-untouched; tool-name not in any key — verified.
- ADR-20 (OQ-2, file rename scope): rename only `export_to_graphdb.py` → `ingest_code.py` via `git mv`; six others already match.
- ADR-21 (OQ-3, grep gate): authoritative command `grep -RIE 'cpp_(get|export)_' src/ tests/` exit 1. No shim exclusion (aliases forbidden by AC-R4-3).
- All three ADRs `Status: accepted`. No ADR_UNRESOLVED.

## Deliverables
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/design.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-19.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-20.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v5/adr-21.md

## Dependency order for senior-developer
R1 → R2 → R3 → R4, single PR, sub-commits optional.

## Notes
Python project (uv + pytest + ruff). Test parity is a hard gate (618/6 unit, 18 integration). FastMCP introspection snippet in design.md is illustrative — sr-dev to confirm API.
