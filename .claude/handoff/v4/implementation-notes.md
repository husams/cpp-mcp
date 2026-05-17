---
task: cpp-mcp-v4
story: S1 commit-identifier-to-str-driver-patch
role: developer
date: 2026-05-17
---

# Implementation Notes — S1

## Files changed

- `src/cpp_mcp/graphdb/indradb_driver.py` — 2 call sites Identifier→str; docstring cleaned; type:ignore updated
- `tests/fixtures/fake_indradb.py` — `_type_name()` compat shim; Vertex/Edge hash/eq updated
- `tests/unit/test_indradb_driver.py` — `test_label_stored_as_vertex_type` assertion updated
- `tests/bdd/test_export_to_indradb.py` — `then_file_node_type` step updated
- `tests/unit/test_indradb_driver_no_identifier.py` — new structural grep test (AC-5-1, AC-5-2)

## Tests added/run

```
uv run pytest tests/unit/test_indradb_driver_no_identifier.py -q   → 2 passed
uv run pytest -q                                                    → 592 passed, 6 skipped
```

## Deviations from plan

Plan §S1 files-to-touch listed only `indradb_driver.py` + new grep test. Three additional files were required because the fake_indradb fixture used `t.name` (Identifier attribute) in hash/eq/set_properties, and one unit test + one BDD step asserted `vertex.t.name`. All fixes are minimal compat changes, not scope expansion.

The `type: ignore` comment in `indradb_driver.py` was changed from `import-not-found` to `import-untyped` because `indradb` is installed in the dev venv (after `uv sync --all-extras`), causing mypy to resolve the import but report missing stubs.

## Follow-ups

- `@sr-dev` — Update plan §S1 file list to include fake_indradb and BDD step for S3 author's reference.
- `@sr-dev` — S3 fake_indradb edits (insert-count tracking) should read the `_type_name` shim before adding logic.
- `@qa` — `uv sync --all-extras` required before running suite; otherwise `uv run pytest` resolves to Homebrew Python 3.13 which lacks cpp_mcp.

## References

- plan.md §S1
- scenarios.md SC-V4-5-01
- design.md (ADR-17 driver contract)
- `[[project-graphdb-v3-post-ship-findings]]` defect 2

---

# Implementation Notes — S2

## Files changed

- `pyproject.toml` — `graphdb-indradb` extra extended to `["indradb>=3.0,<4", "protobuf<4"]`
- `uv.lock` — regenerated; protobuf downgraded from v7.34.1 to v3.20.3
- `tests/integration/__init__.py` — created (empty package marker)
- `tests/integration/test_install.py` — two `@pytest.mark.integration` import-smoke tests
- `tests/unit/test_pyproject_extras.py` — `test_indradb_pin` assertion updated to expect the two-entry list

## Tests added/run

```
uv run pytest -m integration tests/integration/test_install.py -q   → 2 passed
uv run pytest -q                                                      → 594 passed, 6 skipped
```

## Deviations from plan

- `tests/unit/test_pyproject_extras.py` not listed in plan §S2 files-to-touch, but required updating: the pre-existing `test_indradb_pin` asserted the single-entry list and would have broken the default suite. Updated assertion to match the new two-entry form.

## Follow-ups

- `integration` marker `PytestUnknownMarkWarning` resolves in S5 when pyproject.toml registers the marker.
- S5 also edits `pyproject.toml` — diff here is minimal (one extra entry in `graphdb-indradb`).

## References

- plan.md §S2 lines 74-101
- ADR-18 §5 (protobuf<4 pin decision)

---

# Implementation Notes — S3

## Files changed

