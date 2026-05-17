# Plan — cpp-mcp v7 Stage S2

Goal: Additively enrich v2 schema with Type/Parameter nodes, RETURNS/HAS_PARAM/OF_TYPE/POINTS_TO/REFERS_TO edges, function signature props, and Class qualifier props — per ADR-26, no schema_version bump, no pyproject bump.

Toolchain (Python, pinned in CHARTER): `uv`, `ruff`, `pytest`. Real backend code lives in:
- `src/cpp_mcp/graphdb/schema.py` (NODE_* / EDGE_* constants + ALL_* lists)
- `src/cpp_mcp/graphdb/exporter.py` (`_KIND_TO_NODE_TYPE`, `_walk_cursor`, helpers)
- `src/cpp_mcp/graphdb/schema_version.py` (stays `"v2"` — do NOT modify)
- `src/cpp_mcp/graphdb/schema_introspector.py` (read-only; surfaces new labels automatically)

Story sequencing: P1 → P2 → P3 → P4 → P5 → P6 → P7. P6 (Class props) and P7 (compat tests + live) may run in parallel with each other after P5 lands, since their file edits are disjoint. All other stories edit `exporter.py` sequentially. Total: 7 stories (parallel-safe count: 2).

Shared exit-criteria template (each story MUST satisfy):
- `uv run ruff format src tests` — passes (idempotent reformat)
- `uv run ruff check src tests` — zero violations
- `uv run pytest tests/unit -x -q` — zero failures (test deltas allowed only as listed in ADR-26 D9)
- Story-specific scenario assertions named under each story below

---

## Story P1 — Schema constants (Type, Parameter, 5 edges)

Goal: Add new node/edge constants so subsequent stories can import them; no behavioral change yet.

ACs covered: S2-A.AC3 (constant surface), S2-C (constant surface), S2-D/E/B (constant surface), S2-H.AC1/AC2 (introspector autopickup precondition).

Files to change:
- `src/cpp_mcp/graphdb/schema.py` — add constants `NODE_TYPE = "Type"`, `NODE_PARAMETER = "Parameter"`, `EDGE_RETURNS = "RETURNS"`, `EDGE_HAS_PARAM = "HAS_PARAM"`, `EDGE_OF_TYPE = "OF_TYPE"`, `EDGE_POINTS_TO = "POINTS_TO"`, `EDGE_REFERS_TO = "REFERS_TO"`; extend `ALL_NODE_TYPES` (keep `NODE_VARIABLE` per ADR-25 D1 / ADR-26 D9), extend `ALL_EDGE_TYPES`.

New files:
- `tests/unit/graphdb/test_s2_schema_constants.py` — assert new constants exist, are unique strings, appear in `ALL_*` lists, and that `NODE_VARIABLE` is still exported (read-compat invariant).

Tests:
- New: `tests/unit/graphdb/test_s2_schema_constants.py`
- Untouched (must still pass): `tests/unit/graphdb/test_schema_constants.py`, `tests/unit/graphdb/test_describe_v1_compat.py`, `tests/unit/graphdb/test_indradb_query_subset.py`

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit/graphdb/test_s2_schema_constants.py -x -q
uv run pytest tests/unit -x -q
```

Risks: importing new constants elsewhere prematurely. Mitigation: P1 only adds constants; no exporter wiring.

References: ADR-26 D8, D9; design.md §1.1, §1.2; CHARTER §"S2 schema additions".

---

## Story P2 — Type node + dedup + POINTS_TO/REFERS_TO chain

Goal: Implement `_get_or_create_type`, `_type_usr`, `_type_props`, and chained pointer/ref recursion. Type nodes are emitted on demand from callers added in later stories; P2 ships the helper plus a focused caller hook for **return type** to make the helper exercisable end-to-end without yet touching parameters/vars.

ACs covered: S2-A.AC1/AC2/AC3/AC4 (all Type properties + dedup + USR format + lvalue/rvalue mutual exclusion); S2-B.AC1/AC2/AC3/AC4 (POINTS_TO/REFERS_TO single-edge correctness + chain).

Files to change:
- `src/cpp_mcp/graphdb/exporter.py` — add helpers `_type_usr`, `_type_props`, `_get_or_create_type` per design §2.1–2.3; wire a minimal call at the Function emission site only for `cursor.result_type` to drive Type creation for SC-A and SC-B fixtures (the full RETURNS edge wiring is finalized in P4; in P2 we create the Type but do NOT yet emit the RETURNS edge — that lands with P4 alongside parameter wiring to keep the function-block diff atomic).

Tests:
- New: `tests/unit/graphdb/test_type_node.py` — covers SC-A-01..SC-A-09 with fake cursors / minimal real fixtures.
- New: `tests/unit/graphdb/test_type_edges.py` — covers SC-B-01..SC-B-05 including `int **` two-edge chain (ADR-26 D4).

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit/graphdb/test_type_node.py tests/unit/graphdb/test_type_edges.py -x -q
uv run pytest tests/unit -x -q
```

