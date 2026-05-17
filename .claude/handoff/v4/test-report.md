---
run_id: cpp-mcp-v4
role: qa-engineer
date: 2026-05-17
---

# Test Report — cpp-mcp-v4

## Scope

Seven stories: S1 (Identifier→str), S2 (protobuf<4 pin), S3 (insert-vs-attempt metrics),
S4 (Docker fixture removal), S5 (in-memory client harness), S6 (live IndraDB e2e),
S7 (README install fix + DEPENDENCY_MISSING wording).

## Test plan

unit | integration | BDD/E2E | regression

## Prerequisites

```bash
uv sync --all-extras   # required before first run; resolves pytest + all optional deps
```

## Commands run

### Gate 1 — default suite (integration deselected)
```
uv run pytest -q
```
Result: **618 passed, 6 skipped, 18 deselected, 1 warning**

Skips (all expected):
- tests/bdd/test_export_to_indradb.py — INDRADB_TEST_URI not set
- tests/unit/test_cognee_driver.py (x3) — COGNEE_BASE_URL not set
- tests/unit/test_graphdb_additions.py — NEO4J_TEST_URI not set

Warning: neo4j DeprecationWarning on Driver destructor — pre-existing, advisory only.

### Gate 2 — integration suite against live IndraDB daemon
```
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 uv run pytest -m integration -q
```
Result: **18 passed, 624 deselected in 43.38s**

Daemon: `indradb-server memory` autostarted via `~/.cargo/bin/indradb-server`.

### Gate 3 — new test file lint + format
```
uv run ruff format --check tests/unit/test_indradb_driver_insert_boundary.py
uv run ruff check tests/unit/test_indradb_driver_insert_boundary.py
```
Result: both exit 0.

## Results

| Suite | Passed | Failed | Skipped | Deselected |
|---|---|---|---|---|
| Default (`uv run pytest -q`) | 618 | 0 | 6 | 18 |
| Integration (`-m integration` + daemon) | 18 | 0 | 0 | 624 |
| New boundary tests only | 16 | 0 | 0 | 0 |

## Scenario coverage

| Scenario ID | Story | Test file(s) | Coverage |
|---|---|---|---|
| SC-V4-1-01 | US-V4-1 | tests/integration/test_harness_smoke.py::test_sc_v4_1_01_mcp_client_is_connected | explicit |
| SC-V4-1-02 | US-V4-1 | tests/integration/test_harness_smoke.py::test_sc_v4_1_02_cache_hit_toggle | explicit |
| SC-V4-1-03 | US-V4-1 | tests/integration/test_all_tools_smoke.py::test_sc_v4_1_03_tool_smoke[*] (7 params) | explicit |
| SC-V4-1-04 | US-V4-1 | pyproject.toml addopts `-m 'not integration'`; default gate passes with 18 deselected | implicit |
| SC-V4-2-01 | US-V4-2 | tests/integration/conftest.py::indradb_uri fixture pytest.skip | fixture-level |
| SC-V4-2-02 | US-V4-2 | tests/integration/conftest.py::indradb_daemon fixture pytest.skip | fixture-level |
| SC-V4-2-03 | US-V4-2 | tests/integration/test_indradb_e2e.py::test_sc_v4_2_03_export_writes_expected_counts | explicit; pinned _EXPECTED_VERTICES=99, _EXPECTED_EDGES=180 |
| SC-V4-2-04 | US-V4-2 | tests/integration/test_indradb_e2e.py::test_sc_v4_2_04_idempotent_reexport | explicit |
| SC-V4-3-01 | US-V4-3 | tests/integration/test_indradb_e2e.py (daemon query cross-check); tests/unit/test_indradb_driver_insert_counts.py; tests/unit/test_indradb_driver_insert_boundary.py | explicit (unit + e2e) |
| SC-V4-3-02 | US-V4-3 | tests/integration/test_indradb_e2e.py (nodes_attempted >= nodes_written assertion) | explicit |
| SC-V4-4-01 | US-V4-4 | tests/unit/test_pyproject_extras.py::test_indradb_pin (asserts `["indradb>=3.0,<4", "protobuf<4"]`) | explicit |
| SC-V4-4-02 | US-V4-4 | tests/integration/test_install.py::test_import_indradb, test_import_indradb_driver | explicit |
| SC-V4-5-01 | US-V4-5 | tests/unit/test_indradb_driver_no_identifier.py (both tests) | explicit |
| SC-V4-6-01 | US-V4-6 | tests/unit/test_no_broken_docker_image.py::test_no_broken_docker_image_reference | explicit |
| SC-V4-6-02 | US-V4-6 | tests/unit/test_no_broken_docker_image.py (grep excludes .claude dir); README grep confirmed in S4 exit gate | explicit (negative); exit gate (positive) |
| SC-V4-7-01 | US-V4-7 | tests/integration/test_readme_extras.py::TestReadmeExtrasPresent (3 tests) | explicit |
| SC-V4-7-02 | US-V4-7 | tests/integration/test_readme_extras.py::TestDependencyMissingErrorWording (2 tests) | explicit |

