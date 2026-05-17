run_id: cpp-mcp-v7-s1
story: P1 — Schema constants + schema_version bump
stage: S1 of 6

---

Files changed:
  - src/cpp_mcp/graphdb/schema.py — added NODE_FIELD = "Field", NODE_GLOBAL_VARIABLE = "GlobalVariable"; extended ALL_NODE_TYPES (7 → 9); retained NODE_VARIABLE (ADR-25 D1).
  - src/cpp_mcp/graphdb/schema_version.py — SCHEMA_VERSION bumped from "v1" to "v2" (ADR-25 D8).
  - tests/unit/graphdb/test_schema_version_stamp.py — updated test_schema_version_constant_value assertion from "v1" → "v2"; imported new constants; added test_new_node_type_constants_exist and test_new_node_types_in_all_node_types.
  - tests/unit/graphdb/test_schema_constants.py (NEW) — 6 assertions: NODE_FIELD value, NODE_GLOBAL_VARIABLE value, both in ALL_NODE_TYPES, NODE_VARIABLE still exported and still in ALL_NODE_TYPES.
  - tests/unit/test_graphdb_additions.py — renamed test_all_node_types_exactly_7 → test_all_node_types_exactly_9; updated assertion from 7 to 9.

Tests added/run:
  - uv run pytest tests/unit/graphdb/test_schema_version_stamp.py tests/unit/graphdb/test_schema_constants.py -x -q → 12 passed
  - uv run pytest tests/unit -x -q → 776 passed, 4 skipped (zero regressions; pre-existing unit count was 780 total)

Deviations from plan:
  - test_graphdb_additions.py::test_all_node_types_exactly_7 was not mentioned in the plan but failed because it hard-coded the old count of 7. Updated it to 9 as part of P1 to restore the baseline. This is a direct consequence of extending ALL_NODE_TYPES and is additive/non-breaking.
  - tests/integration/test_describe_graph_schema_e2e.py still asserts schema_version == "v1" at lines 129 and 277. Per the plan note ("update test fixtures only if they assert SCHEMA_VERSION literal"), these are integration tests handled in P5 (backward-compat + round-trip). Left as-is for P5.

Follow-ups (tag: sr-dev):
  - tests/integration/test_describe_graph_schema_e2e.py:129,277 assert "v1" — will break once integration suite runs against the new schema_version. Deferred to P5 per plan.

References:
  - plan.md (Story P1)
  - adr-25.md (D1, D2, D8)
  - design.md §2, §7
  - scenarios.md

---

story: P2 — Classifier: FIELD_DECL/VAR_DECL split + static-member invariant
stage: S1 of 6

---

Files changed:
  - src/cpp_mcp/graphdb/exporter.py:
    - Added NODE_FIELD, NODE_GLOBAL_VARIABLE to schema imports.
    - Replaced `"VAR_DECL": NODE_VARIABLE` → `"VAR_DECL": NODE_GLOBAL_VARIABLE` in _KIND_TO_NODE_TYPE (ADR-25 D1).
    - Removed `"FIELD_DECL"` entry from _KIND_TO_NODE_TYPE (runtime classification via _classify_field).
    - Retained `"PARM_DECL": NODE_VARIABLE` (ADR-25 D2, transitional).
    - Added `_is_static_member(cursor)`, `_classify_field(cursor)`, `_classify_node(cursor)` helpers per design §3.
    - Replaced `_KIND_TO_NODE_TYPE.get(kind)` call in `_walk_cursor` with `_classify_node(cursor)`.
    - Updated module docstring to reflect new VAR_DECL/FIELD_DECL/PARM_DECL classification.
  - tests/unit/graphdb/test_field_classification.py (NEW) — 9 test cases:
    - Non-static member → Field (USR-scoped, S1-1 AC1, SC1).
    - Non-static member not GlobalVariable (USR-scoped negation).
    - Static member → GlobalVariable (S1-1 AC3, SC3, D7, fallback path).
    - Static member not Field (D7 invariant).
    - Anonymous struct member → Field (D3, minimal coverage).
    - PARM_DECL → Variable (D2 positive assertion).
    - PARM_DECL not Field or GlobalVariable (D2, parametrized, USR-scoped).
  - tests/unit/graphdb/test_global_variable_classification.py (NEW) — 6 test cases:
    - VAR_DECL → GlobalVariable (parametrized: namespace-scope, file-scope static, extern).
    - VAR_DECL not Variable (D1, USR-scoped negation, same 3 cases).
    - Multiple VAR_DECL all GlobalVariable.

