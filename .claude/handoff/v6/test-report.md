Scope: v6 Graph Query Surface (query_graphdb + describe_graph_schema, S1–S6)
Test plan: unit | integration | BDD/E2E | regression
Run: cpp-mcp-v6
Date: 2026-05-17

---

## Commands run

```bash
# Full lint (project-wide — confirms defects)
uv run ruff check src/ tests/unit/ tests/bdd/test_query_graphdb_bdd.py

# Type check
uv run mypy

# BDD step-def additions (proper pytest-bdd with .feature file, no live daemon)
uv run pytest tests/bdd/test_query_graphdb_bdd.py -q

# Full unit + BDD suite (post-addition)
uv run pytest -q --ignore=tests/integration

# Story-level exit-gate tests (S1)
uv run pytest tests/unit/core/test_query_error_codes.py tests/unit/graphdb/test_schema_version_stamp.py -q

# Story-level exit-gate tests (S2)
uv run pytest tests/unit/graphdb/test_indradb_query_subset.py tests/unit/graphdb/test_query_executor_purity.py tests/unit/graphdb/test_query_executor_dispatch.py tests/unit/tools/test_query_graphdb.py tests/unit/core/test_query_config.py tests/unit/test_tool_registration.py -q

# Story-level exit-gate tests (S3)
uv run pytest tests/unit/graphdb/test_neo4j_read_only.py tests/unit/graphdb/test_neo4j_query_executor.py tests/unit/tools/test_query_graphdb.py -q

# Story-level exit-gate tests (S4)
uv run pytest tests/unit/graphdb/test_schema_introspector.py tests/unit/tools/test_describe_graph_schema.py tests/unit/test_tool_registration.py -q

# Integration tests (IndraDB live daemon — developer-run, QA-verified from log)
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m "integration and indradb" tests/integration/test_query_graphdb_e2e.py tests/integration/test_describe_graph_schema_e2e.py -q
```

---

## Results

| Suite | Outcome | Count |
|---|---|---|
| `uv run mypy` | PASS | 38 source files, 0 issues |
| `uv run ruff check src/ tests/unit/` | **FAIL** | 3 errors (QD-1, QD-2, QD-3 — see defects) |
| `uv run ruff check tests/bdd/test_query_graphdb_bdd.py` | PASS | All checks passed |
| `uv run pytest tests/bdd/test_query_graphdb_bdd.py -q` | PASS | 13 passed |
| `uv run pytest -q --ignore=tests/integration` | PASS | 880 passed, 6 skipped |
| IndraDB integration (developer-run; QA-verified from developer log) | PASS | 10 passed |

---

## Defects

- defect-id: QD-1
  scenario-id: AC-Q1-9, AC-Q1-10, AC-Q2-8 (tool registration invariants — all scenarios depend on correct import)
  failing-command: uv run ruff check src/cpp_mcp/server/app.py
  exit-code: 1
  description: >
    `src/cpp_mcp/server/app.py` line 79 — ruff I001 "Import block is un-sorted or un-formatted".
    The `from cpp_mcp.tools import describe_graph_schema` import on line 89 is a separate
    statement outside the block on lines 79–88; ruff requires them merged into one sorted block.
    S4 developer scoped ruff to individual files and did not include app.py — the per-story
    scoped ruff check passed, but project-wide ruff exposes the failure.
    QA cannot fix production code per role boundary — filed for developer retry.
  status: resolved

- defect-id: QD-2
  scenario-id: AC-Q1-9, AC-Q1-10 (tool registration infrastructure; all scenarios transitively)
  failing-command: uv run ruff check src/cpp_mcp/graphdb/neo4j_driver.py
  exit-code: 1
  description: >
    `src/cpp_mcp/graphdb/neo4j_driver.py` line 51 — ruff RUF100 "Unused `noqa` directive
    (non-enabled: `PLC0415`)". The `# noqa: PLC0415` comment on the lazy `import neo4j` line
    suppresses a pylint rule that is not in this project's ruff ruleset (E,F,I,UP,B,SIM,RUF).
    Developer must remove the noqa comment or add PLC to the ruleset. QA cannot fix per role boundary.
  status: resolved

