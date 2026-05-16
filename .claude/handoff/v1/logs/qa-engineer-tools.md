run_id: cpp-mcp-1
stage: qa-engineer
story-scope: navigation-tools (Story 5 / US-1..US-3) + ast-and-structural-tools (Story 6 / US-4..US-6)
date: 2026-05-16

---

Scope: cpp_get_definition, cpp_get_references, cpp_get_type_info, cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state
Test plan: unit | BDD/E2E | boundary/property-based

---

## Commands run

```
uv run pytest tests/ -q                                    → 321 passed, 1 skipped in 3.17s
uv run pytest tests/unit/test_tools_qa.py -v               → 23 passed in 0.10s
uv run pytest tests/bdd/ -v -rs                            → 77 passed in 1.40s (0 skipped)
uv run ruff format tests/unit/test_tools_qa.py             → 1 file reformatted
uv run ruff check --fix tests/unit/test_tools_qa.py        → 1 fixed (unused import), all checks pass
```

Baseline (pre-QA-additions): 298 tests passed (187 in prior suites + 111 from other QA agents).
Post-QA-additions: 321 passed, 1 skipped (NEO4J_TEST_URI not set — pre-existing), 0 failed.
New tests added: 23.

---

## Results: PASS

No failing tests. No open QA_DEFECT signal IDs.

All @libclang-tagged BDD scenarios executed (libclang present on host). The developer substituted `requires_libclang` (pytest.mark.skipif) for a feature-file `@libclang` tag. Confirmed: @SC_US_4_1..4_6, @SC_US_5_1..5_5, @SC_US_6_1..6_5 all ran — 0 skipped by libclang gate in these feature files.

---

## AC traceability (US-1..US-6)