Tests added/run:
  - uv run pytest tests/unit/graphdb/test_field_classification.py tests/unit/graphdb/test_global_variable_classification.py -x -q → 15 passed
  - uv run pytest tests/unit -x -q → 791 passed, 4 skipped (zero regressions; +15 vs P1 baseline of 776)

Libclang capability probe (ADR-25 F-3):
  - `Cursor.is_static_member`: NOT available on pinned libclang (hasattr check returned False).
  - `StorageClass.STATIC`: available (verified — StorageClass enum is importable and STATIC is present).
  - Consequence: `_is_static_member()` ALWAYS exercises the StorageClass.STATIC fallback path on this libclang version. The primary `is_static_member()` callable path was not exercised.
  - Test coverage: `test_static_member_produces_global_variable_node` sets `cursor.storage_class = StorageClass.STATIC` on the fake cursor (after explicitly deleting `cursor.is_static_member`). This directly exercises the fallback path. Test passes, confirming the fallback is sufficient.
  - StorageClass enum values available: AUTO, EXTERN, INVALID, NONE, OPENCLWORKGROUPLOCAL, PRIVATEEXTERN, REGISTER, STATIC. No THREAD_LOCAL enum value (relevant for P4 design §4.3).

Deviations from plan:
  - None. Plan prescribed exactly `_classify_node`, `_classify_field`, `_is_static_member`; all three implemented per design §3.

Follow-ups (tag: sr-dev):
  - No THREAD_LOCAL StorageClass enum value available in pinned libclang (confirmed during probe). P4 design §4.3 must use `is_thread_local` attr or token scan fallback — document when implementing P4.

References:
  - plan.md (Story P2)
  - adr-25.md (D1, D2, D7, F-3)
  - design.md §3
  - scenarios.md (S1-1 AC1, AC2, AC3, SC1, SC2, SC3)

---

story: P3 — MEMBER_OF.access property
stage: S1 of 6

---

Files changed:
  - src/cpp_mcp/graphdb/exporter.py:
    - Added `_PUBLIC_DEFAULT_PARENT_KINDS` constant (frozenset: STRUCT_DECL, UNION_DECL).
    - Added `_resolve_access(cursor, parent_kind) -> str` helper per design §4.4 and ADR-25 D4/D5.
    - Patched MEMBER_OF edge construction block (was `props={}`); now passes `props={"access": _resolve_access(cursor, parent_kind)}`.
  - tests/unit/graphdb/test_member_of_access.py (NEW) — 11 test cases across 5 test classes:
    - TestExplicitAccessSpecifiers: parametrized over PUBLIC/PROTECTED/PRIVATE (S1-2 AC1, SC1).
    - TestStructDefaultPublic: struct member implicit → "public" (S1-2 AC2, SC2).
    - TestClassDefaultPrivate: class member implicit → "private" (S1-2 AC3, SC3).
    - TestUnionDefaultAccess: _resolve_access(cursor, "UNION_DECL") with INVALID → "public" (ADR-25 D4, S1-2 EC1).
    - TestMethodMemberOfAccess: CXX_METHOD, CONSTRUCTOR, DESTRUCTOR MEMBER_OF edges carry access (ADR-25 D5, S1-2 EC2).
    - TestNegativeBoundAllAccessValid: all MEMBER_OF.access values in {public, protected, private} (S1-2 EC3).

Tests added/run:
  - uv run pytest tests/unit/graphdb/test_member_of_access.py -x -q → 11 passed
  - uv run pytest tests/unit -x -q → 802 passed, 4 skipped (zero regressions; +11 vs P2 baseline of 791)

