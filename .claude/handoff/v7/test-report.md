run_id: cpp-mcp-v7-s1
stage: S1 of 6
produced_by: qa-engineer
charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
scenarios: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/scenarios.md
implementation-notes: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/implementation-notes.md

---

Scope: cpp-mcp v7 S1 — Variable→Field/GlobalVariable split; MEMBER_OF.access; new node properties; schema_version=v2; backward-compat; live integration extension (P1–P6).

Test plan: unit | integration (daemon-gated) | mutation/boundary (QA addition)

---

## Commands run

```
# 1. Coordinator baseline — reproduced verbatim
uv run pytest -q --ignore=tests/integration
# → 959 passed, 6 skipped, 12 warnings in 13.52s  (pre-addition baseline)

# 2. New QA test file — lint + run
uv run ruff format tests/unit/graphdb/test_resolve_access_matrix.py
# → 1 file reformatted
uv run ruff check tests/unit/graphdb/test_resolve_access_matrix.py
# → All checks passed
uv run pytest tests/unit/graphdb/test_resolve_access_matrix.py -v
# → 61 passed in 0.11s

# 3. Full unit suite gate (post-addition)
uv run pytest -q --ignore=tests/integration
# → 1020 passed, 6 skipped, 12 warnings in 13.15s

# 4. Integration suite — daemon absent
uv run pytest tests/integration -m integration -q
# → 20 passed, 19 skipped in 8.80s  (all indradb tests skip cleanly; no failures)
```

---

## Results

| Suite | Command | Passed | Skipped | Failed |
|---|---|---|---|---|
| Unit (pre-addition baseline) | `pytest -q --ignore=tests/integration` | 959 | 6 | 0 |
| QA addition only | `pytest tests/unit/graphdb/test_resolve_access_matrix.py -v` | 61 | 0 | 0 |
| Unit (post-addition) | `pytest -q --ignore=tests/integration` | 1020 | 6 | 0 |
| Integration (daemon absent) | `pytest tests/integration -m integration -q` | 20 | 19 | 0 |

---

## Traceability — SC-ID coverage

All scenario IDs from scenarios.md verified against the test files listed in developer logs (P1–P6).

| Scenario | Status | Test file(s) |
|---|---|---|
| S1-1-SC1 | covered | test_field_classification.py |
| S1-1-SC2 | covered | test_global_variable_classification.py |
| S1-1-SC2b | covered | test_global_variable_classification.py |
| S1-1-SC2c | covered | test_global_variable_classification.py |
| S1-1-SC3 | covered | test_field_classification.py |
| S1-1-SC4 | covered | test_describe_v1_compat.py |
| S1-1-SC5 | daemon-skip | test_v7_s1_field_vs_global_live.py (S1-1 AC5, S1-6 AC1) |
| S1-1-EC1 | needs-clarification (OQ-2 open); not blocked | design §3 D3 minimal note in test_field_classification.py |
| S1-2-SC1 | covered | test_member_of_access.py; test_resolve_access_matrix.py (QA) |
| S1-2-SC2 | covered | test_member_of_access.py; test_resolve_access_matrix.py (QA) |
| S1-2-SC3 | covered | test_member_of_access.py; test_resolve_access_matrix.py (QA) |
| S1-2-SC4 | daemon-skip | test_v7_s1_access_filter_live.py (S1-2 AC4) |
| S1-2-SC5 | covered | test_describe_v1_compat.py |
| S1-2-EC1 | covered | test_member_of_access.py; test_resolve_access_matrix.py (QA) |
| S1-2-EC2 | covered | test_member_of_access.py (method/ctor/dtor MEMBER_OF) |
| S1-2-EC3 | covered | test_member_of_access.py; test_resolve_access_matrix.py Part 5 (QA) |
| S1-3-SC1 | covered | test_variable_properties.py |
| S1-3-SC2 | covered | test_variable_properties.py |
| S1-3-SC3 | covered | test_variable_properties.py |
| S1-3-SC4 | covered | test_variable_properties.py |
| S1-3-SC5 | covered | test_variable_properties.py |
| S1-3-SC6 | covered | test_variable_properties.py |
| S1-3-SC7 | covered | test_variable_properties.py |
| S1-3-SC8 | covered | test_describe_v1_compat.py |
| S1-3-SC9 | qa-gate (inspection); all 4 properties covered both true/false values | test_variable_properties.py |
| S1-3-EC1 | covered | test_variable_properties.py (extern thread_local → thread_local) |
| S1-3-EC2 | covered | test_variable_properties.py (Field.storage_class == "none") |
| S1-3-EC3 | needs-clarification (OQ-6 open); not blocked | exporter silently re-classifies per D7 |
| S1-3-EC4 | covered | test_variable_properties.py |
| S1-4-SC1 | covered | test_schema_version_stamp.py; test_describe_v2_shape.py |
| S1-4-SC2 | covered | test_describe_v2_shape.py |
| S1-4-SC3 | covered | test_describe_v2_shape.py |
| S1-4-SC4 | covered | test_describe_v2_shape.py |
| S1-4-SC5 | covered | test_describe_v1_compat.py |
| S1-4-SC6 | covered | test_mcp_tool_signatures.py (snapshot test) |
| S1-4-EC1 | needs-clarification (OQ-7 open); not blocked | |
| S1-5-SC1 | covered (qa-gate) | 1020 passed / 6 skipped; 0 failures — S1-5 AC1 confirmed |
| S1-5-SC2..SC5 | covered (qa-gate) | test_field_classification.py, test_member_of_access.py, test_variable_properties.py |
| S1-5-SC6 | covered | test_round_trip.py |
| S1-6-SC1 | daemon-skip | test_v7_s1_field_vs_global_live.py |
| S1-6-SC2 | daemon-skip | test_v7_s1_access_filter_live.py |
| S1-6-SC3 | daemon-skip | full integration suite: 19 indradb tests skip cleanly; no regressions among 20 that run |