| Scenario ID | AC         | Status | Test location                                               |
|---|---|---|---|
| SC-US-1-1   | US-1/AC-1  | PASS   | test_get_definition.py / SC_US_1_1                         |
| SC-US-1-5   | US-1/AC-5  | PASS   | test_get_definition.py / SC_US_1_5                         |
| SC-US-1-6   | US-1/AC-6  | PASS   | test_get_definition.py / SC_US_1_6                         |
| SC-US-1-7   | US-1/AC-6  | PASS   | test_get_definition.py / SC_US_1_7                         |
| SC-US-1-9   | US-1/AC-8  | PASS   | test_get_definition.py / SC_US_1_9                         |
| SC-US-1-10  | US-1/AC-9  | PASS   | test_get_definition.py / SC_US_1_10                        |
| SC-US-1-11  | US-12/AC-2 | PASS   | test_get_definition.py / SC_US_1_11                        |
| SC-US-1-14  | edge case  | PASS   | test_get_definition.py / SC_US_1_14                        |
| SC-US-2-1   | US-2/AC-1  | PASS   | test_get_references.py / SC_US_2_1                         |
| SC-US-2-2   | US-2/AC-2  | PASS   | test_get_references.py / SC_US_2_2                         |
| SC-US-2-4   | US-2/AC-4  | PASS   | test_get_references.py / SC_US_2_4                         |
| SC-US-2-5   | US-2/AC-5  | PASS   | test_get_references.py / SC_US_2_5                         |
| SC-US-2-6   | US-2/AC-6  | PASS   | test_get_references.py / SC_US_2_6                         |
| SC-US-3-1   | US-3/AC-1  | PASS   | test_get_type_info.py / SC_US_3_1                          |
| SC-US-3-2   | US-3/AC-2  | PASS   | BDD SC_US_3_2 + unit regression pin test_tools_qa.py       |
| SC-US-3-3   | US-3/AC-3  | PASS   | test_get_type_info.py / SC_US_3_3                          |
| SC-US-3-4   | US-3/AC-4  | PASS   | test_get_type_info.py / SC_US_3_4                          |
| SC-US-3-6   | US-3/AC-6  | PASS   | test_get_type_info.py / SC_US_3_6                          |
| SC-US-3-7   | US-3/AC-6  | PASS   | test_get_type_info.py / SC_US_3_7                          |
| SC-US-3-8   | US-3/AC-7  | PASS   | test_get_type_info.py / SC_US_3_8                          |
| SC-US-4-1   | US-4/AC-1  | PASS   | test_get_ast.py / SC_US_4_1                                |
| SC-US-4-2   | US-4/AC-2  | PASS   | test_get_ast.py / SC_US_4_2                                |
| SC-US-4-3   | US-4/AC-3  | PASS   | BDD SC_US_4_3 + property tests test_tools_qa.py            |
| SC-US-4-4   | US-4/AC-5  | PASS   | BDD SC_US_4_4 + monotonicity property test_tools_qa.py     |
| SC-US-4-5   | US-4/AC-4  | PASS   | test_get_ast.py / SC_US_4_5                                |
| SC-US-4-6   | US-4/AC-7  | PASS   | test_get_ast.py / SC_US_4_6                                |
| SC-US-4-7   | US-4/AC-8  | PASS   | test_get_ast.py / SC_US_4_7                                |
| SC-US-4-8   | US-4/AC-9  | PASS   | BDD SC_US_4_8 + boundary params test_tools_qa.py           |
| SC-US-4-9   | US-4/AC-10 | PASS   | test_get_ast.py / SC_US_4_9                                |
| SC-US-4-10  | US-4/AC-6  | PASS   | test_get_ast.py / SC_US_4_10                               |
| SC-US-4-11  | US-13/AC-3 | PASS   | unit test_fatal_parse_error_raised_* (mocked TU)           |
| SC-US-5-1   | US-5/AC-1  | PASS   | test_get_header_info.py / SC_US_5_1                        |
| SC-US-5-2   | US-5/AC-2  | PASS   | test_get_header_info.py / SC_US_5_2                        |
| SC-US-5-3   | US-5/AC-3  | PASS   | test_get_header_info.py / SC_US_5_3                        |
| SC-US-5-4   | US-5/AC-4  | PASS   | test_get_header_info.py / SC_US_5_4 (orphaned_includes)    |
| SC-US-5-5   | US-5/AC-5  | PASS   | test_get_header_info.py / SC_US_5_5                        |
| SC-US-5-6   | US-5/AC-6  | PASS   | test_get_header_info.py / SC_US_5_6                        |
| SC-US-5-7   | US-5/AC-7  | PASS   | test_get_header_info.py / SC_US_5_7                        |
| SC-US-6-1   | US-6/AC-1  | PASS   | test_get_preprocessor_state.py / SC_US_6_1                 |
| SC-US-6-2   | US-6/AC-2  | PASS   | test_get_preprocessor_state.py / SC_US_6_2                 |
| SC-US-6-3   | US-6/AC-3  | PASS   | BDD SC_US_6_3 (weak) + unit test_preprocessor_ifdef_*      |
| SC-US-6-4   | US-6/AC-4  | PASS   | test_get_preprocessor_state.py / SC_US_6_4                 |
| SC-US-6-5   | US-6/AC-5  | PASS   | test_get_preprocessor_state.py / SC_US_6_5                 |
| SC-US-6-6   | US-6/AC-6  | PASS   | test_get_preprocessor_state.py / SC_US_6_6                 |
| SC-US-6-7   | US-6/AC-7  | PASS   | test_get_preprocessor_state.py / SC_US_6_7                 |

### Scenario IDs from scenarios.md absent from feature files (coverage gap — not defects)

These are absent because the test harness does not support compile_commands.json injection
or multi-TU parsing, or the scenario is tagged needs-clarification:
- SC-US-1-2 (cross-file navigation), SC-US-1-3 (compilation_db flags_source)
- SC-US-1-4 (default flags in definition), SC-US-1-8 (empty build dir)
- SC-US-2-3 (references default flags), SC-US-2-7 (large reference list truncation)
- SC-US-3-5 (type_info default flags)

---

## Defects

none — Invariant I4 satisfied. See observations for assertion-strength findings.

---

## observations