- defect-id: QD-3
  scenario-id: AC-Q1-9, AC-Q1-10, AC-Q2-8 (rename invariant / tool count test)
  failing-command: uv run ruff check tests/unit/test_rename_invariant.py
  exit-code: 1
  description: >
    `tests/unit/test_rename_invariant.py` line 111 — ruff E501 line too long (108 > 100).
    The docstring "EC-2: Registry exposes exactly 9 tools (v5 base 7 + v6 query_graphdb +
    describe_graph_schema)." exceeds the 100-char line limit in pyproject.toml.
    Developer-authored test file; QA may not modify per role boundary.
  status: resolved

---

## Scenario-to-test traceability

| Scenario ID | Test file | Test name(s) |
|---|---|---|
| AC-Q1-7 (error codes) | tests/unit/core/test_query_error_codes.py | TestNewErrorCodesPresent, TestExcToCodeMapping |
| AC-Q1-1/schema_version stamp | tests/unit/graphdb/test_schema_version_stamp.py | all |
| AC-Q1-1 (row_limit clamp) | tests/unit/tools/test_query_graphdb.py | TestRowLimitClamp::* |
| AC-Q1-1/Q1-6 (row_limit default 200) | tests/bdd/test_query_graphdb_bdd.py | test_row_limit_defaults_to_200_and_result_under_cap__truncated_false |
| AC-Q1-6 (truncated=true over cap) | tests/bdd/test_query_graphdb_bdd.py | test_result_exceeds_row_limit__rows_capped_truncated_true_no_error_raised |
| AC-Q1-6 (truncated=false at cap) | tests/bdd/test_query_graphdb_bdd.py | test_result_count_equals_row_limit_exactly__truncated_false |
| AC-Q1-6 (truncated flag) | tests/unit/graphdb/test_indradb_query_subset.py | test_truncated_flag_set_on_execute, test_not_truncated_when_all_fit |
| AC-Q1-2 (IndraDB row coercion) | tests/unit/graphdb/test_indradb_query_subset.py | TestAllowedVerbs::* |
| AC-Q1-2 (Neo4j row coercion) | tests/unit/graphdb/test_neo4j_query_executor.py | TestRowCoercion::* |
| AC-Q1-3 (Neo4j EXPLAIN allow/reject) | tests/unit/graphdb/test_neo4j_read_only.py | TestWalkPlanAllowed::*, TestWalkPlanRejected::*, TestEnforceReadOnly::* |
| AC-Q1-4 (IndraDB purity) | tests/unit/graphdb/test_query_executor_purity.py | all |
| AC-Q1-4 (IndraDB purity BDD) | tests/bdd/test_query_graphdb_bdd.py | test_indradb_executor_module_exports_no_write_symbols |
| AC-Q1-5 (7 verbs) | tests/unit/graphdb/test_indradb_query_subset.py | TestAllowedVerbs::* |
| AC-Q1-5 (QUERY_UNSUPPORTED BDD) | tests/bdd/test_query_graphdb_bdd.py | test_indradb_query_type_outside_the_supported_subset_returns_query_unsupported |
| AC-Q1-5/OQ-Q1-2 (Cypher→IndraDB PARSE_ERROR) | tests/bdd/test_query_graphdb_bdd.py | test_cypher_shaped_string_sent_to_indradb_uri_returns_query_parse_error |
| AC-Q1-5 arg validation | tests/unit/graphdb/test_indradb_query_subset.py | TestArgValidation::*, TestBadTypeIdentifier::*, TestBadUuid::* |
| AC-Q1-7 (QUERY_PARSE_ERROR BDD) | tests/bdd/test_query_graphdb_bdd.py | test_malformed_indradb_json_query_returns_query_parse_error |
| AC-Q1-7 (QUERY_TIMEOUT) | tests/unit/tools/test_query_graphdb.py | TestQueryTimeout::* |
| AC-Q1-7 (DB_UNREACHABLE) | tests/unit/tools/test_query_graphdb.py | TestDbUnreachable::* |
| AC-Q1-7 (DEPENDENCY_MISSING) | tests/unit/tools/test_query_graphdb.py | TestDependencyMissing::* |
| AC-Q1-8 (timeout resolver) | tests/unit/core/test_query_config.py | all |
| AC-Q1-8 (clamp low BDD) | tests/bdd/test_query_graphdb_bdd.py | test_cpp_mcp_query_timeout_seconds_below_1_is_clamped_to_1 |
| AC-Q1-8 (clamp high BDD) | tests/bdd/test_query_graphdb_bdd.py | test_cpp_mcp_query_timeout_seconds_above_120_is_clamped_to_120 |
| AC-Q1-8 (default BDD) | tests/bdd/test_query_graphdb_bdd.py | test_cpp_mcp_query_timeout_seconds_default_when_unset_is_30 |
| AC-Q1-9/Q1-10/Q2-8 | tests/unit/test_tool_registration.py | all |
| AC-Q1-9/Q1-10 (9 tools BDD) | tests/bdd/test_query_graphdb_bdd.py | test_server_registers_exactly_9_tools_including_query_graphdb_and_describe_graph_schema |
| AC-Q1-10 (no cpp_ prefix BDD) | tests/bdd/test_query_graphdb_bdd.py | test_no_registered_tool_name_starts_with_cpp_ |
| AC-Q2-1 (sample_size clamp) | tests/unit/tools/test_describe_graph_schema.py | TestSampleSizeClamping::* |
| AC-Q2-2 (schema_version field) | tests/unit/tools/test_describe_graph_schema.py | TestSchemaVersionField::* |
| AC-Q2-5 (ordering count desc) | tests/unit/graphdb/test_schema_introspector.py | TestOrdering::* |
| AC-Q2-6 (db_uri non-echo) | tests/unit/tools/test_describe_graph_schema.py | TestDbUriNonEcho::* |
| AC-Q2-7 (empty graph) | tests/unit/graphdb/test_schema_introspector.py | TestEmptyGraph::* |
| AC-Q2-8 (describe registered) | tests/bdd/test_query_graphdb_bdd.py | test_server_registers_exactly_9_tools_including_query_graphdb_and_describe_graph_schema |
| OQ-Q2-1 (version mismatch note) | tests/bdd/test_query_graphdb_bdd.py | test_schema_version_mismatch_between_writer_schema_and_live_graph_surfaces_a_warning_note |
| AC-Q3-1..Q3-4 (IndraDB live) | tests/integration/test_query_graphdb_e2e.py, tests/integration/test_describe_graph_schema_e2e.py | all (10 tests, developer-run) |