---

## Defects

- defect-id: QD-1
  scenario-id: S1-6-AC3 (pre-existing integration tests must continue to pass after S1)
  failing-command: >
    uv run pytest tests/integration/test_describe_graph_schema_e2e.py::test_ac_q3_2_vertex_type_counts_pinned
    -m integration -q
  exit-code: 1 (mechanical-certain when INDRADB_TEST_URI is present; skips here because daemon absent)
  description: >
    tests/integration/test_describe_graph_schema_e2e.py::test_ac_q3_2_vertex_type_counts_pinned
    (and test_ac_q3_2_vertex_type_sort_order_pinned) contain
    `_EXPECTED_NODE_COUNTS = {"Variable": 33, "TypeAlias": 28, "Function": 21, "Class": 13,
    "Namespace": 3, "File": 1}` and assert exact type-name set equality and per-type counts.
    After the S1 VAR_DECL → GlobalVariable / FIELD_DECL → Field split, the v2 exporter will
    emit "Field" and "GlobalVariable" nodes rather than "Variable" for data members and
    namespace-scope variables. PARM_DECL still emits Variable (ADR-25 D2) but the count will
    not be 33. The expected dict must be updated to use "Field", "GlobalVariable", and the
    revised counts; "Variable" remains only for PARM_DECL-sourced nodes (count TBD from a
    live run). Lines 37–44 and 248–255 of test_describe_graph_schema_e2e.py need updating.
    Evidence: lines 37–44 inspected; assertion logic at lines 148–162 and 248–263 inspected.
  status: resolved
  resolution: >
    tests/integration/test_describe_graph_schema_e2e.py rewritten (2026-05-17, QD-1 fix):
    _EXPECTED_NODE_COUNTS replaced with _EXPECTED_NODE_COUNTS_STABLE (TypeAlias/Function/
    Class/Namespace/File pinned) + _V2_SPLIT_TYPES structural invariants (Field+GlobalVariable
    +Variable present, sum==33, Variable<33). Sort-order test updated to assert stable suffix
    and that split types precede TypeAlias. 1020 unit tests pass; lint clean.

---

## Follow-ups (advisory — do NOT block dispatch)

- (a) _EXPECTED_NODE_COUNTS Variable:33 (QD-1 above) — defect, not advisory.
- (b) compile_commands.json path: test-repo/v7s1/compile_commands.json hard-codes
  /Users/husam/workspace/cpp-mcp as project root. If checked out elsewhere,
  resolve_flags falls back to default flags (graceful per compile_db.py). CI portability
  concern only; not a test correctness issue.

---

## Observations (advisory only — never blocks dispatch)

- OQ-2, OQ-3, OQ-5, OQ-6, OQ-7 remain open in scenarios.md. Relevant scenarios are tagged
  @needs-clarification; the associated SC-IDs are not covered by passing tests and are not
  expected to be per the scenarios themselves (deferred to architect/ADR-25 resolution).
- The exception-fallback branch (`except Exception: pass`) in `_resolve_access` catches all
  exceptions, including errors unrelated to ImportError (e.g., AttributeError on cursor).
  The QA boundary tests confirm this fallback is correct but the broad catch could mask future
  bugs in AccessSpecifier comparison logic. Advisory: narrow to `except ImportError` with a
  secondary `except (TypeError, AttributeError)` for the spec comparison.
- The `_MEMBER_PARENT_KINDS` frozenset does not include UNION_DECL, so union members never
  emit MEMBER_OF edges. Implementation-notes.md documents this as a follow-up. No test
  currently asserts the absence of union MEMBER_OF edges end-to-end (only `_resolve_access`
  direct unit test). Advisory for S2+ scope.

---

## Additions made

Category: mutation/boundary (role category 3).

New file: tests/unit/graphdb/test_resolve_access_matrix.py
61 parametrized tests across 5 test classes covering:
  - Full AccessSpecifier x parent_kind matrix (12 explicit-spec cases x 4 parent kinds = 12 + 12 + 12 = 36 cases via parametrize)
  - {INVALID, NONE} x {CLASS_DECL, STRUCT_DECL, CLASS_TEMPLATE, UNION_DECL} = 8 default-resolution cases
  - Boundary: parent_kind=None and unknown-kind string (6 cases)
  - Exception-fallback branch: 4 + 1 cases (all parent_kinds + allowed-set loop)
  - Exhaustive S1-2 EC3 negative bound: 5 spec_attrs x 6 parent_kinds = 30 combinations

Gaps filled versus developer tests: CLASS_TEMPLATE parent (not tested in test_member_of_access.py),
parent_kind=None boundary, unknown-kind boundary, exception-fallback branch (except Exception: pass),
and the explicit-PRIVATE x STRUCT_DECL / UNION_DECL cross (mutation that would return 'public').

---

## References

- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/scenarios.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/implementation-notes.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/plan.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/logs/developer-p1-schema-constants.md through developer-p6-live-indradb.md
- Cognee tags: task:cpp-mcp-v7-s1, role:qa-engineer
