# v4 Plan — Real End-to-End Tests + v3 Post-Ship Bug Fixes

**Status:** ready-for-dev
**Date:** 2026-05-17
**run_id:** cpp-mcp-v4
**Senior developer:** Claude (Opus 4.7)
**Inputs:** [requirements.md](requirements.md), [design.md](design.md), [adr-16.md](adr-16.md), [adr-17.md](adr-17.md), [adr-18.md](adr-18.md)

---

## Toolchain (per python-conventions; project uses `uv.lock`)

| Role | Command |
|---|---|
| Formatter | `uv run ruff format .` |
| Linter | `uv run ruff check .` |
| Type checker | `uv run mypy src/` |
| Test runner | `uv run pytest` |
| Integration runner | `uv run pytest -m integration` |

All exit-criteria commands are run from `/Users/husam/workspace/cpp-mcp`.

---

## Story ordering and dependency graph

```
S1 (Identifier→str + docstring) ──► S2 (protobuf<4)
                                        │
S3 (insert-vs-attempt metrics) ◄────────┘
                                        │
S4 (Docker fixture replacement) [parallel with S1..S3]
                                        │
S5 (in-memory Client harness + scaffold) ◄── S1..S3
                                        │
S6 (live IndraDB e2e test)        ◄─────┘
                                        │
S7 (README install + DEPENDENCY_MISSING wording) [parallel with S4..S6]
```

Seven stories chosen to keep each PR small, reviewable, and revertable. Bundling per dispatch hint: S1 bundles the Identifier patch + docstring cleanup (one natural commit).

---

## S1 — `commit-identifier-to-str-driver-patch`

**Goal:** Land the uncommitted working-tree fix to `indradb_driver.py` so every export call no longer raises `AttributeError`, and clean the module docstring's stale `Identifier(...)` references.

**AC-IDs satisfied:** AC-5-1, AC-5-2 (AC-5-3 verified in S6).

**ADR refs:** ADR-17 (driver contract referenced; not modified here), defect 2 of `[[project-graphdb-v3-post-ship-findings]]`.

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/indradb_driver.py` — commit working-tree `indradb.Identifier(...)` → plain `str` change at the two call sites (current lines 143 and 177/178); strip `Identifier(...)` from module docstring (current lines 8 and 10).

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_indradb_driver_no_identifier.py` — structural grep test asserting `"indradb.Identifier"` is absent from the driver source file (string check, not import-based; runs without the `indradb` dep installed).

**Parallel-safe:** false (S2, S3 edit the same file).

**Exit criteria (all must exit 0):**
```bash
uv run ruff format --check src/cpp_mcp/graphdb/indradb_driver.py tests/unit/test_indradb_driver_no_identifier.py
uv run ruff check src/cpp_mcp/graphdb/indradb_driver.py tests/unit/test_indradb_driver_no_identifier.py
uv run mypy src/cpp_mcp/graphdb/indradb_driver.py
uv run pytest tests/unit/test_indradb_driver_no_identifier.py -q
uv run pytest -q
test -z "$(git diff src/cpp_mcp/graphdb/indradb_driver.py)"   # working-tree clean after commit
! grep -n 'indradb.Identifier' src/cpp_mcp/graphdb/indradb_driver.py
```

---

## S2 — `pin-protobuf-lt-4-in-graphdb-indradb-extra`

**Goal:** Add `protobuf<4` to the `graphdb-indradb` optional dep so `import indradb` works on a clean venv.

**AC-IDs satisfied:** AC-4-1, AC-4-2, AC-4-3.

**ADR refs:** ADR-18 §5 (pin documented).

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/pyproject.toml` — `[project.optional-dependencies].graphdb-indradb` becomes `["indradb>=3.0,<4", "protobuf<4"]`.
- `/Users/husam/workspace/cpp-mcp/uv.lock` — regenerate via `uv lock`.

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/integration/__init__.py` — empty.
- `/Users/husam/workspace/cpp-mcp/tests/integration/test_install.py` — `@pytest.mark.integration` test that does `import indradb` and `import cpp_mcp.graphdb.indradb_driver`; asserts both succeed (no daemon/network).

**Parallel-safe:** true (does not touch driver code; the `tests/integration/` directory is created here for the first time).

**Exit criteria:**
```bash
uv lock --check
uv sync --extra graphdb-indradb
uv run python -c "import indradb; import cpp_mcp.graphdb.indradb_driver"
uv run ruff format --check pyproject.toml tests/integration/test_install.py
uv run ruff check tests/integration/test_install.py
uv run pytest -m integration tests/integration/test_install.py -q
uv run pytest -q   # default run still skips integration
```

---

## S3 — `fix-metrics-inserts-vs-attempts-both-drivers`

**Goal:** Make `nodes_written` / `edges_written` count inserts only; expose `nodes_attempted` / `edges_attempted` as additional fields. Apply to both IndraDB and Neo4j drivers per ADR-17.

**AC-IDs satisfied:** AC-3-1, AC-3-2, AC-3-3 (AC-3-4 verified in S6).