---

## observations

- Integration test runtime ~415s (~7 min) vs plan.md S5 "60s combined". Each e2e test independently
  calls `ingest_code` without fixture sharing. Tests are correct; runtime is a performance smell.
  Advisory: introduce a session-scoped `ingested_db` fixture to amortize ingest time across tests.
- Developer per-story scoped ruff checks did not catch QD-1 (app.py) and QD-2 (neo4j_driver.py)
  because those files were excluded from per-story file lists. Recommend senior-developer add
  `uv run ruff check src/` (project-wide) to the global exit gate in addition to per-story scoped checks.
- mypy clean (0 issues, 38 files, --strict mode). Full type coverage is a positive signal.
- QD-3 (test_rename_invariant.py E501) is low severity but ruff exits non-zero, which blocks CI.

---

## Additions made

BDD step-def — new feature file `tests/bdd/features/query_graphdb.feature` (13 Gherkin scenarios
with @tag annotations matching scenario IDs from scenarios.md) + rewritten step-definition module
`tests/bdd/test_query_graphdb_bdd.py` using `from pytest_bdd import given, when, then, scenarios`
with `scenarios("features/query_graphdb.feature")` binding. Covers:

- AC-Q1-1/Q1-6: row_limit default 200 / truncated=false at cap / truncated=true over cap (3 scenarios)
- AC-Q1-5/OQ-Q1-2: Cypher to IndraDB URI → QUERY_PARSE_ERROR (1 scenario)
- AC-Q1-5: unsupported IndraDB verb → QUERY_UNSUPPORTED (1 scenario)
- AC-Q1-7: malformed JSON → QUERY_PARSE_ERROR (1 scenario)
- AC-Q1-8: timeout clamp low / high / default (3 scenarios)
- AC-Q1-4: IndraDB executor purity — no set_/delete_ symbols (1 scenario)
- AC-Q1-9/Q1-10/AC-Q2-8: 9 tools registered, no cpp_ prefix (2 scenarios)
- OQ-Q2-1: schema-version mismatch note in describe_graph_schema output (1 scenario)

---

## References

- scenarios.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/scenarios.md
- implementation-notes: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/logs/developer.md
- developer story logs: developer-s2-query-indradb.md, developer-s3-neo4j-executor.md,
  developer-s4-describe-schema.md, developer-s6-release.md
- Cognee tags: task:cpp-mcp-v6, role:qa-engineer