Risks: source-form vs desugared spelling regression. Mitigation: ADR-26 D2 mandates `cursor.type.spelling` (NOT `get_canonical().spelling`); add an explicit test that asserts `const std::string &` is preserved (not desugared to `std::basic_string<...>`).

References: ADR-26 D1, D2, D3, D4; design.md §2.1–2.3, §3 prelude.

---

## Story P3 — Parameter node + HAS_PARAM edge + PARM_DECL reclassification

Goal: Emit `Parameter` nodes from `cursor.get_arguments()` enumeration, with positional USR `<fn-usr>#param:<i>`, plus `HAS_PARAM` edges with `index` edge property. Reclassify `PARM_DECL` from `NODE_VARIABLE` (ADR-25 D2 transitional) to `NODE_PARAMETER` (ADR-26 D9) and skip PARM_DECL in generic child recursion (design §3.2).

ACs covered: S2-C.AC1/AC2/AC3/AC4/AC5 (3-param, unnamed, default value, source order, zero-param boundary, methods/ctors/dtors).

Files to change:
- `src/cpp_mcp/graphdb/exporter.py` — update `_KIND_TO_NODE_TYPE` to map `PARM_DECL → NODE_PARAMETER`; add `_render_default_value` helper (design §2.6); add the function-block enumeration of `get_arguments()` (design §3.2 option (a)); add the skip-PARM_DECL-in-generic-recursion guard.

Tests:
- New: `tests/unit/graphdb/test_parameter_node.py` — covers SC-C-01..SC-C-10.
- Updates (expected per ADR-26 D9 — NOT regressions): `tests/unit/graphdb/test_field_classification.py:327-384` (PARM_DECL section rewrite), `tests/unit/graphdb/test_global_variable_classification.py:167` (Variable → Parameter filter), `tests/unit/test_graphdb_additions.py:53,66` (inspect & update if asserts PARM_DECL emission).
- Untouched (must still pass — v1 compat): `tests/unit/graphdb/test_describe_v1_compat.py`, `tests/unit/graphdb/test_indradb_query_subset.py`, `tests/unit/graphdb/test_schema_constants.py`.

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit/graphdb/test_parameter_node.py -x -q
uv run pytest tests/unit -x -q
```

Risks: duplicate Parameter vertices if generic recursion still visits PARM_DECL. Mitigation: explicit skip guard + assertion that PARM_DECL is never reached via generic recursion after the function-arg loop (design §3.2 footnote).

References: ADR-26 D6, D9, D10; design.md §2.6, §3.2.

---

## Story P4 — OF_TYPE edges + RETURNS edge (finalize function-block emissions)

Goal: Wire `OF_TYPE` from Parameter/Variable/Field/GlobalVariable to their Type via `_get_or_create_type`, and emit the `RETURNS` edge from every Function cursor to its return-type Type node (constructors & destructors both → `void` Type per ADR-26 D5).

ACs covered: S2-D.AC1/AC2/AC3/AC4/AC5 (all four OF_TYPE source kinds, no duplicates); S2-E.AC1/AC2/AC3/AC4 (free fn, method, void, ctor/dtor → void).

Files to change:
- `src/cpp_mcp/graphdb/exporter.py` — extend the existing Field/GlobalVariable property block (lines 520-530) to emit `OF_TYPE` after computing props (design §3.4); inside the function-arg loop from P3, emit `OF_TYPE` from each Parameter to its type Type; in the `_FUNCTION_CURSOR_KINDS` block, emit `RETURNS` edge after `_get_or_create_type(cursor.result_type, ...)` (design §3.3).

Tests:
- Extend `tests/unit/graphdb/test_global_variable_classification.py` and `tests/unit/graphdb/test_field_classification.py` with OF_TYPE edge-count assertions (SC-D-03, SC-D-04, SC-D-05).
- Extend `tests/unit/graphdb/test_parameter_node.py` with OF_TYPE on Parameter (SC-D-01) and RETURNS scenarios (SC-E-01..SC-E-05). Note: SC-E-04 / SC-E-05 substitute `"void"` for ADR-26-rule placeholder.
- SC-D-02 (local variable OF_TYPE): write the assertion using whatever label the local VAR_DECL currently emits (per design §3.4 / §7, ADR-25 classifies VAR_DECL → GlobalVariable unconditionally; do NOT reclassify in S2). Document in `tests/unit/graphdb/test_parameter_node.py` why the label may read `GlobalVariable` rather than literal `Variable`.

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit/graphdb/test_parameter_node.py tests/unit/graphdb/test_field_classification.py tests/unit/graphdb/test_global_variable_classification.py -x -q
uv run pytest tests/unit -x -q
```