**ADR refs:** ADR-17 (entire decision).

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/driver.py` — tighten `upsert_nodes` / `upsert_edges` Protocol docstrings to "inserts only".
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/indradb_driver.py` — per-record `SpecificVertexQuery` / `SpecificEdgeQuery` pre-check; return insert count (not `len(batch)`).
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/neo4j_driver.py` — replace `RETURN n`-row counting with `result.consume().counters.nodes_created` / `relationships_created`.
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/exporter.py` — extend return dict with `nodes_attempted` / `edges_attempted`.
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/export_to_graphdb.py` — propagate new fields into MCP response; update docstring.
- `/Users/husam/workspace/cpp-mcp/tests/fixtures/fake_indradb.py` — update fake to track inserts vs attempts (existing v3 BDD scenarios `SC_US_G5_1`, `SC_US_G5_2` depend on this).
- `/Users/husam/workspace/cpp-mcp/tests/bdd/` — update any step defs / feature assertions that expect attempt-count semantics (developer enumerates with `grep -rln nodes_written tests/bdd/` before editing).

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_indradb_driver_insert_counts.py` — unit test against `fake_indradb` (no daemon) asserting second upsert of identical records returns 0.
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/logs/developer-us-v4-3.md` — developer records the Neo4j code-review finding per AC-3-3.

**Parallel-safe:** false (touches same files as S1; runs after S1+S2 land).

**Exit criteria:**
```bash
uv run ruff format --check src/ tests/unit tests/bdd tests/fixtures
uv run ruff check src/ tests/unit tests/bdd tests/fixtures
uv run mypy src/
uv run pytest tests/unit -q
uv run pytest tests/bdd -q
uv run pytest -q
test -f .claude/handoff/v4/logs/developer-us-v4-3.md
```

---

## S4 — `replace-docker-fixture-with-cargo-install-path`

**Goal:** Delete the broken `indradb-compose.yml` fixture, document `cargo install indradb` as the canonical local-dev path, and update v3 runbook references.

**AC-IDs satisfied:** AC-6-1, AC-6-2 (README), AC-6-3 (runbook).

**ADR refs:** ADR-16.

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/tests/fixtures/indradb-compose.yml` — **delete**.
- `/Users/husam/workspace/cpp-mcp/README.md` — add `## Local development (IndraDB)` subsection with `cargo install indradb` + `indradb-server memory`.
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/runbook.md` — replace broken `indradb/indradb:5.0.0` image references with the cargo-install path.

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_no_broken_docker_image.py` — repo-grep test asserting the literal string `indradb/indradb:5.0.0` is absent from the working tree.

**Parallel-safe:** true (independent of driver/test-harness work).

**Exit criteria:**
```bash
test ! -e tests/fixtures/indradb-compose.yml
! grep -rn 'indradb/indradb:5.0.0' . --exclude-dir=.git --exclude-dir=.venv
uv run ruff format --check tests/unit/test_no_broken_docker_image.py
uv run ruff check tests/unit/test_no_broken_docker_image.py
uv run pytest tests/unit/test_no_broken_docker_image.py -q
grep -q 'cargo install indradb' README.md
grep -q 'cargo install indradb' .claude/handoff/v3/runbook.md
uv run pytest -q
```

---

## S5 — `in-memory-client-harness-and-integration-scaffold`

**Goal:** Add the session-scoped `mcp_client` fixture using `fastmcp.Client(build_server())`, register the `integration` marker, set default `addopts` to skip integration, and scaffold seven-tool smoke tests per AC-1-3.

**AC-IDs satisfied:** AC-1-1, AC-1-2, AC-1-3, AC-1-4, AC-1-5.

**ADR refs:** ADR-18.

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/tests/conftest.py` — add session-scoped `mcp_client` fixture (async, via `pytest_asyncio.fixture`).
- `/Users/husam/workspace/cpp-mcp/pyproject.toml` — register `integration` marker; set `addopts = "-ra -m 'not integration'"`.

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/integration/conftest.py` — placeholder; daemon fixtures arrive in S6.
- `/Users/husam/workspace/cpp-mcp/tests/integration/test_harness_smoke.py` — SC-V4-1-01, SC-V4-1-02 (cache_hit toggle on `cpp_get_ast`).
- `/Users/husam/workspace/cpp-mcp/tests/integration/test_all_tools_smoke.py` — parametrised over the seven tools; for `cpp_export_to_graphdb` use `db_uri="bolt://invalid"` and assert a structured `DB_UNREACHABLE` / `DEPENDENCY_MISSING` envelope per design §3.1.

**Parallel-safe:** false (S6 depends on this; S2 also touches pyproject.toml and `tests/integration/__init__.py` — must merge S2 first).

**Exit criteria:**
```bash
uv run ruff format --check tests/conftest.py tests/integration pyproject.toml
uv run ruff check tests/conftest.py tests/integration
uv run mypy src/
uv run pytest -q                                    # integration skipped by default
uv run pytest -m integration tests/integration/test_harness_smoke.py tests/integration/test_all_tools_smoke.py -q
uv run pytest --collect-only -m integration -q | grep -E 'test_harness_smoke|test_all_tools_smoke'
```

---

## S6 — `live-indradb-e2e-test-against-fmt-os-cc`

