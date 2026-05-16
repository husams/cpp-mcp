---
run_id: graphdb-multi-v3
stage: senior-developer
date: 2026-05-16
status: final
mode: plan
reads: [requirements.md, scenarios.md, design.md, adr-12.md, adr-13.md, adr-14.md, adr-15.md, pyproject.toml]
ac_coverage: US-G1/AC-1..4, US-G2/AC-1..8, US-G3/AC-1..5, US-G4/AC-1..4, US-G5/AC-1..5, US-G6/AC-1..3
---

# Plan: Pluggable GraphDB Backends (Neo4j + IndraDB)

Goal: Ship URI-scheme-based driver dispatch with a new `IndraDBDriver` peer to `Neo4jDriver`, a new `DEPENDENCY_MISSING` error code, dual optional extras, BDD coverage, and docs — without changing the existing `cpp_export_to_graphdb` tool surface (C-G1) or breaking the 472-passing Neo4j path (C-G2/C-G7).

Toolchain (project canonical — `uv.lock` present):
- Formatter: `uv run ruff format`
- Linter:    `uv run ruff check`
- Types:     `uv run mypy src/`  (project `pyproject.toml` sets `strict = true`)
- Tests:     `uv run pytest -q`

Conventions: snake_case funcs, PascalCase classes, `X | None` not `Optional[X]`, `raise ... from exc`, line length 100 (per `[tool.ruff]`).

---

## Story sequencing & dependency graph

```
S1 (error code)  ──┐
                   ├──► S3 (dispatch + tool wiring) ──► S5 (BDD) ──► S6 (docs)
S2 (IndraDB drv) ──┘                              └─► (independent)
S4 (extras)      ──────────────────────────────────────────────────► (any time)
```

| Story | Depends on | Parallel-safe with |
|-------|------------|--------------------|
| S1 | — | S4 |
| S2 | S1 | S4 |
| S3 | S1, S2 | S4 |
| S4 | — | S1, S2 |
| S5 | S2, S3 | S6 (docs touch different files) |
| S6 | S1..S5 | — |

Parallel-safe count: 2 in early stages (S1+S4 or S2+S4), then serialized.

---

## Story S1 — `DEPENDENCY_MISSING` error code (US-G1)

**AC satisfied:** US-G1/AC-1, US-G1/AC-2, US-G1/AC-3, US-G1/AC-4.

Files to change:
- `src/cpp_mcp/core/error_envelope.py` — add `ErrorCode.DEPENDENCY_MISSING = "DEPENDENCY_MISSING"`; add `class DependencyMissingError(Exception)`; insert `(DependencyMissingError, ErrorCode.DEPENDENCY_MISSING)` in `_EXC_TO_CODE` **above** `(DBUnreachableError, ErrorCode.DB_UNREACHABLE)` (ADR-13).
- `src/cpp_mcp/graphdb/neo4j_driver.py` — in `connect()`, replace the `ImportError → DBUnreachableError` line with `raise DependencyMissingError('neo4j Python driver is not installed. Install with: pip install "cpp-mcp[graphdb-neo4j]"') from exc` (fixes v2 miswire at neo4j_driver.py:51-54).

New files:
- `tests/unit/test_dependency_missing.py` — unit tests asserting:
  - envelope shape `{code, message, tool, request_id}` for `DependencyMissingError` via `wrap_tool`.
  - `_EXC_TO_CODE` orders `DependencyMissingError` before `DBUnreachableError`.
  - `Neo4jDriver().connect("bolt://x")` with `neo4j` absent (`monkeypatch.setitem(sys.modules, "neo4j", None)` pattern, or `monkeypatch.setattr` blocking import) raises `DependencyMissingError`, not `DBUnreachableError`.
  - Install-command fragment in message.

