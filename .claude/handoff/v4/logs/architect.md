# architect log — cpp-mcp-v4

Date: 2026-05-17
Inputs read: CHARTER.md, requirements.md, scenarios.md, src/cpp_mcp/graphdb/{driver.py,indradb_driver.py,neo4j_driver.py,exporter.py,__init__.py}, src/cpp_mcp/tools/export_to_graphdb.py, src/cpp_mcp/server/app.py, tests/fixtures/indradb-compose.yml, pyproject.toml.

## Deliverables

- design.md
- adr-16.md (cargo-install for local IndraDB; resolves OQ-6-1)
- adr-17.md (insert-vs-attempt counting; tightens Protocol contract; covers Neo4j fix too)
- adr-18.md (in-process fastmcp.Client harness; session-scoped fixture)

All three ADRs are `Status: accepted`.

## Key design findings

1. **Neo4j driver has the same attempt-vs-insert bug as IndraDB** — `RETURN n` after MERGE returns 1 row whether the node was created or matched. Fix is in scope for US-V4-3 via `ResultSummary.counters.nodes_created` / `relationships_created`. Code-review only per AC-3-3 (no live Neo4j daemon).

2. **GraphDriver Protocol docstring is ambiguous** ("created or updated"); tightened in ADR-17 to "created only" so idempotent re-export naturally returns 0.

3. **Existing v3 BDD tests will break** — `SC_US_G5_1`, `SC_US_G5_2` and `tests/fixtures/fake_indradb.py` assume `len(batch)` semantics. Listed in design §5 failure modes; developer plan must include update.

4. **DEPENDENCY_MISSING error string needs wording update** — current message says `pip install "cpp-mcp[graphdb-indradb]"`, but SC-V4-7-02 asserts literal `--extra graphdb-indradb`. Updated wording proposed in design §3.7.

5. **`memory` daemon subcommand chosen** (not `rocksdb`) — RAM-only, fresh on each fixture setup, no volume cleanup; matches `cargo install indradb` default.

## Open items handed to senior-developer

- Implement per-record `get(SpecificVertexQuery(vid))` pre-check in IndraDB driver.
- Refactor Neo4j driver to `result.consume().counters`.
- Extend exporter return dict + tool docstring with `nodes_attempted` / `edges_attempted`.
- Update `tests/fixtures/fake_indradb.py` to also return insert counts.
- Delete `tests/fixtures/indradb-compose.yml`.
- Add `addopts = "-ra -m 'not integration'"` to pyproject and register `integration` marker.
- All test files listed in design §3.1.