### OQ-2-1 resolution

Placeholder `<EXPECTED_VERTICES>` and `<EXPECTED_EDGES>` in scenarios.md SC-V4-2-03 are now
pinned in `tests/integration/test_indradb_e2e.py`:
- `_EXPECTED_VERTICES = 99`
- `_EXPECTED_EDGES = 180`

Confirmed by S6 developer live run 2026-05-17 against `test-repo/fmt/src/os.cc`.

## Defects

None. All scenarios pass. No open QA_DEFECT entries.

## Additions made

**Category 3 — mutation/boundary** (mandatory addition):

New file: `tests/unit/test_indradb_driver_insert_boundary.py` (16 tests)

Rationale: the existing `test_indradb_driver_insert_counts.py` covers the happy-path
(first-insert = N, re-insert = 0) but does not parametrise over overlap ratios, batch
size boundaries, or the generator-truthiness regression class discovered in S6.

Tests added:
1. `test_node_insert_count_overlap_parametrised` — 7-way parametrised sweep over node
   overlap percentages (0%, 50%, 100%) and batch-size boundaries (single, large).
   Kills the pre-S6 generator-truthiness bug: if `any(item for batch in ...)` were
   replaced with `bool(generator)`, the 100%-overlap cases would return N instead of 0.

2. `test_edge_insert_count_overlap_parametrised` — 5-way parametrised sweep over edge
   overlap ratios. Kills the same class for edge paths.

3. `test_edge_with_missing_target_vertex_counts_zero` — boundary: edge insert where
   target vertex absent; verifies post-create SpecificEdgeQuery verification path is
   exercised and count matches daemon state.

4. `test_empty_batch_always_returns_zero` — parametrised over nodes + edges; boundary at
   batch size = 0.

5. `test_driver_flatten_idiom_works_with_generator_client` — installs a
   `_GeneratorReturningClient` whose `get()` returns a generator (not a list) and verifies
   the driver's `any(item for batch in client.get(...) for item in batch)` idiom handles
   it correctly. Directly reproduces the S6 latent bug class.

## Observations (advisory)

1. **SC-V4-1-04 implicit only**: the marker-discipline scenario has no dedicated subprocess
   test asserting `exit code == 0` and "0 failed". It is validated implicitly by the
   default gate (18 deselected, 0 failed). Sufficient for v4; a subprocess-based assertion
   could be added in v5 for belt-and-suspenders documentation.

2. **SC-V4-2-01/02 fixture-level only**: the skip paths for unset `INDRADB_TEST_URI` and
   `INDRADB_AUTOSTART=0` + unreachable daemon are exercised implicitly by the fixture
   implementation, not by a dedicated test that monkeypatches the env and asserts the
   skip message. Functional for v4; explicit test could be added in v5.

3. **SC-V4-6-02 positive assertion via exit gate only**: `README.md` containing
   `cargo install indradb` and `indradb-server memory` is verified only by S4's exit-gate
   grep commands, not by a pytest test. `test_readme_extras.py` covers the `uv sync --extra`
   strings; a third test class for the cargo-install strings would close this gap.

4. **22,989 silently-dropped edge attempts (os.cc)**: S6 log notes that
   `edges_attempted = 23169` vs `edges_written = 180` because IndraDB drops edges whose
   target vertex is not in the exported node set. This is a data-completeness design smell
   documented in ADR-17 §Follow-ups, not a bug in v4 scope. Advisory only.

5. **neo4j DeprecationWarning**: `neo4j._sync.driver.py:547` emits a warning about Driver
   destructor usage. Pre-existing; tracked as v5 cleanup item.

## References

- scenarios.md: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/scenarios.md`
- implementation-notes.md: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/implementation-notes.md`
- developer logs: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/logs/developer-*.md`
- Cognee tags: `task:cpp-mcp-v4`, `role:qa-engineer`