**Goal:** End-to-end test that exports `test-repo/fmt/src/os.cc` through the in-process MCP client to a real `indradb-server memory` daemon and verifies vertex/edge counts plus idempotency.

**AC-IDs satisfied:** AC-2-1, AC-2-2, AC-2-3, AC-2-4, AC-2-5 (QA pins exact counts in `scenarios.md`); also closes AC-3-4 and AC-5-3.

**ADR refs:** ADR-16, ADR-17, ADR-18.

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/tests/integration/conftest.py` — add `indradb_uri`, `indradb_daemon`, `fresh_indradb` fixtures per design §3.2.
- `/Users/husam/workspace/cpp-mcp/pyproject.toml` — register `indradb` marker if not already present.

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/integration/test_indradb_e2e.py` — SC-V4-2-01..04, SC-V4-3-01..02. Uses `mcp_client` + `fresh_indradb`. Queries daemon directly post-export for independent vertex/edge counts. Idempotency: second call returns `nodes_written == 0 and edges_written == 0`.

**Parallel-safe:** false (depends on S1, S2, S3, S5).

**Exit criteria:**
```bash
uv run ruff format --check tests/integration/test_indradb_e2e.py tests/integration/conftest.py
uv run ruff check tests/integration/test_indradb_e2e.py tests/integration/conftest.py
uv run mypy src/
uv run pytest -q                                                                 # skipped (no env)
INDRADB_AUTOSTART=1 INDRADB_TEST_URI=grpc://127.0.0.1:27615 \
  uv run pytest -m "integration and indradb" tests/integration/test_indradb_e2e.py -q
```

(Last command requires `indradb-server` on `$PATH`; QA fixture skips with a clear message otherwise per ADR-16.)

---

## S7 — `readme-install-fix-and-dependency-missing-wording`

**Goal:** README install section enumerates the three extras with `uv sync` examples; `DEPENDENCY_MISSING` error message contains the literal `--extra graphdb-<name>` string for both drivers.

**AC-IDs satisfied:** AC-7-1, AC-7-2.

**ADR refs:** none direct; ergonomics polish referenced in design §3.7.

**Files to touch:**
- `/Users/husam/workspace/cpp-mcp/README.md` — install section with `graphdb-neo4j`, `graphdb-indradb`, `graphdb` examples.
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/indradb_driver.py` — `DependencyMissingError` message includes `uv sync --extra graphdb-indradb`.
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/graphdb/neo4j_driver.py` — same treatment for `--extra graphdb-neo4j`.

**New files:**
- `/Users/husam/workspace/cpp-mcp/tests/integration/test_readme_extras.py` — SC-V4-7-01 (README contains all three `uv sync --extra` strings), SC-V4-7-02 (driver-import patching to force `DependencyMissingError` and assert message contains the literal extra flag).
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/logs/developer-us-v4-7.md` — developer records pre/post wording per AC-7-2.

**Parallel-safe:** true (S4 also touches README — merge S4 first; after that, S7 is independent of S5/S6).

**Exit criteria:**
```bash
uv run ruff format --check src/cpp_mcp/graphdb/indradb_driver.py src/cpp_mcp/graphdb/neo4j_driver.py tests/integration/test_readme_extras.py
uv run ruff check src/cpp_mcp/graphdb/indradb_driver.py src/cpp_mcp/graphdb/neo4j_driver.py tests/integration/test_readme_extras.py
uv run mypy src/
grep -q 'uv sync --extra graphdb-neo4j' README.md
grep -q 'uv sync --extra graphdb-indradb' README.md
grep -q 'uv sync --extra graphdb' README.md
uv run pytest -m integration tests/integration/test_readme_extras.py -q
uv run pytest -q
test -f .claude/handoff/v4/logs/developer-us-v4-7.md
```

---

## Risks

- **S3 BDD churn:** existing `SC_US_G5_*` BDD scenarios assume attempt semantics; developer must enumerate hits with `grep -rln nodes_written tests/bdd/` before editing or the suite breaks silently. (Design §5 row 7.)
- **S3 doubled RPCs on IndraDB:** per ADR-17 §Consequences; acceptable for v4 fixture-sized exports.
- **S6 daemon availability:** `indradb-server` not on `$PATH` skips the e2e test — coordinator must run it locally before approving v4 ship.
- **S5 `addopts` change** alters default `uv run pytest` invocation across all contributors; verified to skip cleanly via AC-1-5.
- **S2 + S5 both edit pyproject.toml** — must land in order (S2 first per dependency graph).

## Out of scope (re-confirmed from design §6)

Live Neo4j daemon tests, GitLab CI wiring, new backends, IndraDB performance work, network fault injection.

## References

- [requirements.md](requirements.md), [design.md](design.md), [scenarios.md](scenarios.md)
- [ADR-16](adr-16.md), [ADR-17](adr-17.md), [ADR-18](adr-18.md)
- `[[project-graphdb-v3-post-ship-findings]]`, `[[project-fastmcp-migration]]`, `[[project-graphdb-multi]]`
- cognee tags: `task:cpp-mcp-v4`, `role:senior-developer`