Risks: OF_TYPE emitted twice for the same node if hook lives in two places. Mitigation: emit OF_TYPE exactly once per node-create site (function-arg loop for Parameter; Field/Global block for those; no generic-recursion path). Cross-check via `EdgeRecord` count assertions.

References: ADR-26 D5; design.md §3.3, §3.4, §7.

---

## Story P5 — Function signature properties

Goal: Add `signature`, `is_constexpr`, `is_noexcept`, `is_deleted`, `is_defaulted`, `cv_qualifiers`, `ref_qualifier` to every `Function` node via `_emit_function_signature_props` + `_method_has_volatile_qualifier` helpers. DEFERRED (do not emit): `is_template`, `is_virtual`, `is_override`.

ACs covered: S2-F.AC1..AC7 (SC-F-01..SC-F-12). SC-F-01-sig substitutes `cursor.displayname` per ADR-26 D7.

Files to change:
- `src/cpp_mcp/graphdb/exporter.py` — add `_emit_function_signature_props` (design §2.4) and `_method_has_volatile_qualifier` (design §2.7); call `props.update(_emit_function_signature_props(cursor))` inside the `if node_type == NODE_FUNCTION` branch of `_walk_cursor` (design §3.1, before `nodes.append`).

Tests:
- New: `tests/unit/graphdb/test_function_signature.py` — covers SC-F-01..SC-F-12.
- Includes explicit cases for ADR-26 D11 `is_noexcept` semantics: `noexcept(false)` → False; `throw()` (DYNAMIC_NONE) → True; plain `noexcept` → True; no spec → False.

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit/graphdb/test_function_signature.py -x -q
uv run pytest tests/unit -x -q
```

Risks: libclang capability mismatch (e.g., `is_constexpr` absent). Mitigation: ADR-26 D10 capability matrix is authoritative; use `getattr + callable` guards and token-scan fallback per S1 pattern (`_var_qualifiers`, `_storage_class_value`). Risk: `cv_qualifiers="volatile"` token scan misreads multi-line method signatures. Mitigation: add SC-F-04 with both single-line and multi-line formatting (per ADR-26 F-7 follow-up).

References: ADR-26 D7, D10, D11; design.md §2.4, §2.7, §3.1.

---

## Story P6 — Class properties (is_final, is_abstract, record_kind) + UNION_DECL classifier

Goal: Add `_emit_class_props` helper (design §2.5) and add `UNION_DECL → NODE_CLASS` to `_KIND_TO_NODE_TYPE` so `record_kind="union"` works. Wire into `_walk_cursor`'s Class branch.

ACs covered: S2-G.AC1..AC6 (SC-G-01..SC-G-06).

Files to change:
- `src/cpp_mcp/graphdb/exporter.py` — add `"UNION_DECL": NODE_CLASS` to `_KIND_TO_NODE_TYPE` (ADR-26 D8); add `_emit_class_props` helper; call `props.update(_emit_class_props(cursor))` inside the `if node_type == NODE_CLASS` branch.

Tests:
- New: `tests/unit/graphdb/test_class_props.py` — covers SC-G-01..SC-G-06 (Scenario Outline expanded to class/struct/union rows).

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit/graphdb/test_class_props.py -x -q
uv run pytest tests/unit -x -q
```

Parallel-safe with P7: edits in `exporter.py` Class branch only; P7 edits no source files.

Risks: `is_abstract_record()` semantics on forward decls. Mitigation: scope `is_abstract` to definitions only; default to False on incomplete records.

References: ADR-26 D8, D10; design.md §2.5, §3.1.

---

## Story P7 — describe_graph_schema surface + backward-compat tests + live IndraDB smoke

Goal: Verify that `describe_graph_schema` autopickup surfaces `Type`, `Parameter`, and the five new edges; verify v1 and v2-from-S1 backward compat (SC-H-04, SC-H-05); verify SC-H-06 no-regression; run live `ingest_code` smoke against `{fmt}` to confirm scale (mirrors v6 live test).