Libclang capability probe — union member access (ADR-25 F-4):
  - AccessSpecifier enum is fully available on pinned libclang: PUBLIC, PROTECTED, PRIVATE, INVALID, NONE all confirmed present.
  - The live libclang.dylib is not loadable on this host (macOS, no shared lib path configured), so direct TU parse was not possible. However, enum values are importable and the mock-based test exercises the exact code path `_resolve_access` takes at runtime.
  - The `_resolve_access` function reads `cursor.access_specifier` and compares against AccessSpecifier enum values. For `INVALID` or `NONE` it falls through to parent-kind default.
  - For UNION_DECL parent: `_resolve_access(cursor_with_INVALID, "UNION_DECL")` → "public". This is the expected behavior per ISO C++ (union members are implicitly public) and ADR-25 D4.
  - UNION_DECL is not in `_MEMBER_PARENT_KINDS` and union members do not emit MEMBER_OF edges in S1 (S1 scope per design §4.4: "not required for S1 — flag as a follow-up"). The union default is therefore exercised via direct unit test of `_resolve_access`.

Deviations from plan:
  - Dispatch note says "ALL MEMBER_OF edges (fields, methods, ctors, dtors, nested types)". Design §4.4 and plan.md Story P3 are explicit that nested types are a non-goal for S1. Followed design.md (authoritative). Filed as follow-up below.
  - Union members do not emit MEMBER_OF edges in S1 (UNION_DECL absent from _MEMBER_PARENT_KINDS). Union default access tested via `_resolve_access` directly per advisor guidance, not end-to-end.

Follow-ups (tag: sr-dev):
  - Nested types in MEMBER_OF: design §4.4 defers CLASS_DECL/STRUCT_DECL/TYPEDEF_DECL children of classes to a later stage. Not implemented in S1.
  - Union MEMBER_OF edges: UNION_DECL is not in _MEMBER_PARENT_KINDS and union members don't emit MEMBER_OF. If union membership tracking is needed, add UNION_DECL to _MEMBER_PARENT_KINDS as a follow-up.

References:
  - plan.md (Story P3)
  - adr-25.md (D4, D5, F-4)
  - design.md §4.4, §5
  - scenarios.md (S1-2 AC1, AC2, AC3, EC1, EC2, EC3, SC1, SC2, SC3)

---

story: P4 — Field / GlobalVariable node properties (is_static, is_const, is_constexpr, storage_class)
stage: S1 of 6

---

Files changed:
  - src/cpp_mcp/graphdb/exporter.py:
    - Added `_var_qualifiers(cursor) -> tuple[bool, bool]` — returns (is_const, is_constexpr);
      primary via cursor.is_constexpr() (absent on pinned libclang); token-scan fallback
      looks for "constexpr" in cursor.get_tokens(); constexpr forces is_const=True (SC2, design §4.1).
    - Added `_is_storage_static(cursor) -> bool` — returns True when cursor.storage_class == StorageClass.STATIC;
      used for the second clause of is_static on GlobalVariable from VAR_DECL (design §4.2, §6).
    - Added `_storage_class_value(cursor, node_type) -> str` — priority: (1) NODE_FIELD → "none" (D6);
      (2) thread_local detection via is_thread_local attr or token scan (fires before enum check to
      satisfy EC1 for extern thread_local); (3) StorageClass enum → "static"/"extern"/"auto"/"register"/"none".
    - Patched the `if node_type and usr:` block in `_walk_cursor` — replaced inline `props={}` dict
      literal with a named `props` variable; added property-branch for NODE_FIELD/NODE_GLOBAL_VARIABLE
      that populates is_const, is_constexpr, is_static, storage_class (design §6, ADR-25 D6).
  - tests/unit/graphdb/test_variable_properties.py (NEW) — 18 test cases covering all 10 plan rows:
    - TestConstVar: const int MAX → is_const=True (S1-3 AC1, SC1).
    - TestConstexprVar: constexpr int LIMIT → is_constexpr=True and is_const=True (S1-3 AC2, SC2).
    - TestStaticVar: static int file_var → is_static=True, storage_class="static" (S1-3 AC3, SC3).
    - TestExternVar: extern int shared_val → storage_class="extern" (S1-3 AC4, SC4).
    - TestThreadLocalVar: thread_local int tls → storage_class="thread_local" via token scan (S1-3 AC5, SC5).
    - TestNonStaticFieldIsStatic: non-static class member → is_static=False (S1-3 AC6, SC6).
    - TestPlainVar: plain int plain_var → storage_class="none" (S1-3 AC7, SC7).
    - TestMutableVar: int mutable_var → is_const=False, is_constexpr=False (S1-3 EC4).
    - TestFieldStorageClassNone: non-static Field.storage_class == "none" (ADR-25 D6, S1-3 EC2).
    - TestExternThreadLocal: extern thread_local int ext_tls → storage_class="thread_local" (S1-3 EC1).
    - TestPropertyPresence: parametrized — all four properties present on both GlobalVariable and Field nodes.

