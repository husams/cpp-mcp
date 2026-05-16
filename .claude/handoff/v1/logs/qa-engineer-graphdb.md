run_id: cpp-mcp-1
story: graphdb-exporter (Story 8 / US-7)
date: 2026-05-16
role: qa-engineer
qa-model: claude-sonnet-4-6

## Skills loaded

- `python-conventions` — loaded to confirm test runner (uv run pytest), marker patterns,
  parametrize conventions, and ruff/mypy gate commands.

## Orientation phase

Files read:
  - CHARTER.md
  - scenarios.md (SC-US-7-* section)
  - logs/developer-graphdb-exporter.md
  - src/cpp_mcp/graphdb/schema.py
  - src/cpp_mcp/graphdb/driver.py
  - src/cpp_mcp/graphdb/exporter.py
  - src/cpp_mcp/graphdb/neo4j_driver.py
  - src/cpp_mcp/tools/export_to_graphdb.py
  - tests/unit/test_graphdb_exporter.py (developer)
  - tests/bdd/test_export_to_graphdb.py (developer)
  - tests/bdd/features/export_to_graphdb.feature (developer)
  - tests/bdd/conftest.py
  - pyproject.toml

## Pre-existing test run (developer tests only)

  uv run pytest tests/unit/test_graphdb_exporter.py -v
  → 19 passed in 0.05s

  uv run pytest tests/bdd/test_export_to_graphdb.py -v
  → 11 passed in 0.26s

  uv run pytest tests/ -q (full suite, excluding new additions)
  → 157 passed in 1.32s

All developer tests passed before QA additions were written.

## Coverage gaps identified

1. REFERENCES edge type in ALL_EDGE_TYPES but no cursor kind emits it — advisory
   observation, not a defect (AC only requires the type appear in the schema set).
2. Idempotency of the full upsert pipeline (running export twice) was not exercised
   by developer tests — the FakeGraphDriver accumulates, it does not MERGE.
3. DB_UNREACHABLE only tested via mock (patch Neo4jDriver) — no real network path
   exercised; the Neo4jDriver.connect() lazy-import + verify_connectivity() branch
   was untouched by developer tests.
4. All 7 node labels and all 7 edge types were not individually parametrized — only
   one functional subpath (FUNCTION_DECL) was exercised.
5. @pytest.mark.neo4j was registered in pyproject.toml but no test exercised the
   skip path.

## QA additions written

File: tests/unit/test_graphdb_additions.py

Category 1 — Parametrized boundary (14 parametrized tests):
  - test_schema_node_label_in_all_node_types[File|Namespace|Class|Function|Variable|Macro|TypeAlias]
  - test_schema_edge_type_in_all_edge_types[DEFINES|DECLARES|CALLS|INHERITS|REFERENCES|INCLUDES|MEMBER_OF]
  - test_all_node_types_exactly_7
  - test_all_edge_types_exactly_7
  - test_node_record_accepts_every_label
  - test_edge_record_accepts_every_edge_type

Category 2 — In-memory MERGE-idempotency driver (5 tests):
  - test_idempotent_upsert_nodes_same_batch_twice
  - test_idempotent_upsert_edges_same_batch_twice
  - test_idempotent_full_export_twice (end-to-end extract → upsert twice)
  - test_idempotent_driver_empty_node_batch
  - test_idempotent_driver_empty_edge_batch
  - test_idempotent_driver_overlapping_batches

Category 3 — Mutation/boundary (real network + skip guard):
  - test_db_unreachable_closed_port (real refused TCP, no mocks)
  - test_neo4j_marker_skips_when_uri_absent (@neo4j skip infrastructure)
  - test_neo4j_marker_registered_in_config (no PytestUnknownMarkWarning)

## Commands run

  uv run pytest tests/unit/test_graphdb_additions.py -v
  → 26 passed, 1 skipped in 0.53s

  uv run pytest tests/unit/test_graphdb_exporter.py tests/unit/test_graphdb_additions.py tests/bdd/test_export_to_graphdb.py -v
  → 56 passed, 1 skipped in 0.57s

  uv run pytest tests/ -q
  → 213 passed, 1 skipped in 1.68s

## Defects

None. All scenarios pass. No open QA_DEFECT signals.

## Observations (advisory)

- REFERENCES edge type is defined in schema.py but _walk_cursor never emits it
  for any CursorKind — future developer story should implement or remove.
- FakeGraphDriver is duplicated between test_graphdb_exporter.py and
  test_export_to_graphdb.py — extract to shared fixture module to reduce drift.

## Gate status

I4 satisfied: test-report.md written with no open defects.
→ Ready for devops dispatch.