Existing tests to update:
- `tests/unit/test_envelope_codes.py` — extend the codes list to include `DEPENDENCY_MISSING`.
- `tests/unit/test_runbook_present.py` — extend runbook error-code expected list to include `DEPENDENCY_MISSING` (the row itself is added in S6; this assertion just keeps S6's row from being orphaned).

References: ADR-13; scenarios "DependencyMissingError class exists…", "Missing neo4j package returns DEPENDENCY_MISSING…".

Risks / out of scope:
- Do NOT alter envelope wire shape. Code field is the only addition.
- `wrap_tool` ordering bug if the new row is placed after `DBUnreachableError` — the unit test catches this.

Parallel-safe: yes (touches only `core/error_envelope.py` + `graphdb/neo4j_driver.py:connect`).

Exit criteria (must all pass — gates `LINT_FAIL`/`TEST_FAIL`/`BUILD_FAIL`):
```bash
uv run ruff format --check src/cpp_mcp/core/error_envelope.py src/cpp_mcp/graphdb/neo4j_driver.py tests/unit/test_dependency_missing.py
uv run ruff check src/cpp_mcp/core/error_envelope.py src/cpp_mcp/graphdb/neo4j_driver.py tests/unit/test_dependency_missing.py tests/unit/test_envelope_codes.py
uv run mypy src/cpp_mcp/core/error_envelope.py src/cpp_mcp/graphdb/neo4j_driver.py
uv run pytest -q tests/unit/test_dependency_missing.py tests/unit/test_envelope_codes.py
uv run pytest -q   # full suite still green; >=472 passed, <=1 skipped (neo4j)
```

---

## Story S2 — `IndraDBDriver` implementation (US-G2)

**AC satisfied:** US-G2/AC-1..8.

Files to change:
- (none — net-new module + tests + fake fixture)

New files:
- `src/cpp_mcp/graphdb/indradb_driver.py` — `IndraDBDriver` class (ADR-14, ADR-15):
  - `__init__(self) -> None`: `self._client: Any = None; self._closed: bool = False`.
  - `connect(self, uri: str, **kwargs: Any) -> None`:
    - lazy `import indradb`; on `ImportError`, `raise DependencyMissingError('indradb Python driver is not installed. Install with: pip install "cpp-mcp[graphdb-indradb]"') from exc`.
    - parse `uri` via `urllib.parse.urlparse`; accept schemes `indradb`, `grpc`, `indradb+grpc`; strip scheme → `host:port` (default port 27615 per design §5.2).
    - `self._client = indradb.Client(host=host, **kwargs); self._client.ping()`.
    - on any other exception: `raise DBUnreachableError(...) from exc`.
  - `upsert_nodes(self, batch: list[NodeRecord]) -> int`: per design §5.4. Use `uuid.uuid5(NS_CPPMCP_USR, rec["usr"])` (constant `NS_CPPMCP_USR` pinned in ADR-14 — copy the literal UUID into a module-level `NS_CPPMCP_USR = uuid.UUID("…")`). JSON-encode non-scalar props with `logger.debug` per ADR-15. Returns `len(batch)`.
  - `upsert_edges(self, batch: list[EdgeRecord]) -> int`: per design §5.5. Returns `len(batch)`.
  - `close(self) -> None`: idempotent guard via `self._closed` per design §5.6.
- `tests/fixtures/fake_indradb.py` — an in-memory fake of the `indradb` module: provides `Client`, `Vertex`, `Edge`, `Identifier`, `SpecificVertexQuery`, `SpecificEdgeQuery`, `BulkInserter`, and a backing dict store. Used by unit tests and BDD (shared surrogate per design §8). Installable via `monkeypatch.setitem(sys.modules, "indradb", fake_module)`.
- `tests/unit/test_indradb_driver.py` — covers:
  - import-and-protocol-shape (US-G2/AC-1): methods exist; `isinstance(IndraDBDriver(), GraphDriver)` via `runtime_checkable` Protocol (or structural check).
  - connect with each of `indradb://`, `grpc://`, `indradb+grpc://` URIs (US-G2/AC-2).
  - connect raises `DBUnreachableError` when fake client `.ping()` raises (US-G2/AC-2 fail-path).
  - connect raises `DependencyMissingError` when `indradb` not in `sys.modules` (US-G2/AC-8).
  - USR → UUID determinism across two independent `IndraDBDriver` instances (US-G2/AC-3).
  - `upsert_nodes` idempotent — vertex count stable after two identical calls (US-G2/AC-4).
  - `upsert_edges` idempotent — edge count stable (US-G2/AC-5).
  - round-trip label + props (US-G2/AC-6) via the fake store.
  - non-scalar prop is JSON-encoded; assert `logger.debug` was called (ADR-15) using `caplog`.
  - `close()` twice does not raise (US-G2/AC-7).

References: ADR-14 (UUID namespace), ADR-15 (prop serialization), design §5.

Risks / out of scope:
- The real `indradb` Python API surface (per design §11) — the fake mirrors only the calls we make. If the real client diverges, the live BDD scenario in S5 will catch it; unit tests deliberately use the fake.
- Do not import `indradb` at module-top level — must be lazy inside `connect`.

Parallel-safe: yes (net-new module; S1 must complete first because `DependencyMissingError` must exist).

Exit criteria:
```bash
uv run ruff format --check src/cpp_mcp/graphdb/indradb_driver.py tests/fixtures/fake_indradb.py tests/unit/test_indradb_driver.py
uv run ruff check src/cpp_mcp/graphdb/indradb_driver.py tests/fixtures/fake_indradb.py tests/unit/test_indradb_driver.py
uv run mypy src/cpp_mcp/graphdb/indradb_driver.py
uv run pytest -q tests/unit/test_indradb_driver.py
uv run pytest -q   # full suite green
```

---

## Story S3 — URI-scheme dispatch + tool wiring (US-G3)

**AC satisfied:** US-G3/AC-1..5.

Files to change:
- `src/cpp_mcp/graphdb/__init__.py` — remove existing `make_driver` (verified no external callers via grep before deletion); add `select_driver(db_uri: str) -> GraphDriver` per design §4. Constants `_NEO4J_SCHEMES`, `_INDRADB_SCHEMES`. Lazy-import driver classes inside the matched branch. Raise `InvalidArgumentError` for: empty string, no `://`, unknown scheme. No I/O, no `neo4j`/`indradb` package import at module-top.
- `src/cpp_mcp/tools/export_to_graphdb.py` — at the line that currently constructs `Neo4jDriver()` (≈ line 85), replace with `driver = select_driver(db_uri); driver.connect(db_uri, ...)`. Keep `DependencyMissingError` in the re-raise group alongside `DBUnreachableError` (the envelope mapper handles the rest). Re-order top-level checks so that **unknown-scheme INVALID_ARGUMENT fires before PATH_VIOLATION/FILE_NOT_FOUND** — call `select_driver(db_uri)` (which validates scheme) **before** `validate_path(...)` and file existence checks. The actual `driver.connect()` still runs after path checks (design §2).

New files:
- `tests/unit/test_driver_dispatch.py` — parametrized scheme→class table (all 6 Neo4j + 3 IndraDB schemes); `InvalidArgumentError` for unknown / empty / no-scheme inputs. Uses `monkeypatch.setitem(sys.modules, "indradb", fake_module)` so `IndraDBDriver()` instantiation does not require the real package; this also confirms `select_driver` itself does no I/O.

Existing tests to update:
- `tests/bdd/test_export_to_graphdb.py` — add scenarios (or update step impls) covering:
  - INVALID_ARGUMENT > PATH_VIOLATION for unknown scheme with `../../etc/passwd` file (scenarios "INVALID_ARGUMENT fires before PATH_VIOLATION…").
  - INVALID_ARGUMENT > FILE_NOT_FOUND for unknown scheme + missing file.
  - select_driver call-site replaces direct Neo4jDriver instantiation (covered by fake `select_driver` patch).

References: ADR-12, design §4.

Risks / out of scope:
- The reorder of validation steps must NOT regress existing path-traversal tests against `bolt://` URIs — every existing `test_path_traversal.py` and `test_export_to_graphdb.py` scenario with a Neo4j URI must still produce the same code. Cover with a quick parametrized check that bolt+bad-path still yields PATH_VIOLATION (scheme is valid → path check runs).
- Removing `make_driver` is a public-API change in `graphdb/__init__.py`. Grep `make_driver` across repo + wiki + `.claude/handoff/v1` and `.claude/handoff/v2` to ensure no live callers; if any, replace them in this story.

Parallel-safe: no (depends on S1 + S2 being in place).

Exit criteria:
```bash
uv run ruff format --check src/cpp_mcp/graphdb/__init__.py src/cpp_mcp/tools/export_to_graphdb.py tests/unit/test_driver_dispatch.py
uv run ruff check src/cpp_mcp/graphdb/ src/cpp_mcp/tools/export_to_graphdb.py tests/unit/test_driver_dispatch.py
uv run mypy src/cpp_mcp/graphdb/__init__.py src/cpp_mcp/tools/export_to_graphdb.py
uv run pytest -q tests/unit/test_driver_dispatch.py tests/bdd/test_export_to_graphdb.py
uv run pytest -q   # full suite green
test -z "$(grep -rn 'make_driver' src/ tests/ 2>/dev/null)"   # no stragglers
```

---

## Story S4 — Optional dependency extras split (US-G4)

**AC satisfied:** US-G4/AC-1..4.

Files to change:
- `pyproject.toml` — replace current `[project.optional-dependencies]` `graphdb` entry with the three extras per design §7:
  ```toml
  graphdb-neo4j = ["neo4j>=5,<6"]
  graphdb-indradb = ["indradb>=3.0,<4"]
  graphdb = ["cpp-mcp[graphdb-neo4j]", "cpp-mcp[graphdb-indradb]"]
  ```
  Keep the `dev` extras and `[dependency-groups]` `dev` block unchanged.

New files:
- `tests/unit/test_pyproject_extras.py` — parse `pyproject.toml` with stdlib `tomllib`; assert keys exist; assert pins are `"neo4j>=5,<6"` and `"indradb>=3.0,<4"`; assert meta `graphdb` references both via `"cpp-mcp[graphdb-neo4j]"` and `"cpp-mcp[graphdb-indradb]"`.

Risks / out of scope:
- Existing `cpp-mcp[graphdb]` installs now also pull IndraDB (and its `grpcio`/`protobuf`). Documented as a rename in S6 runbook.
- BDD scenarios for `uv sync` install matrix (gherkin in scenarios.md) are NOT executable in CI without burning install minutes; the unit-test of `pyproject.toml` is the durable check (US-G4/AC-2 is the strictly-required AC; AC-1/AC-4 are covered transitively by the toml content). If QA wants live `uv sync` runs, gate behind an `@uv_install` marker — out of scope for this plan; mark as future work.

Parallel-safe: yes (no code dependency on other stories).

Exit criteria:
```bash
uv run ruff format --check tests/unit/test_pyproject_extras.py
uv run ruff check tests/unit/test_pyproject_extras.py
uv run pytest -q tests/unit/test_pyproject_extras.py
uv lock --check   # lock file remains valid against the edited pyproject
uv sync           # default sync still succeeds without pulling neo4j/indradb
test -z "$(uv pip list 2>/dev/null | grep -E '^(neo4j|indradb) ')"   # confirm C-G5
```

---

## Story S5 — IndraDB BDD coverage (US-G5)

**AC satisfied:** US-G5/AC-1..5.

Files to change:
- `tests/fixtures/fake_indradb.py` — extend with a configurable failure mode (`ping()` raises) and an exposed counter API the BDD step impls can read (`node_count`, `edge_count`).
- `pyproject.toml` `[tool.pytest.ini_options].markers` — add `"indradb: requires INDRADB_TEST_URI"` to mirror the existing `"neo4j: requires NEO4J_TEST_URI"` row.

New files:
- `tests/bdd/features/export_to_indradb.feature` — exact gherkin from scenarios.md "Feature: IndraDB BDD export coverage". Tag live scenarios with `@indradb`.
- `tests/bdd/test_export_to_indradb.py` — pytest-bdd step impls. Steps:
  - "the MCP server is running with allowed root for graphdb export" — reuse fixture from `tests/bdd/test_export_to_graphdb.py`.
  - "a fake IndraDB driver is installed as the IndraDB backend" — monkeypatch `cpp_mcp.graphdb.indradb_driver.IndraDBDriver` (or the `sys.modules["indradb"]` shim) to the fake.
  - "the fake IndraDB driver is configured to fail on connect" — flip a flag on the fake before invocation.
  - "INDRADB_TEST_URI is set in the environment" — `pytest.skip` when unset; otherwise use the real driver.
  - Idempotency steps — compare node_count/edge_count between two invocations.
- `tests/fixtures/indradb-compose.yml` — `docker compose` fragment running `indradb/indradb:5.0.0` (or compatible) on port 27615 with RocksDB backend. Header comment documents `INDRADB_TEST_URI=indradb://localhost:27615` (not CI-wired per US-G5/AC-3).

References: scenarios.md "Feature: IndraDB BDD export coverage", design §8.

Risks / out of scope:
- pytest-bdd scenario-tag gating: use `pytest.skip` inside the live-scenario step, not test-level skipif (matches existing Neo4j pattern in `test_export_to_graphdb.py`).
- The `@indradb` tag must be registered as a pytest marker to avoid `PytestUnknownMarkWarning` failing `-W error` runs.

Parallel-safe: with S6 only (different file set). Depends on S2 + S3.

Exit criteria:
```bash
uv run ruff format --check tests/bdd/features/export_to_indradb.feature tests/bdd/test_export_to_indradb.py tests/fixtures/fake_indradb.py
uv run ruff check tests/bdd/test_export_to_indradb.py tests/fixtures/fake_indradb.py
uv run pytest -q tests/bdd/test_export_to_indradb.py   # all fake-driver scenarios pass; @indradb scenarios skip
uv run pytest -q   # full suite: >=472 passed, <=2 skipped (1 neo4j + 1 indradb)
```

---

## Story S6 — Documentation (US-G6)

**AC satisfied:** US-G6/AC-1..3.

Files to change:
- `README.md` — add a "Graph database backends" section listing Neo4j (default) and IndraDB (alternative) with one-line summaries and the two install commands.
- `~/workspace/wiki/pages/code/cpp-mcp.md` — append IndraDB to the architecture summary; add a `[[pages/decisions/adr-12-graphdb-dispatch]]` reference (or inline ADR link).

New files:
- `.claude/handoff/v3/runbook.md` — sections per US-G6/AC-2:
  - URI scheme → driver mapping table (the 6 Neo4j + 3 IndraDB schemes).
  - Install commands: `pip install "cpp-mcp[graphdb-neo4j]"`, `pip install "cpp-mcp[graphdb-indradb]"`, `pip install "cpp-mcp[graphdb]"` (both).
  - Daemon bring-up: `docker run -p 7687:7687 neo4j:5` and `docker compose -f tests/fixtures/indradb-compose.yml up -d`.
  - Error-code reference (extend v2 table) including a `DEPENDENCY_MISSING` row with message/cause/fix columns.
  - License posture note: Neo4j Community = GPLv3 (separate daemon); IndraDB = MPL-2.0.

Existing tests already enforce parts of this:
- `tests/unit/test_runbook_present.py` — already updated in S1 to expect the new error code; verifies the runbook file exists and contains the row.

References: scenarios.md "Feature: Documentation completeness", design §11 references.

Risks / out of scope:
- Wiki page edit goes through the wiki-first/ingest workflow per project conventions. The doc-writer agent picks this up.
- README content must not break any existing doc tests (none expected on README content beyond presence checks).

Parallel-safe: with S5 only. Depends on S1..S5 content (so it can quote correct schemes/install commands).

Exit criteria:
```bash
uv run pytest -q tests/unit/test_runbook_present.py
grep -q "Graph database backends" README.md
grep -q "DEPENDENCY_MISSING" .claude/handoff/v3/runbook.md
grep -q "GPLv3" .claude/handoff/v3/runbook.md
grep -q "MPL-2.0" .claude/handoff/v3/runbook.md
grep -q "IndraDB" ~/workspace/wiki/pages/code/cpp-mcp.md
```

---

## Traceability matrix (story → AC → exit-criteria check)

| Story | ACs | Primary durable check |
|-------|-----|----------------------|
| S1 | US-G1/AC-1..4 | `test_dependency_missing.py`, `test_envelope_codes.py` |
| S2 | US-G2/AC-1..8 | `test_indradb_driver.py` |
| S3 | US-G3/AC-1..5 | `test_driver_dispatch.py`, `test_export_to_graphdb.py` (path-order scenarios) |
| S4 | US-G4/AC-1..4 | `test_pyproject_extras.py`, `uv sync` clean-env check |
| S5 | US-G5/AC-1..5 | `test_export_to_indradb.py` (fake + gated live) |
| S6 | US-G6/AC-1..3 | `test_runbook_present.py`, README/wiki greps |

---

## Risks / Out of scope (run-wide)

- Live IndraDB CI integration: out of scope (US-G5/AC-3) — gated on `INDRADB_TEST_URI`.
- Memgraph/FalkorDB/embedded backends: ADR-12 rejected.
- Migration tooling Neo4j ↔ IndraDB: out of scope.
- Auth on graphdb connection: out of scope.
- Performance benchmarking: out of scope.
- Async driver path: ADR-12 — sync-only for v3.
- The `graphdb` meta-extra rename means `pip install cpp-mcp[graphdb]` now installs IndraDB too; documented in runbook (S6), not gated as a hard regression.

---

## References

- requirements: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/requirements.md`
- scenarios: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/scenarios.md`
- design: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/design.md`
- ADRs: `adr-12.md` (dispatch), `adr-13.md` (DEPENDENCY_MISSING), `adr-14.md` (USR→UUID), `adr-15.md` (property serialization)
- charter: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/CHARTER.md`
- predecessor patterns: `.claude/handoff/v2/` (tool registration / executor dispatch reusable)
- cognee tags: `task:graphdb-multi`, `role:senior-developer`