- `src/cpp_mcp/graphdb/driver.py` — tightened `upsert_nodes`/`upsert_edges` Protocol docstrings to "inserts only" (ADR-17)
- `src/cpp_mcp/graphdb/indradb_driver.py` — module docstring cleaned (Identifier→str references removed; S1 cross-story); per-record `get(SpecificVertexQuery)` / `get(SpecificEdgeQuery)` pre-check; returns insert count (not `len(batch)`)
- `src/cpp_mcp/graphdb/neo4j_driver.py` — dropped `RETURN n` / `RETURN r`; switched to `result.consume().counters.nodes_created` / `relationships_created` (ADR-17)
- `src/cpp_mcp/graphdb/exporter.py` — `export_file()` extended return dict with `nodes_attempted` / `edges_attempted`; debug log now shows insert/attempt ratios
- `src/cpp_mcp/tools/export_to_graphdb.py` — added `total_nodes_attempted` / `total_edges_attempted` accumulators; all four fields in response dict; docstrings updated
- `tests/fixtures/fake_indradb.py` — added `Client.get(query)` returning `[]` or `[vertex/edge]`; ruff auto-fixed quoted type annotations (UP037)
- `tests/bdd/test_export_to_indradb.py` — `then_live_node_count_stable` updated: asserts `nodes_written == 0` on re-export (insert semantics); old step compared run2 to run1 which would now fail under ADR-17
- `tests/unit/test_pyproject_extras.py` — split long assertion line to fix E501 (pre-existing lint issue surfaced by ruff run on tests/unit/)
- `tests/unit/test_indradb_driver_insert_counts.py` — **new**: 9 tests + 1 parametrized; context-manager based fake to keep sys.modules consistent across lazy re-imports

## Tests added/run

```
uv run ruff format --check src/ tests/unit tests/bdd tests/fixtures  → 0
uv run ruff check src/ tests/unit tests/bdd tests/fixtures            → 0
uv run mypy src/                                                       → 0 (no issues, 30 files)
uv run pytest tests/unit -q                                           → 502 passed, 4 skipped
uv run pytest tests/bdd -q                                            → 99 passed, 2 skipped
uv run pytest -q                                                      → 603 passed, 6 skipped
test -f .claude/handoff/v4/logs/developer-us-v4-3.md                  → 0 (file present)
```

## Deviations from plan

1. **S1 working-tree change included in S3**: `indradb_driver.py` module docstring cleaned (Identifier→str references) since the file was already being edited for S3; avoids merge conflict when S1 lands. Cross-story bleed documented in references.
2. **`tests/unit/test_pyproject_extras.py` touched**: E501 fix surfaced by ruff during exit-gate run. Not in S3 scope but required for lint gate to pass cleanly.
3. **`_connected_driver()` helper replaced with `_fake_indradb_context()`**: Initial helper removed `indradb` from `sys.modules` before upsert methods ran, causing lazy `import indradb` inside those methods to resolve to real package. Context manager keeps fake in `sys.modules` for driver lifetime.

## Follow-ups

- S1 `test_indradb_driver_no_identifier.py` can land cleanly (S3 already cleaned the docstring).
- Feature file `export_to_indradb.feature` wording "equals the recorded count" is now semantically stale (step now asserts 0). Update wording in a later story.
- Neo4j live daemon test deferred to v5 per ADR-17 §Follow-ups.

## References

- plan.md §S3 lines 105-137
- design.md §3.3
- adr-17.md (entire decision)
- scenarios.md SC-V4-3-01/02, SC-V4-2-04
- .claude/handoff/v4/logs/developer-us-v4-3.md (Neo4j code-review finding per AC-3-3)

---

# Implementation Notes — S4

## Files changed

- `tests/fixtures/indradb-compose.yml` — **deleted** (broken Docker image `indradb/indradb:5.0.0`, ADR-16)
- `tests/unit/test_no_broken_docker_image.py` — **new** repo-grep test (AC-6-1)
- `README.md` — added `## Local development (IndraDB)` subsection; replaced `docker compose` line in `### IndraDB` backend block with `indradb-server memory`
- `.claude/handoff/v3/runbook.md` — replaced Docker-based IndraDB daemon section with cargo-install path

## Tests added/run

```
uv run ruff format --check tests/unit/test_no_broken_docker_image.py   → 0
uv run ruff check tests/unit/test_no_broken_docker_image.py            → 0
uv run pytest tests/unit/test_no_broken_docker_image.py -q             → 1 passed
grep -q 'cargo install indradb' README.md                              → 0
grep -q 'cargo install indradb' .claude/handoff/v3/runbook.md          → 0
uv run pytest -q                                                        → 602 passed, 6 skipped
```

## Deviations from plan

1. **Exit criterion `! grep -rn 'indradb/indradb:5.0.0' . --exclude-dir=.git --exclude-dir=.venv` is over-scoped.**
   The `.claude/handoff/` directory contains planning/ADR/requirements/scenarios files that legitimately name the broken image as the problem being fixed (adr-16.md, requirements.md, scenarios.md, plan.md, v3/plan.md, etc.). These are documentation, not broken fixture code.
   - **Resolution:** the unit test excludes `.claude`, `__pycache__`, and restricts to text extensions (`*.py`, `*.yml`, `*.md`, `*.toml`, `*.txt`). This matches design §233 intent.
   - **Tag for sr-dev:** amend plan §S4 line 162 to add `--exclude-dir=.claude`.