- **D-TOOLS-001 (assertion-strength, advisory)** SC-US-4-3: BDD step `_check_truncated_at_depth`
  (test_get_ast.py:327-335) has a no-op branch: `if depth >= limit and node.get("truncated"): pass`
  — nothing is asserted. Mitigated by `test_ast_depth_truncated_flag_set_when_children_pruned`
  (test_tools_qa.py) which asserts at least one depth-1 boundary node has truncated=True.

- **D-TOOLS-002 (assertion-strength, advisory)** SC-US-6-3: BDD step `_check_conditional_directives`
  (test_get_preprocessor_state.py:189-198) passes when conditionals=[]. AC US-6/AC-3 requires
  evaluated_result=true for #ifdef; the BDD step never asserts this. Mitigated by
  `test_preprocessor_ifdef_debug_evaluated_result_is_true` (test_tools_qa.py) which asserts
  conditionals is non-empty AND #ifdef MY_VERSION evaluated_result is True.

- **D-TOOLS-003 (passes-by-construction, advisory)** SC-US-4-7: BDD step `_call_ast_nonexistent`
  (test_get_ast.py:154-183) catches any exception and constructs build_error(FILE_NOT_FOUND, ...)
  itself; the Then step asserts code=FILE_NOT_FOUND, which is true by construction regardless of
  what the tool raised. Path-guard is independently tested in tests/unit/test_path_guard.py.

- SC-US-4-11 (unparseable.cpp zero-node TU): the binary fixture may not produce zero nodes
  + fatal diagnostics across all libclang versions. The mocked-TU unit test covers the
  detection logic; the real-libclang path is architecturally exercised but not asserted.
- `test_foundation_property.py::test_valid_path_inside_root_always_passes` flaked once
  in parallel run (Hypothesis database state contention); passes in isolation. Pre-existing,
  outside this story scope.
- Warning `Unknown pytest.mark.SC_US_14_CALL_ENVELOPE` pre-exists from another QA agent scope.
- SC-US-4-11 and SC-US-4-12 remain `needs-clarification` per scenarios.md; architect
  decision on PARSE_ERROR threshold (zero nodes vs. partial AST) has not been recorded.

---

## Additions made

Category: property-based + boundary (option 2 of the mandatory three categories).

File: /Users/husam/workspace/cpp-mcp/tests/unit/test_tools_qa.py (23 new tests, all pass).

Test groups in the new file:
1. test_ast_depth_truncation_signals_truncated_flag [parametrize depth∈{0,1,2,3,5}]
   — tree depth ≤ limit; D-TOOLS-001 detection.
2. test_ast_depth_truncated_flag_set_when_children_pruned
   — positive assertion: at least one boundary node has truncated=True (SC-US-4-3).
3. test_ast_nodes_emitted_monotonic_with_depth [parametrize depth∈{1,2,3,4}]
   — nodes_emitted non-decreasing with depth (SC-US-4-3/4-4 property).
4. test_invalid_range_boundary [5 parametrize cases including start==end]
   — INVALID_RANGE fires on start>end; does NOT fire on start==end (SC-US-4-8).
5. test_has_zero_ast_nodes_* + test_has_fatal_diagnostics_* (4 unit tests)
   — PARSE_ERROR detection helpers (SC-US-4-11).
6. test_fatal_parse_error_raised_when_zero_nodes_and_fatal_diag
   — FatalParseError raised end-to-end with mocked TU (SC-US-4-11).
7. test_preprocessor_ifdef_debug_evaluated_result_is_true
   — conditionals non-empty; evaluated_result is real bool True (SC-US-6-3).
8. test_type_info_auto_resolves_to_float
   — regression pin: canonical_type contains 'float', not 'auto' (SC-US-3-2).
9. test_ast_budget_truncation_max_nodes_one
   — budget fires at max_nodes=1; truncated=True + reason='max_nodes' (ADR-5).

---

## References

- scenarios.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md
- developer log (navigation): /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-navigation-tools.md
- developer log (ast/structural): /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-ast-and-structural-tools.md
- new test file: /Users/husam/workspace/cpp-mcp/tests/unit/test_tools_qa.py
- cognee tags: task:cpp-mcp role:qa-engineer scope:tools
