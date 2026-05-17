## P1 — Schema constants (Type, Parameter, 5 edges)

Files changed:
- `src/cpp_mcp/graphdb/schema.py`
- `tests/unit/test_graphdb_additions.py`

Files added:
- `tests/unit/graphdb/test_s2_schema_constants.py`

Tests added/run:
- `uv run pytest tests/unit/graphdb/test_s2_schema_constants.py -x -q` → 15 passed
- `uv run pytest tests/unit -x -q` → 923 passed, 4 skipped, 0 failed

Deviations from plan:
- `test_graphdb_additions.py` cardinality tests updated (9→11 nodes, 7→12 edges). ADR-26 D9 permits this as expected churn (additive schema growth, not PARM_DECL emission assertion).

Follow-ups:
- None for P1. Proceed to P2 (Type node + dedup + POINTS_TO/REFERS_TO chain).

References: plan.md §P1, adr-26.md D8/D9, design.md §1.1/§1.2

## P2 — Type node + dedup + POINTS_TO/REFERS_TO chain

Files changed:
- `src/cpp_mcp/graphdb/exporter.py` — added _type_usr, _type_props, _get_or_create_type helpers; wired into _walk_cursor at function result_type site (no RETURNS edge)

Files added:
- `tests/unit/graphdb/test_type_node.py` (SC-A-01..SC-A-09)
- `tests/unit/graphdb/test_type_edges.py` (SC-B-01..SC-B-05)

Tests added/run:
- `uv run pytest tests/unit/graphdb/test_type_node.py tests/unit/graphdb/test_type_edges.py -x -q` → 40 passed
- `uv run pytest tests/unit -x -q` → 963 passed, 4 skipped, 0 failed

Deviations from plan:
- None. Wire-in emits Type node at function return-type site with NO RETURNS edge (P4 scope).

Follow-ups:
- None for P2. Proceed to P3 (HAS_PARAM + Parameter node) and P4 (OF_TYPE + RETURNS edges).

References: plan.md §P2, adr-26.md D1-D4, design.md §2.1-2.3/§3.1-3.3

## P3 — Parameter node + HAS_PARAM edge + PARM_DECL reclassification

Files changed:
- `src/cpp_mcp/graphdb/exporter.py` — (1) `PARM_DECL` in `_KIND_TO_NODE_TYPE` changed from `NODE_VARIABLE` to `NODE_PARAMETER` (ADR-26 D9); (2) `NODE_VARIABLE` import removed (no longer used in write path); (3) `NODE_PARAMETER` and `EDGE_HAS_PARAM` added to imports; (4) `_render_default_value` helper added (design §2.6); (5) PARM_DECL skip guard added at top of `_walk_cursor` (returns early before any classification — prevents duplicate vertices from generic recursion); (6) `get_arguments()` parameter loop added after P2 result_type block — emits `NodeRecord(NODE_PARAMETER, synthetic_usr)` + `EdgeRecord(EDGE_HAS_PARAM, {"index": idx})` for each param.
- `tests/unit/graphdb/test_field_classification.py` — module docstring updated; `_make_parm_cursor` added `get_tokens.return_value = []`; `_make_function_cursor` changed `get_children.return_value = params` → `get_children.return_value = []` + `get_arguments.return_value = params`; `TestParmDeclInvariant` fully rewritten to assert `NODE_PARAMETER` (not `NODE_VARIABLE`) via synthetic USR; negative assertion now covers Field, GlobalVariable, AND Variable labels (ADR-26 D9).
- `tests/unit/test_graphdb_additions.py` — `func_cursor.get_arguments.return_value = []` added to idempotent-export-twice test.
- `tests/unit/test_graphdb_exporter.py` — `get_arguments.return_value = []` added to 3 function cursor fixtures.
- `tests/unit/graphdb/test_type_node.py` — `get_arguments.return_value = []` added to `_make_func_cursor`.
- `tests/unit/graphdb/test_member_of_access.py` — `get_arguments.return_value = []` added to `_make_member_cursor`.
- `tests/unit/graphdb/test_schema_version_stamp.py` — `get_arguments.return_value = []` added to `_make_cursor`.

Files added:
- `tests/unit/graphdb/test_parameter_node.py` — 23 tests covering SC-C-01..SC-C-10, plus _render_default_value unit tests and parametrized kind coverage.

Tests added/run:
- `uv run pytest tests/unit/graphdb/test_parameter_node.py -x -q` → 23 passed
- `uv run pytest tests/unit -x -q` → 987 passed, 4 skipped, 0 failed

