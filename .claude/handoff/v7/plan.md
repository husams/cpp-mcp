# Plan — cpp-mcp v7 Stage S1

run_id: cpp-mcp-v7-s1
stage: S1 of 6
produced_by: senior-developer
charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
requirements: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md
design: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/design.md
adrs: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md
scenarios: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/scenarios.md
schema target: 0.4.0 (NO pyproject.toml bump in S1 — reserved for end of S6 per CHARTER NC-3)
toolchain: uv + ruff + pytest (python-conventions)

---

## Conventions (apply to every story)

- All edits live under `src/cpp_mcp/graphdb/` (real path — the CHARTER's `graphdb_export/` is a typo; design §1 confirms).
- Run from project root `/Users/husam/workspace/cpp-mcp`.
- Do NOT bump `pyproject.toml` `version`. Do NOT commit until S1-6 and the qa-engineer gates pass.
- Commit message (when reached, end of S1, NC-4): `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`.
- Every story's exit-criteria MUST pass before moving to the next (CHARTER invariant I3).

---

## Story P1: Schema constants + schema_version bump (foundation)

Goal: introduce `NODE_FIELD`, `NODE_GLOBAL_VARIABLE` constants and bump `SCHEMA_VERSION` to `"v2"` so all downstream code can import the new symbols. Pure additive constant work; no classifier change yet.

Satisfies AC: S1-1 AC1 (constant existence — partial), S1-4 AC1 (SCHEMA_VERSION value).
Design ref: §2 (schema diff), §7 (schema_version bump), ADR-25 D8.
Parallel-safe: false (every downstream story imports these constants).

Files to change:
  - `src/cpp_mcp/graphdb/schema.py` — add `NODE_FIELD = "Field"`, `NODE_GLOBAL_VARIABLE = "GlobalVariable"`; extend `ALL_NODE_TYPES`; retain `NODE_VARIABLE` (ADR-25 D1).
  - `src/cpp_mcp/graphdb/schema_version.py` — `SCHEMA_VERSION = "v2"` (was `"v1"`).

New files: none.

Tests:
  - `tests/unit/graphdb/test_schema_version_stamp.py` — update existing assertion from `"v1"` → `"v2"`; add assertion that both new node-type constants exist and appear in `ALL_NODE_TYPES`. (covers S1-4 AC1)
  - `tests/unit/graphdb/test_schema_constants.py` (new, ~25 lines) — assert `NODE_FIELD == "Field"`, `NODE_GLOBAL_VARIABLE == "GlobalVariable"`, both in `ALL_NODE_TYPES`, `NODE_VARIABLE` still exported.

Risks: any other existing test asserting `SCHEMA_VERSION == "v1"` will break — grep before edit.

Exit criteria (all MUST pass):
```
cd /Users/husam/workspace/cpp-mcp && grep -rn '"v1"' src/ tests/ | grep -v __pycache__   # audit residual hardcodes
cd /Users/husam/workspace/cpp-mcp && uv run ruff format src/cpp_mcp/graphdb/schema.py src/cpp_mcp/graphdb/schema_version.py tests/unit/graphdb/test_schema_version_stamp.py tests/unit/graphdb/test_schema_constants.py
cd /Users/husam/workspace/cpp-mcp && uv run ruff check src/cpp_mcp/graphdb/ tests/unit/graphdb/
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit/graphdb/test_schema_version_stamp.py tests/unit/graphdb/test_schema_constants.py -x -q
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit -x -q   # zero regressions vs. 880 baseline
```

---

## Story P2: Classifier — FIELD_DECL / VAR_DECL split + static-member invariant

Goal: implement `_classify_node`, `_classify_field`, `_is_static_member` per design §3. VAR_DECL → `GlobalVariable`; FIELD_DECL → `Field` unless `is_static_member()` then `GlobalVariable` (ADR-25 D7); PARM_DECL stays `Variable` (ADR-25 D2).

Satisfies AC: S1-1 AC1, AC2, AC3, AC5 (live deferred to P6).
Design ref: §3, ADR-25 D1, D2, D7.
Parallel-safe: false (depends on P1; P3 and P4 layer on top of this branching).

Files to change:
  - `src/cpp_mcp/graphdb/exporter.py` — replace `_KIND_TO_NODE_TYPE["FIELD_DECL"]`/`"VAR_DECL"` entries with the partial table in design §3; add `_classify_node`, `_classify_field`, `_is_static_member` helpers; call `_classify_node(cursor)` where `_KIND_TO_NODE_TYPE.get(kind)` is currently called in `_walk_cursor`.

New files: none.

Tests (new under `tests/unit/graphdb/`):
  - `test_field_classification.py` — fixture C++ sources via libclang TU in-memory; assert:
    - non-static `int x` in class → one `Field` node, no `Variable` for that USR (S1-1 AC1, SC1).
    - `static int count` in class → `GlobalVariable`, no `Field` for that USR (S1-1 AC3, SC3, D7).
    - anonymous-struct member → `Field` (D3 — note in test docstring; minimal coverage).
  - `test_global_variable_classification.py` — namespace-scope `int counter`, file-scope `static int file_count`, `extern int shared_val` → all `GlobalVariable` (S1-1 AC2, SC2/SC2b/SC2c).
  - Negative assertion (D2): test must NOT assert "no Variable nodes globally"; instead assert "no Variable node for THIS usr" (PARM_DECL still emits `Variable`).

Risks: `cursor.is_static_member()` may be absent on pinned libclang; helper has storage-class fallback per design §3. Developer records actual libclang behavior in `implementation-notes.md` (ADR-25 F-3).

Exit criteria:
```
cd /Users/husam/workspace/cpp-mcp && uv run ruff format src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/test_field_classification.py tests/unit/graphdb/test_global_variable_classification.py
cd /Users/husam/workspace/cpp-mcp && uv run ruff check src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit/graphdb/test_field_classification.py tests/unit/graphdb/test_global_variable_classification.py -x -q
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit -x -q   # baseline holds; pre-existing 880 still pass
```

---

## Story P3: MEMBER_OF.access property

Goal: emit `access` (`public` | `protected` | `private`) on every `MEMBER_OF` edge for fields, methods, ctors, dtors (ADR-25 D5). Apply struct→public / class→private / union→public defaults when libclang returns INVALID (design §4.4, ADR-25 D4).

Satisfies AC: S1-2 AC1, AC2, AC3, AC5 (read tolerance covered by P5; live deferred to P6).
Design ref: §4.4, §5, ADR-25 D4, D5.
Parallel-safe: with P2 — false (both touch `exporter.py` in adjacent blocks).

Files to change:
  - `src/cpp_mcp/graphdb/exporter.py` — add `_resolve_access(cursor, parent_kind) -> str`; patch the MEMBER_OF construction block per design §5 to pass `props={"access": access}`.

New files: none.

Tests (new under `tests/unit/graphdb/`):
  - `test_member_of_access.py`:
    - Scenario Outline over `public`/`protected`/`private` explicit specifiers (S1-2 AC1, SC1).
    - struct member, no specifier → `public` (S1-2 AC2, SC2).
    - class member, no specifier → `private` (S1-2 AC3, SC3).
    - union member, no specifier → `public` (ADR-25 D4, S1-2 EC1).
    - method MEMBER_OF carries `access` (ADR-25 D5, S1-2 EC2).
    - Negative bound: every emitted MEMBER_OF.access value ∈ {public, protected, private} (S1-2 EC3).

Risks: libclang may return `CX_CXXInvalidAccessSpecifier` for union members. The parent-kind default handles this; developer must verify against pinned libclang and document in `implementation-notes.md` (ADR-25 F-4).

Exit criteria:
```
cd /Users/husam/workspace/cpp-mcp && uv run ruff format src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/test_member_of_access.py
cd /Users/husam/workspace/cpp-mcp && uv run ruff check src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/test_member_of_access.py
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit/graphdb/test_member_of_access.py -x -q
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit -x -q
```

---

## Story P4: Field / GlobalVariable node properties (is_static, is_const, is_constexpr, storage_class)

Goal: populate the four new node properties per design §4.1–4.3 and §6. Field nodes get `storage_class: "none"` (ADR-25 D6); `extern thread_local` resolves to `"thread_local"` (design §4.3 EC1).

Satisfies AC: S1-3 AC1–AC7 (AC8 read tolerance via P5; AC9 per-property test coverage covered here).
Design ref: §4.1, §4.2, §4.3, §6, ADR-25 D6.
Parallel-safe: with P3 — false (same `exporter.py` block).

Files to change:
  - `src/cpp_mcp/graphdb/exporter.py` — add `_var_qualifiers(cursor)`, `_is_storage_static(cursor)`, `_storage_class_value(cursor, node_type)`; insert the property-branch block per design §6 inside the `if node_type and usr:` section.

New files: none.

Tests (new under `tests/unit/graphdb/`):
  - `test_variable_properties.py` — Scenario-outline-style table:
    - `const int MAX = 100` → `is_const=true` (S1-3 AC1, SC1).
    - `constexpr int LIMIT = 42` → `is_constexpr=true` AND `is_const=true` (S1-3 AC2, SC2).
    - `static int file_var = 0` (ns scope) → `is_static=true`, `storage_class="static"` (S1-3 AC3, SC3).
    - `extern int shared_val` → `storage_class="extern"` (S1-3 AC4, SC4).
    - `thread_local int tls = 0` → `storage_class="thread_local"` (S1-3 AC5, SC5).
    - non-static class member `int value` → `is_static=false` (S1-3 AC6, SC6).
    - plain `int plain_var = 0` → `storage_class="none"` (S1-3 AC7, SC7).
    - `int mutable_var = 0` → `is_const=false`, `is_constexpr=false` (S1-3 EC4).
    - non-static `Field`.storage_class == `"none"` (ADR-25 D6, S1-3 EC2).
    - `extern thread_local int ext_tls` → `storage_class="thread_local"` (S1-3 EC1).

Risks: `cursor.is_constexpr()` may not exist on pinned libclang — fall back to token scan (design §4.1). libclang has no THREAD_LOCAL storage_class enum value — use `is_thread_local` attr or token scan (design §4.3). Both fallbacks documented in `implementation-notes.md`.

Exit criteria:
```
cd /Users/husam/workspace/cpp-mcp && uv run ruff format src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/test_variable_properties.py
cd /Users/husam/workspace/cpp-mcp && uv run ruff check src/cpp_mcp/graphdb/exporter.py tests/unit/graphdb/test_variable_properties.py
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit/graphdb/test_variable_properties.py -x -q
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit -x -q
```

---

## Story P5: v1 backward-compatibility tests + round-trip

Goal: prove that the read path (`query_graphdb`, `describe_graph_schema`) tolerates legacy v1 graphs (schema_version `"v1"`, nodes typed `Variable`, no `access`, no new properties). No production code changes expected — design §8 confirms introspector is generic; tests are the evidence.

Satisfies AC: S1-1 AC4, S1-2 AC5, S1-3 AC8, S1-4 AC2–AC6, S1-5 AC1, AC6.
Design ref: §8, §9 (test plan), ADR-25 D1 (read path).
Parallel-safe: with P4 — true (tests only, separate files, no exporter edit).

Files to change: none expected. If a test surfaces a read-path failure, escalate as a defect; fix in this story.

New files:
  - `tests/unit/graphdb/test_describe_v1_compat.py` — build a fixture v1 graph (in-memory fake driver OR small JSON), call `describe_graph_schema`; assert no raise; assert response includes legacy `Variable` in `node_types` (per ADR-25 D1 — surfaced naturally) and `schema_version == "v1"` is reported through (S1-4 AC5, S1-1 AC4, S1-2 AC5, S1-3 AC8).
  - `tests/unit/graphdb/test_describe_v2_shape.py` — fresh export through fake driver; assert response includes `schema_version == "v2"`, `Field` and `GlobalVariable` in node_types with the four new property_keys, MEMBER_OF in edge_types with `access` in property_keys (S1-4 AC1–AC4, SC1–SC4).
  - `tests/unit/graphdb/test_mcp_tool_signatures.py` — import the three FastMCP tool registrations (`ingest_code`, `query_graphdb`, `describe_graph_schema`); snapshot their input/output JSON schemas; assert unchanged vs. a committed reference snapshot (S1-4 AC6, SC6, NC-1). If no prior snapshot exists, generate one in this story and commit it as fixture.
  - `tests/unit/graphdb/test_round_trip.py` — small C++ source → export to fake driver → re-read via introspector → compare Field/GlobalVariable node sets (S1-5 AC6, SC6).

Tests: see above.

Risks: a hidden assumption in `schema_introspector.py:464-476` skew-detection path may misbehave when `"v1"` is now the *legacy* value — verify the existing skew message text still reads correctly per design §7.

Exit criteria:
```
cd /Users/husam/workspace/cpp-mcp && uv run ruff format tests/unit/graphdb/test_describe_v1_compat.py tests/unit/graphdb/test_describe_v2_shape.py tests/unit/graphdb/test_mcp_tool_signatures.py tests/unit/graphdb/test_round_trip.py
cd /Users/husam/workspace/cpp-mcp && uv run ruff check tests/unit/graphdb/
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit/graphdb/test_describe_v1_compat.py tests/unit/graphdb/test_describe_v2_shape.py tests/unit/graphdb/test_mcp_tool_signatures.py tests/unit/graphdb/test_round_trip.py -x -q
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit -x -q   # full suite: ≥880 + new, 0 fail (S1-5 AC1)
```

---

## Story P6: Live IndraDB integration tests

Goal: extend the v4 live IndraDB harness with two new tests covering the Field/GlobalVariable split and the access-private filter; confirm the 18 pre-existing integration tests still pass (S1-6 AC3).

Satisfies AC: S1-1 AC5 (live), S1-2 AC4 (live), S1-6 AC1, AC2, AC3.
Design ref: §9 (integration tests).
Parallel-safe: false — REQUIRES a running IndraDB daemon and depends on P2/P3/P4/P5 being green; run strictly LAST.

Files to change:
  - `tests/integration/conftest.py` — add fixtures (named C++ source for class-with-members + namespace-var, and another with public/protected/private members) if not already trivially constructible.

New files:
  - `tests/integration/test_v7_s1_field_vs_global_live.py` — ingest fixture; query live IndraDB for vertices of type `Field` and `GlobalVariable`; assert both present and disjoint (S1-1 AC5, S1-6 AC1, SC1).
  - `tests/integration/test_v7_s1_access_filter_live.py` — ingest fixture; query for MEMBER_OF edges with `access == "private"`; assert returned member set == declared private members, excludes public/protected (S1-2 AC4, S1-6 AC2, SC2).

Tests: above.

Risks:
  - Requires `indradb-server` reachable (existing harness pattern). If daemon absent, mark skipped via existing live-test gating, not failed; QA must verify the gating works.
  - schema_version bump to `"v2"` may emit a skew note on top of a pre-existing v1 graph stored in the daemon — pre-clean the test database in fixture setup (existing harness pattern from v4).

Exit criteria:
```
cd /Users/husam/workspace/cpp-mcp && uv run ruff format tests/integration/test_v7_s1_field_vs_global_live.py tests/integration/test_v7_s1_access_filter_live.py tests/integration/conftest.py
cd /Users/husam/workspace/cpp-mcp && uv run ruff check tests/integration/
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/integration/test_v7_s1_field_vs_global_live.py tests/integration/test_v7_s1_access_filter_live.py -x -q
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/integration -q   # full integration suite: ≥18 + 2 new, 0 fail (S1-6 AC3)
cd /Users/husam/workspace/cpp-mcp && uv run pytest tests/unit tests/integration -q   # final full-suite gate before S1 ships
```

---

## Cross-story risks and notes

- The CHARTER references `src/cpp_mcp/graphdb_export/`; the real path is `src/cpp_mcp/graphdb/`. All stories use the real path (ADR-25 "Charter path typo" section).
- PARM_DECL still emits `Variable` after S1 (ADR-25 D2). NO test may assert "no Variable nodes globally"; assertions must be USR-scoped or kind-scoped.
- `pyproject.toml` `version` MUST remain `0.4.0` (NC-3). Plan does not list a version-bump story.
- The exporter changes in P2/P3/P4 all touch adjacent regions of `exporter.py` (lines 286–326 per design §5, §6). Implementing in P2 → P3 → P4 order avoids merge conflict.
- Developer records libclang capability probes (`is_static_member`, `is_constexpr`, thread_local detection, union-access default) in `/Users/husam/workspace/cpp-mcp/.claude/handoff/v7/implementation-notes.md` per ADR-25 F-3, F-4.
- After P6 green, developer (not senior-developer) creates the commit with the exact message: `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`.

---

## Out of scope (do NOT implement in S1)

- S2: `Type`, `Parameter`, `RETURNS`/`OF_TYPE`/`HAS_PARAM`, signature property.
- S3–S5: templates, virtual dispatch, enums, namespace directives, `ALIAS_OF`.
- S6: IndraDB ordered traversal, full describe rewrite.
- Removing `NODE_VARIABLE` from `schema.py` (ADR-25 D1 keeps it).
- Removing PARM_DECL `Variable` emission (ADR-25 D2 keeps it; removed in S2).
- Multi-label / parent-label retention for `Variable` (ADR-25 Alt-A rejected).
- pyproject.toml version bump.

---

## References

- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/scenarios.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/design.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md
- src/cpp_mcp/graphdb/{exporter,schema,schema_version,schema_introspector,neo4j_driver,indradb_driver}.py
- wiki: ~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md
- Cognee tag: `task:cpp-mcp-v7-s1`, `role:senior-developer`
