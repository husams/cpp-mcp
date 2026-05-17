Scope: cpp-mcp v7 Stage S2 — Type/Parameter nodes, RETURNS/HAS_PARAM/OF_TYPE/POINTS_TO/REFERS_TO edges, Function signature props, Class props, describe_graph_schema surface + backward compat
Test plan: unit | integration | regression

## Commands run

```
uv run ruff format src tests          # 0 changes
uv run ruff check src tests           # 0 violations
uv run pytest -q --ignore=tests/integration
uv run pytest tests/integration -q
```

## Results

Unit (incl. new additions): 1183 passed / 7 skipped / 0 failed
Integration: 39 deselected (exit 5 — all skipped; daemon absent)
Ruff format: 0 files changed
Ruff check: 0 violations

### Skip breakdown

| Test | Reason | Acceptable |
|------|--------|------------|
| tests/bdd/test_ingest_code_indradb.py (×2) | INDRADB_TEST_URI not set | yes |
| tests/unit/graphdb/test_s2_failure_mode.py::TestSCFM01GetChildrenRaises | no top-level guard around cursor.get_children() in extract_nodes_and_edges | see observations |
| tests/unit/test_cognee_driver.py (×3) | COGNEE_BASE_URL not set | yes |
| tests/unit/test_graphdb_additions.py | NEO4J_TEST_URI not set | yes |

## SC-ID coverage matrix

All 59 scenario IDs from scenarios.md are covered:

| Feature | SC-IDs | Test file |
|---------|--------|-----------|
| S2-A (Type node) | SC-A-01..SC-A-09 | test_type_node.py |
| S2-B (POINTS_TO/REFERS_TO) | SC-B-01..SC-B-05 | test_type_edges.py |
| S2-C (Parameter + HAS_PARAM) | SC-C-01..SC-C-10 | test_parameter_node.py |
| S2-D (OF_TYPE) | SC-D-01..SC-D-05 | test_parameter_node.py, test_field_classification.py, test_global_variable_classification.py, **test_s2_boundary.py** (SC-D-05 combined) |
| S2-E (RETURNS) | SC-E-01..SC-E-05 | test_parameter_node.py |
| S2-F (Fn signature props) | SC-F-01..SC-F-12, SC-F-01-sig | test_function_signature.py |
| S2-G (Class props) | SC-G-01..SC-G-06 | test_class_props.py |
| S2-H (describe + compat) | SC-H-01..SC-H-03, SC-H-05 | test_describe_v2_shape.py |
| S2-H (v1 backward compat) | SC-H-04 | test_describe_v1_compat.py::TestV1Compatibility::test_describe_v1_graph_does_not_raise (implicit; lacks SC-H-04 tag — see observations) |
| S2-H (no-regression) | SC-H-06 | full unit suite (1183 pass, S1 baseline 1020 fully covered) |
| Failure mode | SC-FM-01 | test_s2_failure_mode.py (get_children path SKIPped; other 8 variants pass) |

Notes on `@needs-clarification` scenarios (now resolved per ADR-26):
- SC-B-05: int** → chained 2-edge POINTS_TO implemented and tested.
- SC-E-04/SC-E-05: ctor/dtor both → void Type per ADR-26 D5; tested with `return_type_spelling="void"`.
- SC-F-01-sig: signature = `cursor.displayname` per ADR-26 D7; tested in test_function_signature.py::TestDisplaynameAsSignature.

## Defects

None.

## P7 follow-up assessment

### (a) top-level guard for cursor.get_children() exceptions

- Scenario SC-FM-01 is tagged `@assumed` and `@failure-mode`, not `@confirmed`.
- scenarios.md line 914: `# EC-16 — assumed (not explicit in AC; derived from general consistency requirement)`
- The BA's own scenario comment states: "Verify this with the developer; may need an explicit transactional guard."
- There is NO acceptance criterion binding this behaviour.
- Assessment: **advisory only — not a QD**. A real get_children() exception from libclang would propagate up uncaught; whether that is desirable (fail fast) vs guarded (atomicity) is a design decision not made in S2. The skip in test_s2_failure_mode.py::TestSCFM01GetChildrenRaises correctly documents the behaviour without making the test green by lying.
- CHARTER I4 status: not blocking (zero open QD entries).

### (b) integration totals re-pin after live S2 run

- Advisory. Daemon absent; 39 deselected. No live run possible in this environment.
- Re-pin after first live ingest against {fmt}/os.cc per plan.md §P7.

## observations

- SC-H-04 is covered by test_describe_v1_compat.py::TestV1Compatibility::test_describe_v1_graph_does_not_raise but lacks the SC-H-04 scenario tag in the docstring. Advisory; test passes.
- Individual OF_TYPE per-kind tests cover SC-D-05 component-by-component; test_s2_boundary.py::test_sc_d_05_combined_of_type_completeness now provides the combined assertion from scenarios.md.
- P5 implementation notes flag: `noexcept(false)` (COMPUTED_NOEXCEPT) is indistinguishable from `noexcept(true)` at the enum level on pinned libclang — both map to is_noexcept=True. ADR-26 D11 documents this; not a defect.
- MagicMock truthy fallback in P5: old test fixtures using bare MagicMock() for function cursors now get cv_qualifiers="const", is_deleted=True, is_defaulted=True from MagicMock return values. All prior tests pass because they do not assert on these new props. Advisory design smell; does not block.
- Live smoke (ingest against {fmt}) was not run; daemon absent. Defer to manual per plan.md §P7.

## Additions made

Category 2 — property-based / parametrised:
File: tests/unit/graphdb/test_s2_boundary.py (17 new tests)

Tests:
1. `test_type_dedup_k_functions_m_spellings` — @parametrize over (K,M) pairs (1,1), (2,1), (5,1), (2,2), (5,3), (10,4): K function cursors sharing M distinct type spellings must produce exactly M Type nodes. Covers the dedup invariant of ADR-26 D2/D3 at boundary scale.
2. `test_distinct_spellings_produce_distinct_usrs` — @parametrize over 10 spelling pairs from S2 vocabulary: distinct spellings must never hash-collide to the same USR (ADR-26 D1 boundary).
3. `test_sc_d_05_combined_of_type_completeness` — combined TU with GlobalVariable + Field + Parameter; each must emit exactly 1 OF_TYPE edge (SC-D-05, S2-D.AC5). Fills gap left by per-symbol individual tests.

## References

- scenarios.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/scenarios.md
- implementation-notes.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/implementation-notes.md
- plan.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/plan.md
- ADR-26: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md
- CHARTER: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md
- Cognee tags: task:cpp-mcp-v7-s2, role:qa-engineer
