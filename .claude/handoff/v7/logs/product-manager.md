# product-manager session log — cpp-mcp-v7-s1

date: 2026-05-17
role: product-manager
task-slug: cpp-mcp-v7-s1
deliverable: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md

## Sources read

1. CHARTER.md — confirmed handoff paths, cross-stage invariants (I1–I4), failure codes, S1 scope note.
2. requirements-raw.md — primary input: 7 items (node split, access property, new props, schema_version bump, unit tests, live integration, ADR-25 slot).
3. wiki: pages/planning/cpp-mcp-v7-full-ast-schema.md — broader v7 PRD; used to confirm S2–S6 deferred scope and coverage matrix.
4. advisor call — confirmed story decomposition, open questions to surface, constraints to flag.

## Skills loaded

- advisor (called once before write, once at completion)

## Decisions made

- Decomposed into 7 stories: S1-1 (node split), S1-2 (MEMBER_OF.access), S1-3 (new node props), S1-4 (schema_version), S1-5 (unit tests), S1-6 (live integration), S1-7 (ADR-25).
- S1-7 is a product story that makes the ADR a tracked deliverable with its own AC; the architect owns execution but the requirement is product-stated.
- Did NOT resolve OQ-1 (Variable transition path) — deferred to ADR-25 per role boundary.
- Did NOT resolve OQ-3 (union default access) — deferred to implementation notes.
- Did NOT resolve OQ-5 (storage_class for Field nodes) — deferred to architect/developer.
- All stories have ≥1 Given/When/Then AC; I1 satisfied.

## Problems encountered

- requirements-raw.md §1 was ambiguous on static class data members: should they be Field or GlobalVariable? Resolved by C++ semantics (static members are not instance fields → GlobalVariable). Surfaced as AC in S1-1 rather than open question.
- Default access for unions not specified in raw requirements. Opened as OQ-3.
- storage_class semantics for instance fields ambiguous. Opened as OQ-5.

## Open questions filed

OQ-1: Variable transition path (a vs b) — ADR-25 to resolve.
OQ-2: Anonymous struct/union member classification.
OQ-3: Union member default access in libclang.
OQ-4: Whether access property emits on all MEMBER_OF edges or only Field edges.
OQ-5: storage_class value for non-static class data members.
OQ-6: Invariant enforcement if static member somehow typed Field.
OQ-7: describe_graph_schema listing of Variable label if ADR-25 retains it.

## Status

requirements.md written. No blockers. 7 open questions documented in file.