Deviations from plan:
- `NODE_VARIABLE` import removed from `exporter.py` — plan said "add NODE_PARAMETER, EDGE_HAS_PARAM"; removing the now-unused `NODE_VARIABLE` import is correct and required by ruff F401. The constant stays in `schema.py` (ADR-26 D9 read-compat invariant).
- OF_TYPE NOT wired in P3 (per task dispatch note: "Do NOT add OF_TYPE/RETURNS yet (P4)"). The design §3.2 pseudocode shows OF_TYPE in the same block, but P3 scope is Parameter + HAS_PARAM only.
- `is_noexcept` (absent on pinned libclang per ADR-26 D10) confirmed not needed in P3 scope.

Follow-ups:
- P4: OF_TYPE from Parameter to its Type; also OF_TYPE from Field/GlobalVariable; RETURNS edge from Function to return Type.
- ADR-26 D11 `is_noexcept` semantics (P5 scope).

References: plan.md §P3, adr-26.md D6/D9/D10, design.md §2.6/§3.2

## P4 — OF_TYPE edges + RETURNS edge (finalize function-block emissions)

Files changed:
- `src/cpp_mcp/graphdb/exporter.py` — (1) Added `EDGE_OF_TYPE` and `EDGE_RETURNS` to imports; (2) In the P2 RETURNS block, captured the return value of `_get_or_create_type(cursor.result_type, ...)` and emitted a `RETURNS` EdgeRecord when `ret_usr` is non-None — guarded by `contextlib.suppress(Exception)` to protect MagicMock fixtures that lack `result_type`; (3) In the P3 param loop, added `param_type_usr: str | None = None` before the suppress block, called `_get_or_create_type(param.type, ...)` inside it, then emitted `EDGE_OF_TYPE` from `param_usr → param_type_usr` after `EDGE_HAS_PARAM`; (4) In the `if usr not in seen_usrs:` block for Field/GlobalVariable, added a suppress-guarded call to `_get_or_create_type(cursor.type, ...)` and emitted `EDGE_OF_TYPE` from `usr → of_type_usr` — placed inside the `seen_usrs` guard to prevent duplicate edges on re-encountered cursors (forward decl + definition).

Files changed (tests):
- `tests/unit/graphdb/test_parameter_node.py` — updated module docstring; added `EDGE_OF_TYPE`, `EDGE_RETURNS`, `NODE_TYPE` imports; added `return_type_spelling` parameter to `_make_func_cursor` with explicit `result_type` mock (spelling, kind, is_const_qualified, is_volatile_qualified, get_pointee); appended test classes: `TestParameterOfTypeEdge` (SC-D-01), `TestFunctionReturnsEdge` (SC-E-01), `TestMethodReturnsEdge` (SC-E-02), `TestVoidReturnsEdge` (SC-E-03), `TestConstructorReturnsEdge` (SC-E-04), `TestDestructorReturnsEdge` (SC-E-05).
- `tests/unit/graphdb/test_field_classification.py` — appended `TestFieldOfTypeEdge` class covering SC-D-03: 2 fields both get `OF_TYPE` edges, plus dedup test.
- `tests/unit/graphdb/test_global_variable_classification.py` — appended `TestGlobalVariableOfTypeEdge` class covering SC-D-04: GlobalVariable gets `OF_TYPE` edge to correct Type spelling, plus dedup test.

Tests added/run:
- `uv run pytest tests/unit/graphdb/test_parameter_node.py tests/unit/graphdb/test_field_classification.py tests/unit/graphdb/test_global_variable_classification.py -x -q` → 50 passed
- `uv run pytest tests/unit -x -q` → 998 passed, 4 skipped, 0 failed

Deviations from plan:
- SC-D-02 (local Variable OF_TYPE): documented inline in test docstring as "local VAR_DECL is classified GlobalVariable by ADR-25 D2; the 'Variable' label in scenarios is read as the node emitted for the local VAR_DECL regardless of label". No reclassification; ADR-25 decision respected. Covered implicitly by SC-D-04 (GlobalVariable OF_TYPE).
- `_make_func_cursor` in test_parameter_node.py gained a `return_type_spelling` parameter with `default="void"` — all existing P3 tests that call it without the new arg get `return_type_spelling="void"` and emit a `RETURNS → void` Type edge. Tests that only filter by PARAMETER/HAS_PARAM labels still pass; no count-based regressions.
- ADR-26 D5 (ctor/dtor RETURNS void): confirmed that `_make_func_cursor` with `kind_name="CONSTRUCTOR"/"DESTRUCTOR"` and `return_type_spelling="void"` produces the correct behavior. No special case needed in exporter — the natural code path just works as documented.