Tests added/run:
  - uv run pytest tests/unit/graphdb/test_variable_properties.py -x -q → 18 passed
  - uv run pytest tests/unit -x -q → 820 passed, 4 skipped (zero regressions; +18 vs P3 baseline of 802)

Libclang capability probe — P4 (ADR-25 F-3):
  - `cursor.is_constexpr`: NOT available on pinned libclang. Token-scan fallback ("constexpr" in
    cursor.get_tokens()) is exercised for all constexpr tests; verified via MagicMock with
    `del cursor.is_constexpr` pattern matching the P2 `del cursor.is_static_member` approach.
  - `cursor.is_thread_local`: NOT available on pinned libclang. Token-scan fallback ("thread_local"
    in cursor.get_tokens()) is exercised. Verified via MagicMock with `del cursor.is_thread_local`.
  - No THREAD_LOCAL enum value in StorageClass (confirmed in P2 probe, reconfirmed for P4).
  - Consequence: `_storage_class_value` always takes the token-scan path for thread_local on this
    libclang version. The `is_thread_local` callable path exists but is unreachable with pinned libclang.
  - EC1 (extern thread_local priority): token scan fires before StorageClass enum check; test with
    StorageClass.EXTERN + ["extern","thread_local"] tokens confirmed "thread_local" wins (EC1).

Deviations from plan:
  - None. All three helpers implemented exactly per design §4.1-4.3, §6 and ADR-25 D6.
    Property block inserted in `_walk_cursor` per design §6 pattern verbatim.

Follow-ups (tag: sr-dev):
  - None specific to P4. Thread_local and is_constexpr callable paths remain dead code on pinned
    libclang but are kept for forward-compatibility when the libclang binding is upgraded.

References:
  - plan.md (Story P4)
  - adr-25.md (D6, F-3)
  - design.md §4.1, §4.2, §4.3, §6
  - scenarios.md (S1-3 AC1-AC7, EC1, EC2, EC4, SC1-SC7)

---

story: P5 — v1 backward-compatibility tests + describe_v2 shape + round-trip + tool-signature snapshot
stage: S1 of 6

---