2. **README `### IndraDB` block also updated** (not only the new `## Local development (IndraDB)` subsection). The existing block contained a hard reference to the deleted compose file. Fix was one line: `docker compose ... up -d` → `indradb-server memory`. S7 developer: this is in `## Graph database backends`, not `## Install` — no conflict expected.

## Follow-ups

- `@sr-dev` — Amend plan §S4 exit criterion line 162 to add `--exclude-dir=.claude`.
- `@S7` — The `## Graph database backends` → `### IndraDB` block was updated here; S7's scope is `## Install` + driver wording — no conflict, but note the region.
- `@v5` — CI story: package `indradb-server` binary in runner image or add `cargo install indradb` step (ADR-16 §Follow-ups).

## References

- plan.md §S4 lines 141-169
- adr-16.md
- scenarios.md SC-V4-6-01, SC-V4-6-02

---

# Implementation Notes — S5

## Files changed

- `tests/conftest.py` — added `pytest_asyncio` import; added session-scoped `mcp_client` fixture (`@pytest_asyncio.fixture(scope="session", loop_scope="session")`) using in-process `fastmcp.Client(build_server())`; sets/restores `CPP_MCP_ALLOWED_ROOTS` env var inside fixture body
- `pyproject.toml` — registered `integration` marker; changed `addopts` from `-ra` to `-ra -m 'not integration'`; added `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"`
- `tests/integration/conftest.py` — new placeholder (daemon fixtures arrive in S6)
- `tests/integration/test_harness_smoke.py` — new; SC-V4-1-01 (fixture connectivity), SC-V4-1-02 (cache_hit toggle on fmt-c.cc)
- `tests/integration/test_all_tools_smoke.py` — new; SC-V4-1-03 (parametrised, all 7 tools on os.cc)

## Tests added/run

```
uv run ruff format --check tests/conftest.py tests/integration pyproject.toml  → 6 files already formatted (exit 0)
uv run ruff check tests/conftest.py tests/integration                          → All checks passed (exit 0)
uv run mypy src/                                                                → Success: no issues found in 30 source files (exit 0)
uv run pytest -q                                                                → 602 passed, 6 skipped, 11 deselected (exit 0)
uv run pytest -m integration tests/integration/test_harness_smoke.py tests/integration/test_all_tools_smoke.py -q → 9 passed in 3.41s (exit 0)
uv run pytest --collect-only -m integration -q | grep -E 'test_harness_smoke|test_all_tools_smoke' → 9 items (exit 0)
```

## Deviations from plan

1. **`asyncio_default_test_loop_scope = "session"` added to pyproject.toml** — plan §S5 only mentioned the fixture scope and the `integration` marker addopts change. The pytest-asyncio 1.3.0 default is `asyncio_default_test_loop_scope=function`, which creates a separate event loop per test. The session-scoped `mcp_client` fixture's FastMCP Client object is bound to the session event loop. When a function-scoped test does `await mcp_client.call_tool(...)`, the awaitable crosses event loop boundaries → deadlock. Setting `asyncio_default_test_loop_scope = "session"` makes all async tests share the session event loop, matching the fixture. Verified: all 602 existing tests continue to pass.

2. **`loop_scope="session"` on `@pytest_asyncio.fixture`** — required alongside the pyproject setting for pytest-asyncio 1.3.0 (belt-and-suspenders). Not mentioned in plan or design.

3. **`CPP_MCP_ALLOWED_ROOTS` managed inside fixture** — design §3.1 omits this. The lifespan's `load_config()` raises `ConfigError: CPP_MCP_ALLOWED_ROOTS is required` if the env var is absent. Since `monkeypatch` is function-scoped (cannot be used in session fixtures), the fixture manually saves/restores the env var in a try/finally block.

4. **fmt-c.cc used for cache-hit toggle, os.cc for all-tools smoke** — design §3.1 uses `os.cc` generically for all tests. With session state, the parametrised all-tools smoke warms the `cpp_get_ast` cache for `os.cc`. The cache-hit toggle test (SC-V4-1-02) must start with a cold cache; using `fmt-c.cc` (a different file) achieves this regardless of collection order.