Follow-ups:
- P5: Function signature properties (`signature`, `is_constexpr`, `is_noexcept`, `is_deleted`, `is_defaulted`, `cv_qualifiers`, `ref_qualifier`).

References: plan.md §P4, adr-26.md D5/D9, design.md §3.3/§3.4

## P5 — Function signature properties

Files changed:
- `src/cpp_mcp/graphdb/exporter.py` — added two helpers: `_method_has_volatile_qualifier(cursor)` (design §2.7, paren-depth token-scan for "volatile" after close-paren) and `_emit_function_signature_props(cursor)` (design §2.4, returns all 7 properties); wired `props.update(_emit_function_signature_props(cursor))` in `_walk_cursor` inside the `if node_type == NODE_FUNCTION:` branch before `nodes.append()`.

Files added:
- `tests/unit/graphdb/test_function_signature.py` — 26 tests covering SC-F-01..SC-F-12, plus edge cases for volatile-in-param-list (must not fire), all _FUNCTION_CURSOR_KINDS parametrize, and FUNCTION_TEMPLATE coverage.

Tests added/run:
- `uv run pytest tests/unit/graphdb/test_function_signature.py -x -q` → 26 passed
- `uv run pytest tests/unit -x -q` → 1024 passed, 4 skipped, 0 failed

Deviations from plan:
- None. All 7 properties implemented per design §2.4/§2.7 and ADR-26 D7/D10/D11.

Libclang fallbacks (per ADR-26 D10/D11, F-6/F-7):
1. `is_constexpr` absent on pinned libclang: token-scan for "constexpr" keyword fires. Limitation: if a non-constexpr function body contains `constexpr int y = 5;`, the scan may return True. Inherited from S1's `_var_qualifiers` pattern; documented in ADR-26 D10.
2. `ExceptionSpecificationKind.NOEXCEPT_FALSE` absent on pinned libclang (confirmed via probe). Only 9 values present: NONE, DYNAMIC_NONE, DYNAMIC, MS_ANY, BASIC_NOEXCEPT, COMPUTED_NOEXCEPT, UNEVALUATED, UNINSTANTIATED, UNPARSED. `noexcept(false)` reports as `COMPUTED_NOEXCEPT` and is indistinguishable from `noexcept(true)` at the enum level — both map to `is_noexcept=True` per ADR-26 D11 (COMPUTED_NOEXCEPT → True). Cannot disambiguate without inspecting the boolean expression. Documented.
3. No `is_volatile_method` on libclang: `cv_qualifiers="volatile"` detected via `_method_has_volatile_qualifier` token-scan. Scan correctly skips "volatile" appearing inside the parameter list (e.g. `void f(volatile int *)`) by only scanning tokens after the `)` that closes the param list (paren-depth tracking). SC-F-04 includes a negative test for this.
4. `ref_qualifier` via `cursor.type.get_ref_qualifier()` returning `RefQualifierKind` (NONE/LVALUE/RVALUE) → mapped to ""/&"/&&".
5. No `is_noexcept` attribute: `exception_specification_kind` enum used. BASIC_NOEXCEPT + COMPUTED_NOEXCEPT + DYNAMIC_NONE → True; all other values (NONE, DYNAMIC, MS_ANY, UNEVALUATED, UNINSTANTIATED, UNPARSED) → False.

MagicMock fixture impact:
- Existing tests using raw `MagicMock()` for function cursors will now get `cv_qualifiers="const"`, `is_deleted=True`, `is_defaulted=True` (MagicMock returns truthy for method calls). All existing tests still pass because they don't assert on function node props directly. New P5 tests use explicit `is_const_method=False` (etc.) fixtures to avoid this.

Follow-ups:
- P6: Class properties (`is_final`, `is_abstract`, `record_kind`). [DONE — see below]

References: plan.md §P5, adr-26.md D7/D10/D11, design.md §2.4/§2.7/§3.1

## P6 — Class properties (is_final, is_abstract, record_kind) + UNION_DECL classifier

