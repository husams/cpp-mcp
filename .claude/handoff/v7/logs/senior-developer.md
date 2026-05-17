# senior-developer log — cpp-mcp v7 S1

date: 2026-05-17
deliver: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/plan.md

## Decisions
- Decomposed S1 into 6 sequential stories (P1..P6); 0 parallel-safe (all touch shared exporter or depend on prior step).
- Foundation-first ordering: constants/version (P1) → classifier (P2) → MEMBER_OF.access (P3) → node properties (P4) → backward-compat + round-trip tests (P5) → live IndraDB (P6).
- Real source path is `src/cpp_mcp/graphdb/` (NOT `graphdb_export/` as CHARTER states — confirmed via design §1 and ADR-25).
- Every story carries explicit AC IDs and exit-criteria commands (ruff format/check + pytest unit + pytest integration where applicable) per CHARTER I3.
- pyproject version bump intentionally NOT planned (reserved for end of S6 per CHARTER NC-3).
- PARM_DECL keeps `Variable` emission per ADR-25 D2; tests must scope assertions by USR, not global "no Variable".

## Risks surfaced for developer
- libclang capability probes (`is_static_member`, `is_constexpr`, thread_local, union access) — fallbacks in design; results must land in implementation-notes.md (ADR-25 F-3, F-4).
- P3+P4 touch adjacent regions of exporter.py — sequential implementation avoids conflict.
- P6 needs running IndraDB daemon; pre-clean test DB to avoid v1→v2 skew note noise.

## Open items
- None blocking. ADR-25 status = accepted (I2 satisfied).