5. **`cpp_export_to_graphdb` asserts `code in {"DB_UNREACHABLE", "DEPENDENCY_MISSING"}`** — plan text said "DB_UNREACHABLE / DEPENDENCY_MISSING". Verified: current env returns `DEPENDENCY_MISSING` (neo4j extra absent). Set membership assertion stays correct regardless of which extra is installed at test time.

## Follow-ups

- `@sr-dev`: `asyncio_default_test_loop_scope = "session"` is now a project-wide setting. Any future test that requires per-test asyncio isolation (e.g. task cancellation state) must use `@pytest.mark.asyncio(loop_scope="function")` explicitly. Document in test-conventions or ADR-18 addendum.
- S6 will add `indradb_uri`, `indradb_daemon`, `fresh_indradb` fixtures to `tests/integration/conftest.py`.

## References

- plan.md §S5 lines 173-200
- design.md §3.1
- adr-18.md
- scenarios.md SC-V4-1-01..SC-V4-1-03

---

# Implementation Notes — S7

## Files changed

- `src/cpp_mcp/graphdb/indradb_driver.py` — DependencyMissingError message now includes `uv sync --extra graphdb-indradb` (pip install form retained for backwards compat with existing tests)
- `src/cpp_mcp/graphdb/neo4j_driver.py` — DependencyMissingError message now includes `uv sync --extra graphdb-neo4j` (pip install form retained)
- `README.md` — `## Install` section now explicitly enumerates `--extra graphdb-neo4j`, `--extra graphdb-indradb`, and `--extra graphdb` with separate `uv sync` examples
- `tests/integration/test_readme_extras.py` — **new**; SC-V4-7-01 (README extras) + SC-V4-7-02 (driver error wording); 5 tests, all pass

## Tests added/run

```
uv run ruff format --check src/cpp_mcp/graphdb/indradb_driver.py src/cpp_mcp/graphdb/neo4j_driver.py tests/integration/test_readme_extras.py
# → 3 files already formatted (exit 0)

uv run ruff check src/cpp_mcp/graphdb/indradb_driver.py src/cpp_mcp/graphdb/neo4j_driver.py tests/integration/test_readme_extras.py
# → All checks passed! (exit 0)

uv run mypy src/
# → Success: no issues found in 30 source files (exit 0)

uv run pytest -m integration tests/integration/test_readme_extras.py -q
# → 5 passed in 0.08s (exit 0)

uv run pytest -q
# → 602 passed, 6 skipped, 18 deselected (exit 0)
```

## Deviations from plan

- Driver messages keep the `pip install` form alongside the new `uv sync --extra` form. Pre-existing tests (`test_dependency_missing.py:154`, `test_indradb_driver.py:193`) assert `match="pip install"`. Dropping pip install would cause TEST_FAIL; keeping both satisfies AC-7-2 and all existing assertions.

## Follow-ups

- None for S7. S4 already landed `## Local development (IndraDB)` and `## Graph database backends` sections in README — no overlap introduced.

## References

- plan.md §S7 lines 235-265
- scenarios.md SC-V4-7-01/02
- .claude/handoff/v4/logs/developer-us-v4-7.md

---

# Implementation Notes — v4-followups

## Files changed

- `.claude/handoff/v4/adr-18.md` — addendum appended: `asyncio_default_test_loop_scope=session` is project-wide; per-function isolation requires `@pytest.mark.asyncio(loop_scope="function")`
- `.claude/handoff/v4/adr-17.md` — Known-gap addendum (v4) appended: ~23K dropped edge attempts are expected; post-create verify doubles RPCs; deferred to v5 for bulk pre-fetch optimization
- `src/cpp_mcp/graphdb/indradb_driver.py` — ruff format applied (pre-existing trailing whitespace; no logic change)

## Tests added/run

```
uv run ruff format --check .                                                                                                     → exit 0 (after formatting indradb_driver.py)
uv run ruff check .                                                                                                              → exit 0
uv run pytest -q                                                                                                                 → 618 passed, 6 skipped, 18 deselected
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m "integration and indradb" tests/integration/test_indradb_e2e.py -q  → 2 passed
```

## Deviations from plan