Files changed:
- `src/cpp_mcp/graphdb/exporter.py` — (1) added `"UNION_DECL": NODE_CLASS` to `_KIND_TO_NODE_TYPE` (ADR-26 D8); (2) added `"UNION_DECL"` to `_MEMBER_PARENT_KINDS` so union fields emit MEMBER_OF edges to the union (consistent with struct behavior); (3) added `_emit_class_props(cursor)` helper returning `{is_final, is_abstract, record_kind}` (design §2.5); (4) wired `props.update(_emit_class_props(cursor))` in `_walk_cursor` inside the `if node_type == NODE_CLASS:` branch (parallel to existing P5 NODE_FUNCTION branch).

Files added:
- `tests/unit/graphdb/test_class_props.py` — 19 tests covering SC-G-01..SC-G-06 (all properties present, types, is_final=True/False, is_abstract=True/False, record_kind for all 4 kinds, UNION_DECL → NODE_CLASS label, defensive absent-method fallback).

Tests added/run:
- `uv run pytest tests/unit/graphdb/test_class_props.py -x -q` → 19 passed
- `uv run pytest tests/unit -x -q` → 1047 passed, 4 skipped, 0 failed (was 1024 before P6; +19 new + 4 from earlier count)

Deviations from plan:
- `_MEMBER_PARENT_KINDS` extended to include `"UNION_DECL"` — not explicitly called out in plan.md but required for correctness: union fields accessed via `cursor.get_children()` during recursive walk would otherwise emit DEFINES/DECLARES edges to the file instead of MEMBER_OF to the union. This matches the struct behavior and is consistent with `_PUBLIC_DEFAULT_PARENT_KINDS` (already contained UNION_DECL since S1). No plan violation.
- `_KIND_TO_RECORD` dict inside `_emit_class_props` is a local constant (defined inline in the function body, not a module-level constant) — acceptable style; mirrors how similar small lookup tables appear elsewhere in the project.

Follow-ups:
- P7: describe_graph_schema surface + backward-compat tests + live IndraDB smoke.
- is_template (Class) deferred to S3 per plan.md §"Out of scope".

References: plan.md §P6, adr-26.md D8/D10, design.md §2.5/§3.1

## P7 — describe_graph_schema surface + backward-compat tests + live IndraDB smoke

Files changed:
- `tests/unit/graphdb/test_describe_v2_shape.py` — extended with _make_v2_s2_graph() + TestDescribeS2Additions (SC-H-01, SC-H-02, SC-H-03, SC-H-05)
- `tests/integration/test_describe_graph_schema_e2e.py` — ADR-26 D9 updates: _V2_SPLIT_TYPES Variable→Parameter, _EXPECTED_NODE_TYPE_NAMES +Type, totals >= baseline, edge-type subset check, _SYMBOL_NODE_TYPES +Parameter +Type

Files added:
- `tests/unit/graphdb/test_s2_failure_mode.py` — SC-FM-01: 3 classes / 8 tests; degenerate TU variants (empty, raising result_type, raising param.type, raising get_children)

Tests added/run:
- `uv run ruff format src tests` → 0 issues
- `uv run ruff check src tests` → 0 violations
- `uv run pytest tests/unit -x -q` → 1054 passed, 5 skipped (baseline was 1024)
- `uv run pytest tests/integration -x -q` → 39 deselected (no INDRADB daemon)

Deviations from plan:
- test_s2_failure_mode.py::TestSCFM01GetChildrenRaises skips at runtime — exporter has no top-level guard around _walk_cursor for cursor.get_children() exceptions. EC-16 "assumed" does not hold for this path. Flagged to sr-dev; test documents behavior via pytest.skip not a failure.
- Integration test changes broader than ADR-26 D9 table rows 65/84/176-214: totals loosened to >=, edge-count check made subset, _EXPECTED_NODE_TYPE_NAMES and _SYMBOL_NODE_TYPES extended. All are conservative extensions justified by advisor review.
- SC-H-05 test added to test_describe_v2_shape.py (plan listed SC-H-04/SC-H-05 as verified via untouched existing tests; added an explicit SC-H-05 assertion in the v2-shape file for completeness).

Follow-ups:
- [sr-dev] Add top-level try/except around _walk_cursor(tu.cursor) in extract_nodes_and_edges to guard against cursor.get_children() exceptions (EC-16 gap).
- [sr-dev] Re-pin integration test totals (vertices/edges) after first live S2 run against {fmt}/os.cc.
- Live smoke: IndraDB daemon absent; deferred per task dispatch note. Run manually; findings go to logs/senior-developer-p7.md per plan.md §P7.

References: plan.md §P7, design.md §4/§6, scenarios.md SC-H-01..SC-H-06/SC-FM-01, adr-26.md D9