Files changed:
  - tests/unit/graphdb/test_describe_v1_compat.py (NEW, 5 tests) — fixture v1 graph with schema_version="v1", Variable nodes, MEMBER_OF edges without 'access'. Asserts no raise, Variable in node_types, MEMBER_OF with empty property_keys, skew note present mentioning "v1", required keys present. Covers S1-1 AC4, S1-2 AC5, S1-3 AC8, S1-4 AC5.
  - tests/unit/graphdb/test_describe_v2_shape.py (NEW, 8 tests) — fresh v2 graph fixture (Field, GlobalVariable, MEMBER_OF.access, File with schema_version="v2"). Asserts schema_version=="v2", Field/GlobalVariable in node_types, four new property keys each, MEMBER_OF with "access" in property_keys, no spurious skew note. Covers S1-4 AC1-AC4, SC1-SC4.
  - tests/unit/graphdb/test_mcp_tool_signatures.py (NEW, 5 tests, 3 parametrized) — snapshot test: loads committed fixture under tests/unit/graphdb/fixtures/tool_signatures.json; asserts live to_mcp_tool().inputSchema matches snapshot for ingest_code, query_graphdb, describe_graph_schema. Covers S1-4 AC6, SC6, NC-1.
  - tests/unit/graphdb/test_round_trip.py (NEW, 6 tests) — builds NodeRecord/EdgeRecord lists (S1 v2 export shape) → converts to _FakeIndraDBClient state → introspects via IndraDbSchemaIntrospector. Asserts Field and GlobalVariable node types present and disjoint, MEMBER_OF edge carries "access", schema_version=="v2", Field exposes four new property keys. Covers S1-5 AC6, SC6.
  - tests/unit/graphdb/fixtures/tool_signatures.json (NEW) — committed snapshot fixture for the three graph tool input schemas.
  - tests/integration/test_describe_graph_schema_e2e.py (UPDATED) — updated lines 129 and 277 from asserting schema_version=="v1" → "v2" (P5 follow-up from P1; these are integration tests that won't run in the unit gate).

Tests added/run:
  - uv run pytest tests/unit/graphdb/test_describe_v1_compat.py tests/unit/graphdb/test_describe_v2_shape.py tests/unit/graphdb/test_mcp_tool_signatures.py tests/unit/graphdb/test_round_trip.py -x -q → 27 passed
  - uv run pytest tests/unit -x -q → 847 passed, 4 skipped (baseline was 820; +27 new)

Deviations from plan:
  - Round-trip test uses NodeRecord/EdgeRecord construction rather than a real libclang TU parse. libclang.dylib is not loadable on this macOS host (confirmed in P2 implementation notes — no shared lib path configured). The test still covers the full data-path contract: exporter output format → driver shape → introspector describe. Noted in log.
  - test_describe_v1_compat.py: schema_version in the describe response is the code constant (SCHEMA_VERSION="v2"), not the stored "v1" value. The v1 stored value surfaces as a skew note. Test updated to assert skew note presence (mentioning "v1") rather than asserting response schema_version=="v1" — consistent with design §8 and how the introspector works.
  - pytest import removed from test_describe_v1_compat, test_describe_v2_shape, and test_round_trip (ruff F401; files didn't use parametrize or explicit pytest symbols).
  - Integration test docstring at line 272 also updated to reference "v2" for consistency.

Follow-ups (tag: sr-dev):
  - P6 integration tests will require a live IndraDB daemon. The pinned counts in test_describe_graph_schema_e2e.py (_EXPECTED_NODE_COUNTS: Variable:33) will need update once a live ingest with v2 exporter runs and Variable nodes become Field/GlobalVariable split. This is P6 scope.
  - Integration tests are marked @pytest.mark.integration and only run via pytest tests/integration; the unit gate (tests/unit) is what blocks P5.

References:
  - plan.md (Story P5)
  - adr-25.md (D1, D5, D8, F-2)
  - design.md §8, §9
  - scenarios.md (S1-1 AC4, S1-2 AC5, S1-3 AC8, S1-4 AC1-AC6, S1-5 AC6, SC1-SC6, NC-1)

---

story: P6 — Live IndraDB integration tests (Field/GlobalVariable split + access filter)
stage: S1 of 6

---

Files changed:
  - test-repo/v7s1/members.cc (NEW) — C++ fixture: Widget class with public/protected/private
    data members + Point struct + namespace-scope global_counter/MAX_SIZE. No functions to avoid
    PARM_DECL Variable nodes that would complicate assertions.
  - test-repo/v7s1/compile_commands.json (NEW) — minimal compile_commands.json for the fixture
    so resolve_flags uses explicit -std=c++17 flags (falls back to default_flags gracefully if
    the file is not found in the DB — verified from compile_db.py).
  - tests/integration/test_v7_s1_field_vs_global_live.py (NEW) — 4 integration tests:
    - test_field_nodes_present_after_ingest: Field vertices present (S1-1 AC5, S1-6 AC1).
    - test_global_variable_nodes_present_after_ingest: GlobalVariable vertices present (S1-1 AC5, S1-6 AC1).
    - test_field_and_global_variable_vertex_sets_are_disjoint: no ID overlap (S1-6 SC1).
    - test_no_variable_nodes_for_class_members_or_namespace_vars: Variable count == 0
      (members.cc has no PARM_DECL, so no Variable nodes expected).
  - tests/integration/test_v7_s1_access_filter_live.py (NEW) — 3 integration tests:
    - test_member_of_edges_carry_access_property: every MEMBER_OF.access ∈ {public,protected,private} (S1-2 AC4).
    - test_edge_with_property_equal_private_returns_only_private_members: filter by access==private
      returns only Widget::secret_value and Widget::another_secret, excludes public/protected (S1-6 AC2, SC2).
    - test_public_member_access_edges_present_and_correct: public members carry access=="public" (S1-2 AC4).
  - tests/integration/conftest.py — unchanged (existing fresh_indradb fixture suffices).

Bug fixed post-initial-write:
  - test_v7_s1_access_filter_live.py line 156: `e["inbound_id"]` → `e["outbound_id"]`.
    MEMBER_OF edges go member→class (source_usr=member→outbound_id, target_usr=class→inbound_id).
    The original code extracted the CLASS vertex IDs, causing all field_id_to_spelling lookups to
    miss, so private_member_spellings would be empty and the assertion would fail against a live daemon.
    Comment on line 155 updated to reflect correct direction: "outbound (member) side".

Tests added/run:
  - uv run ruff format tests/integration/test_v7_s1_field_vs_global_live.py tests/integration/test_v7_s1_access_filter_live.py tests/integration/conftest.py → 2 reformatted, 1 unchanged
  - uv run ruff check tests/integration/ → All checks passed
  - uv run ruff format tests/integration/test_v7_s1_access_filter_live.py (post-fix) → 1 file left unchanged
  - uv run ruff check tests/integration/ (post-fix) → All checks passed
  - uv run pytest tests/integration/test_v7_s1_field_vs_global_live.py tests/integration/test_v7_s1_access_filter_live.py -m integration -q → 7 skipped (daemon absent; skip confirmed via INDRADB_TEST_URI fixture gate)
  - uv run pytest tests/integration -q → 20 passed, 19 skipped (all indradb tests skip without daemon)
  - uv run pytest tests/unit tests/integration -q → 847 passed, 4 skipped, 39 deselected (integration marker excluded by addopts), 0 failures
  - uv run pytest tests/unit tests/integration -q (post-fix) → 847 passed, 4 skipped, 39 deselected, 0 failures

Gate note: plan exit criterion 3 (`pytest tests/integration/test_v7_s1_field_vs_global_live.py ... -x -q`)
  returns exit code 5 (no tests ran) because pyproject.toml addopts="-m 'not integration'" deselects all
  @integration-marked tests when run without explicit -m integration. Running with -m integration gives
  exit 0 (7 skipped). This is the same gating pattern used by all pre-existing IndraDB tests in this repo.

Deviations from plan:
  - conftest.py not modified. plan.md says "add fixtures ... if not already trivially constructible" —
    the existing fresh_indradb fixture covers both new tests completely. No new fixture added.
  - Plan suggested using existing fmt source files (os.cc/fmt-c.cc). Those files don't have simple
    public/protected/private class declarations with known member names. Created test-repo/v7s1/members.cc
    as a dedicated, controlled fixture. This is the cleanest approach (design §9 "fixture with class-with-members").
  - Fixture uses no functions (methods removed) to avoid PARM_DECL Variable nodes from method parameters,
    which would invalidate the "no Variable nodes" assertion for the variable-count test.
  - edge_with_property_equal verb: v6 bugs (3 bugs) were all fixed via client-side fallback in
    indradb_query_executor.py (confirmed by reading the executor — no xfail needed). Tests run as normal
    (not xfail).

Follow-ups (tag: sr-dev):
  - test_describe_graph_schema_e2e.py _EXPECTED_NODE_COUNTS maps Variable:33 from old v1 schema. When
    live integration tests run against a real IndraDB daemon with v2 exporter, the Variable count will
    drop (field/var split). Those pinned counts need updating in a follow-up live run. Filed as P5
    follow-up; confirmed as still open after P6.
  - The fixture compile_commands.json hard-codes /Users/husam/workspace/cpp-mcp as the project root.
    If the repo is checked out at a different path, resolve_flags will fall back to default flags (graceful
    per compile_db.py) rather than using the explicit -std=c++17 flags. This is acceptable for the live test
    but documented for CI portability.

References:
  - plan.md (Story P6)
  - adr-25.md (D1, D2, D4, D5)
  - design.md §9 (integration tests)
  - scenarios.md (S1-1 AC5, S1-2 AC4, S1-6 AC1, AC2, AC3, SC1, SC2)
  - src/cpp_mcp/core/compile_db.py (resolve_flags fallback behavior)
  - src/cpp_mcp/graphdb/indradb_query_executor.py (edge_with_property_equal client-side fix)