- Follow-up 2 (pin os.cc counts): `_EXPECTED_VERTICES=99` and `_EXPECTED_EDGES=180` were already pinned as exact equality by the S6 developer. No edit to `test_indradb_e2e.py` was made (no-op per dispatch instruction).

## Follow-ups

- v5: bulk pre-fetch of USR vertex set before edge phase to eliminate ~22K wasted `create_edge` RPCs (documented in ADR-17 addendum)
- v5: live Neo4j daemon test for `counters.nodes_created` path (documented in ADR-17 §Follow-ups)
- v5: function-scoped `mcp_client_isolated` fixture if a future story mutates server state non-atomically (documented in ADR-18 §Follow-ups)

## References

- plan.md, adr-17.md, adr-18.md, logs/developer-s6-e2e.md

---

# Implementation Notes — S6

## Files changed

- `tests/integration/conftest.py` — added indradb_uri, indradb_daemon, fresh_indradb fixtures per design §3.2
- `tests/integration/test_indradb_e2e.py` — new; SC-V4-2-03, SC-V4-2-04, SC-V4-3-01, SC-V4-3-02
- `src/cpp_mcp/graphdb/indradb_driver.py` — two driver bug fixes discovered during live e2e run (see Deviations)
- `tests/fixtures/fake_indradb.py` — updated get() return shape to match real daemon's batch-stream API

## Tests added/run

```
uv run ruff format --check tests/integration/test_indradb_e2e.py tests/integration/conftest.py  → exit 0
uv run ruff check tests/integration/test_indradb_e2e.py tests/integration/conftest.py           → exit 0
uv run mypy src/                                                                                  → exit 0 (30 files, no issues)
uv run pytest -q                                                                                  → 602 passed, 6 skipped, 18 deselected
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m "integration and indradb" tests/integration/test_indradb_e2e.py -q  → 2 passed
```

Pinned counts (test-repo/fmt/src/os.cc, live run 2026-05-17):
- nodes_written = 99, edges_written = 180
- nodes_attempted = 99, edges_attempted = 23169

## Deviations from plan

1. **indradb_driver.py — upsert_nodes generator truthy bug**: the driver used `if not existing:` where `existing` was an unconsumed generator from `client.get()`. Generators are always truthy in Python, so `create_vertex` was never called — every export returned nodes_written=0. Fixed by flattening: `any(item for batch in client.get(...) for item in batch)`. Filed as S6-discovered defect; scope of change is within the S6 live-test story.

2. **indradb_driver.py — upsert_edges silent-failure**: IndraDB's `create_edge` silently returns without error when either endpoint vertex does not exist in the store, but the edge is not persisted. The driver was counting these as inserts (inserted += 1) even though the edge was never stored. Fixed by post-create verification: call `SpecificEdgeQuery` after `create_edge`; only increment `inserted` if the edge is actually stored.

3. **tests/fixtures/fake_indradb.py — get() return shape**: the real daemon's `client.get()` is a gRPC streaming call returning a generator of batches (each batch is a list of items). The fake returned a flat list `[item]` or `[]`. Updated to return `[[item]]` / `[[]]` to match the real API's batch-stream shape, enabling the flatten idiom in the driver to work identically against both real and fake clients.

4. **pyproject.toml — indradb marker already registered**: the plan §S6 note "register indradb marker if not already present" — the marker was already registered in pyproject.toml by a prior story. No change required.

## Follow-ups

- `@sr-dev`: The 23169 - 180 = 22989 edge attempts that are silently dropped by IndraDB (because the target vertex is an external symbol not exported to the graph) represent a data-completeness gap. The exporter creates REFERENCES/INCLUDES edges to symbols defined outside the file, but those node USRs are not upserted as vertices. A future story should either: (a) also export stub nodes for external symbols, or (b) filter out edges whose target USR is not in the exported node set before calling upsert_edges. Currently edges_written=180 correctly matches the daemon, but edges_attempted=23169 makes the ratio misleading for callers.
- `@sr-dev`: The post-create edge verification adds one extra gRPC RPC per "dangling" edge attempt. For os.cc this is ~23K extra RPCs (acceptable for fixture-size exports). For full-repo exports this will be expensive. Escalating per ADR-17 §Consequences note on doubled RPCs.

## References

- plan.md §S6 lines 204-231
- design.md §3.2
- adr-16.md, adr-17.md, adr-18.md
- scenarios.md SC-V4-2-01..SC-V4-2-04, SC-V4-3-01..SC-V4-3-02