ACs covered: S2-H.AC1/AC2/AC3/AC4/AC5/AC6 (SC-H-01..SC-H-06); SC-FM-01 (malformed TU produces no partial Type state).

Files to change: NONE in `src/` (the introspector is read-only and surfaces labels live per design §4). Test-only stage.

New / updated files:
- Extend `tests/unit/graphdb/test_describe_*` (whichever exists post-S1) to add SC-H-01, SC-H-02, SC-H-03 assertions. Find file via `rg -l describe_graph_schema tests/unit`.
- Keep `tests/unit/graphdb/test_describe_v1_compat.py` and `tests/unit/graphdb/test_indradb_query_subset.py` unchanged (ADR-26 D9 mandate — they prove SC-H-04 via seeded `"Variable"` vertices).
- Update `tests/integration/test_describe_graph_schema_e2e.py:65,84,176-214` — replace PARM-only Variable count assertion with Parameter count assertion (ADR-26 D9 table).
- New: `tests/unit/graphdb/test_s2_failure_mode.py` — SC-FM-01 (malformed TU → no partial Type/Parameter nodes); verify per design §6 row "SC-FM-01".

Live smoke (manual, post-test; report in handoff `logs/senior-developer-p7.md` or equivalent):
- Run `ingest_code` on local `{fmt}` checkout; confirm Type/Parameter node counts > 0, RETURNS/HAS_PARAM/OF_TYPE edges populate, `describe_graph_schema` lists all new labels with non-zero counts, schema_version still `"v2"`.

Exit-criteria commands:
```
uv run ruff format src tests
uv run ruff check src tests
uv run pytest tests/unit -x -q
uv run pytest tests/integration -x -q
```

(Live smoke is a separate manual check; not a gating CI command, but its absence blocks QA sign-off per CHARTER I4.)

Parallel-safe with P6: P7 touches no `src/` files, only tests.

Risks:
- A pre-existing test asserts on old `Variable`-count value for PARM_DECL emissions. Mitigation: ADR-26 D9 lists the four files where updates are expected; treat as ADR-bound expected churn, NOT regression.
- Live smoke may surface unseen IndraDB executor gaps with the new edge types (similar to v6 INTERNAL_ERROR findings). Mitigation: file findings into `logs/senior-developer-p7.md`; coordinator decides whether to spawn a hotfix story before closing S2.

References: ADR-26 D9; design.md §4, §6, §7; PRD §"Acceptance criteria".

---

## Out of scope (do NOT touch in S2)

- `is_template` on Function or Class (S3)
- `is_virtual` / `is_override` on Function (S4)
- OVERRIDES / FRIEND_OF / INHERITS.is_virtual (S4)
- INSTANTIATES / SPECIALIZES / TEMPLATE_PARAM / TEMPLATE_ARG / CONSTRAINED_BY / Concept (S3)
- Enum / Enumerator / ENUMERATOR_OF / UNDERLYING_TYPE / USES_* / ALIAS_OF (S5)
- IndraDB ordered-traversal verb (S6)
- `pyproject.toml` version bump 0.4.0 → 0.5.0 (S6 final)
- `schema_version` bump (stays `"v2"` for entire S2)
- Reclassifying local VAR_DECL out of `GlobalVariable` (ADR-25 D2 decision; S2 does not revisit)

---

## Cross-cutting risks

- **PARM_DECL migration churn**: ADR-26 D9 enumerates the 4 expected test updates and 3 tests that MUST stay unchanged (v1 read-compat). QA must read D9 before flagging "regression". Surface to QA in test-report.md.
- **Source-form vs desugared spelling**: ADR-26 D2 binds `cursor.type.spelling` only. Any helper that reaches for `get_canonical()` is a defect.
- **Constructor/destructor RETURNS rule**: ADR-26 D5 says both → `void` Type. Implementer must NOT special-case; libclang's `result_type.spelling` already returns `"void"` for both kinds — the natural path Just Works.
- **Type node count explosion** on large TUs ({fmt}-scale): acceptable per ADR-26 §Negative consequences, but P7 live smoke confirms. If perf regresses materially, file follow-up; do NOT block S2 close.

---

## References

- Requirements: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements.md`
- Scenarios: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/scenarios.md`
- Design: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/design.md`
- ADR: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md` (Status: accepted)
- CHARTER: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md`
- Prior stage (S1): `~/workspace/cpp-mcp/.claude/handoff/v7/`, wiki `~/workspace/wiki/pages/code/cpp-mcp-v7-s1.md`
- PRD: `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md`
- Cognee tags: `task:cpp-mcp-v7-s2`, `role:senior-developer`
