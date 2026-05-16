---
run_id: graphdb-multi-v3
stage: architect
date: 2026-05-16
status: complete
---

# Architect log — graphdb-multi-v3

## Inputs read
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/CHARTER.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/requirements.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/scenarios.md`
- `src/cpp_mcp/graphdb/{__init__.py, driver.py, neo4j_driver.py, cognee_driver.py}`
- `src/cpp_mcp/tools/export_to_graphdb.py`
- `src/cpp_mcp/core/error_envelope.py`
- `pyproject.toml`
- IndraDB Python client API docs (`indradb.github.io/python-client`).

## Decisions filed
- adr-12.md — URI-scheme dispatch (`select_driver`), replaces `make_driver`. Resolves OQ-G1, OQ-G3.
- adr-13.md — `DEPENDENCY_MISSING` error code. Resolves OQ-G4.
- adr-14.md — USR → UUID5 mapping with pinned namespace.
- adr-15.md — Property JSON-encoding for IndraDB. Resolves OQ-G2.

All four ADRs at `Status: accepted`.

## Compatibility constraints — verified in design.md §10
C-G1..C-G8 all satisfied by the design.

## OQ resolution map
| OQ | Resolution | Location |
|----|------------|----------|
| OQ-G1 | sync only for v3 | adr-12 |
| OQ-G2 | JSON-encode non-scalar props; debug log | adr-15 |
| OQ-G3 | lazy import inside each driver's connect() | adr-12 |
| OQ-G4 | DependencyMissingError = setup-error class | adr-13 |
| OQ-G5 | out of scope (daemon health-check) | design.md §9 |

## Open issues for downstream stages
- senior-developer must add tests for: scheme dispatch table, ImportError → DependencyMissingError on both drivers, USR→UUID determinism, prop JSON-encoding round-trip, idempotency via fake IndraDB store.
- `make_driver` removal: senior-developer to grep external callers (no in-repo callers confirmed).
- IndraDB live BDD test fixture (`tests/fixtures/indradb-compose.yml`) — schema TBD by senior-developer; out of v3 CI scope.

## Deliverables (absolute paths)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/design.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/adr-12.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/adr-13.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/adr-14.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/adr-15.md`
