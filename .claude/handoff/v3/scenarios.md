---
run_id: graphdb-multi-v3
stage: business-analyst
date: 2026-05-16
status: final
ac_coverage: US-G1/AC-1..4, US-G2/AC-1..8, US-G3/AC-1..5, US-G4/AC-1..4, US-G5/AC-1..5, US-G6/AC-1..3
---

# Requirements

## In-scope

- Error code `DEPENDENCY_MISSING` and the `DependencyMissingError` class (US-G1).
- `IndraDBDriver` implementing `GraphDriver` Protocol with gRPC-based connect, upsert_nodes, upsert_edges, close (US-G2).
- URI-scheme-based driver dispatch via `select_driver(db_uri)` (US-G3).
- Dual optional extras in `pyproject.toml` — `graphdb-neo4j`, `graphdb-indradb`, meta `graphdb` (US-G4).
- BDD feature file and pytest-bdd step implementations for the IndraDB export path, fake-driver tests unconditional, live-daemon tests gated on `INDRADB_TEST_URI` (US-G5).
- README and runbook documentation updates (US-G6).

## Out-of-scope

- Embedded backends (Kuzu, CozoDB, SurrealDB embedded, DuckPGQ).
- Memgraph, FalkorDB.
- Migration tooling between Neo4j and IndraDB.
- Auth on graph DB connections.
- Performance benchmarking.
- Async IndraDB driver path.
- Daemon health-check before export.
- CI integration for IndraDB live tests.

## Assumptions

- `assumed` — Deterministic USR-to-vertex ID mapping (US-G2/AC-3) is ensured by the architect's choice of identifier; BDD verifies idempotency outcome, not internal mechanism.
- `assumed` — `select_driver` is called with a valid string; None/empty-string inputs hit pre-existing INVALID_ARGUMENT validation before reaching dispatch.
- `assumed` — The `indradb` gRPC channel constructor is synchronous (per current `indradb==3.0.1` Python client); close is idempotent if the channel permits double-release.
- `assumed` — All pre-existing Neo4j BDD scenarios (`tests/bdd/features/export_to_graphdb.feature`) continue passing unchanged; no scenario here re-tests them.
- `assumed` — `uv pip list` is available in the test environment for extras-matrix verification scenarios.

## Open questions

All questions below are `needs-clarification` for the architect stage.

- OQ-G1 (from US-G2): Should `IndraDBDriver` expose only a sync API, or also an async path for future use? (Recommend sync-only for v3.)
- OQ-G2 (from US-G2): How are property types unsupported by IndraDB natively (e.g. nested dicts in `props`) handled? (Recommend JSON-serialize with logged warning.)
- OQ-G3 (cross-cutting): Emit deprecation log when neither extra is installed, or only on first `cpp_export_to_graphdb` invocation? (Recommend lazy — fires at `select_driver` time.)
- OQ-G4 (cross-cutting): Should `DependencyMissingError` be classified as user error (4xx-equivalent) or setup error in metrics?
- OQ-G5 (cross-cutting): Daemon health-check before export for both backends — deferred out of v3 scope.

## Edge cases

- `assumed` — DEPENDENCY_MISSING must fire before any I/O; package-not-importable path must never reach the connect() call.
- `assumed` — close() called twice on IndraDBDriver must not raise.
- `needs-clarification` — Idempotent re-export with a live IndraDB daemon: vertex count after run 2 must equal count after run 1. The fake-driver scenario uses a counting dict to confirm UPSERT semantics (no accumulation); live scenario is gated on `INDRADB_TEST_URI`.
- `assumed` — URI scheme ordering: INVALID_ARGUMENT fires before path checks; driver not instantiated for unknown schemes.
- `assumed` — `grpc://` and `indradb+grpc://` URI variants are accepted equivalently to `indradb://`.
- `needs-clarification` — JSON serialisation of unsupported prop types (OQ-G2); scenario tagged needs-clarification pending architect decision.

## Stakeholders

- Operator — selects backend, reads error messages, needs actionable install instructions.
- Tool caller — passes `db_uri`, expects existing argument interface unchanged.
- Integrator — installs cpp-mcp, needs optional extras that do not bloat the default install.
- QA engineer — runs BDD suite; live-daemon scenarios must be skippable.

---

# Gherkin

## Feature: DEPENDENCY_MISSING error code

```gherkin
Feature: DEPENDENCY_MISSING error code
  # US-G1: New DependencyMissingError class and corrected miswiring from DB_UNREACHABLE.

  # covers: US-G1/AC-1, US-G1/AC-2
  Scenario: DependencyMissingError class exists and maps to DEPENDENCY_MISSING code
    Given the cpp_mcp error envelope module is imported
    When a DependencyMissingError is raised with message 'pip install "cpp-mcp[graphdb-indradb]"'
    Then the error envelope code is "DEPENDENCY_MISSING"
    And the envelope wire shape contains fields "code", "message", "tool", "request_id"
    And the message contains 'pip install "cpp-mcp[graphdb-indradb]"'

  # covers: US-G1/AC-2
  Scenario: DependencyMissingError message contains exact install command for Neo4j extra
    Given the cpp_mcp error envelope module is imported
    When a DependencyMissingError is raised with message 'pip install "cpp-mcp[graphdb-neo4j]"'
    Then the message contains 'pip install "cpp-mcp[graphdb-neo4j]"'

  # covers: US-G1/AC-3
  Scenario: Missing neo4j package returns DEPENDENCY_MISSING not DB_UNREACHABLE
    Given the MCP server is running with allowed root for graphdb export
    And a valid C++ source file "main.cpp" exists in the allowed root
    And the neo4j Python package is not importable
    When cpp_export_to_graphdb is called with a bolt:// URI
    Then the response code is "DEPENDENCY_MISSING"
    And the response code is not "DB_UNREACHABLE"
    And the message contains 'pip install "cpp-mcp[graphdb-neo4j]"'

  # covers: US-G1/AC-3, US-G2/AC-8
  Scenario: Missing indradb package returns DEPENDENCY_MISSING not DB_UNREACHABLE
    Given the MCP server is running with allowed root for graphdb export
    And a valid C++ source file "main.cpp" exists in the allowed root
    And the indradb Python package is not importable
    When cpp_export_to_graphdb is called with an indradb:// URI
    Then the response code is "DEPENDENCY_MISSING"
    And the response code is not "DB_UNREACHABLE"
    And the message contains 'pip install "cpp-mcp[graphdb-indradb]"'

  # covers: US-G1/AC-3 (boundary: DEPENDENCY_MISSING fires before connect, no I/O)
  Scenario: DEPENDENCY_MISSING fires before any database I/O attempt
    Given the MCP server is running with allowed root for graphdb export
    And a valid C++ source file "main.cpp" exists in the allowed root
    And the indradb Python package is not importable
    When cpp_export_to_graphdb is called with an indradb:// URI
    Then no database connection is attempted
    And no database write occurs
```

## Feature: IndraDB driver protocol implementation

```gherkin
Feature: IndraDB driver protocol implementation
  # US-G2: IndraDBDriver satisfying the GraphDriver Protocol.

  # covers: US-G2/AC-1
  Scenario: IndraDBDriver module is importable and exposes required Protocol methods
    Given the indradb package is available
    When IndraDBDriver is imported from cpp_mcp.graphdb.indradb_driver
    Then the class has methods "connect", "upsert_nodes", "upsert_edges", "close"
    And IndraDBDriver satisfies the GraphDriver Protocol

  # covers: US-G2/AC-2
  Scenario: IndraDBDriver connect succeeds with indradb:// URI
    Given the indradb package is available
    And a fake gRPC channel factory is installed
    When IndraDBDriver.connect is called with "indradb://localhost:27615"
    Then no exception is raised
    And the gRPC channel is opened to "localhost:27615"

  # covers: US-G2/AC-2 (URI variant: grpc://)
  Scenario: IndraDBDriver connect accepts grpc:// URI variant
    Given the indradb package is available
    And a fake gRPC channel factory is installed
    When IndraDBDriver.connect is called with "grpc://localhost:27615"
    Then no exception is raised

  # covers: US-G2/AC-2 (URI variant: indradb+grpc://)
  Scenario: IndraDBDriver connect accepts indradb+grpc:// URI variant
    Given the indradb package is available
    And a fake gRPC channel factory is installed
    When IndraDBDriver.connect is called with "indradb+grpc://localhost:27615"
    Then no exception is raised

  # covers: US-G2/AC-2 (failure path: daemon unreachable)
  Scenario: IndraDBDriver raises DBUnreachableError when gRPC connection fails
    Given the indradb package is available
    And the gRPC channel factory is configured to raise on connect
    When IndraDBDriver.connect is called with "indradb://localhost:27615"
    Then DBUnreachableError is raised
    And the original exception is chained

  # covers: US-G2/AC-8
  Scenario: IndraDBDriver.connect raises DependencyMissingError when indradb not installed
    Given the indradb package is NOT importable
    When IndraDBDriver.connect is called with "indradb://localhost:27615"
    Then DependencyMissingError is raised
    And DBUnreachableError is not raised

  # covers: US-G2/AC-3, US-G2/AC-4 (idempotent node upsert with fake driver)
  Scenario: IndraDBDriver upsert_nodes is idempotent — same USR produces same vertex count
    Given the indradb package is available
    And an in-memory fake IndraDB store is active
    And a NodeRecord batch with USR "c:@F@foo#" is prepared
    When upsert_nodes is called with the batch
    And upsert_nodes is called again with the same batch
    Then the vertex count equals the count after the first call
    And no duplicate vertex exists for USR "c:@F@foo#"

  # covers: US-G2/AC-5 (idempotent edge upsert with fake driver)
  Scenario: IndraDBDriver upsert_edges is idempotent — re-export does not duplicate edges
    Given the indradb package is available
    And an in-memory fake IndraDB store is active
    And an EdgeRecord batch from "c:@F@foo#" to "c:@F@bar#" of type "CALLS" is prepared
    When upsert_edges is called with the batch
    And upsert_edges is called again with the same batch
    Then the edge count equals the count after the first call

  # covers: US-G2/AC-6
  Scenario: IndraDBDriver round-trip preserves node label and props
    Given the indradb package is available
    And an in-memory fake IndraDB store is active
    And a NodeRecord with label "Function" and props {"name": "foo", "path": "main.cpp"} is prepared
    When upsert_nodes is called with the record
    Then reading the vertex back yields label "Function"
    And the vertex has property "name" equal to "foo"
    And the vertex has property "path" equal to "main.cpp"

  # covers: US-G2/AC-6 (edge type)
  Scenario: IndraDBDriver round-trip preserves edge type
    Given the indradb package is available
    And an in-memory fake IndraDB store is active
    And an EdgeRecord of type "CALLS" is prepared
    When upsert_edges is called with the record
    Then reading the edge back yields type "CALLS"

  # covers: US-G2/AC-7
  Scenario: IndraDBDriver close is idempotent — calling twice does not raise
    Given the indradb package is available
    And a fake gRPC channel factory is installed
    And IndraDBDriver is connected to "indradb://localhost:27615"
    When close is called
    And close is called again
    Then no exception is raised
```

## Feature: URI-scheme-based driver dispatch

```gherkin
Feature: URI-scheme-based driver dispatch
  # US-G3: select_driver function routes db_uri to the correct driver class.

  # covers: US-G3/AC-1 (Neo4j schemes)
  Scenario Outline: select_driver returns Neo4jDriver for bolt/neo4j URI schemes
    Given the graphdb dispatch module is imported
    When select_driver is called with "<uri>"
    Then the returned driver is an instance of Neo4jDriver

    Examples:
      | uri                             |
      | bolt://localhost:7687           |
      | bolt+s://localhost:7687         |
      | bolt+ssc://localhost:7687       |
      | neo4j://localhost:7687          |
      | neo4j+s://localhost:7687        |
      | neo4j+ssc://localhost:7687      |

  # covers: US-G3/AC-1 (IndraDB schemes)
  Scenario Outline: select_driver returns IndraDBDriver for indradb/grpc URI schemes
    Given the graphdb dispatch module is imported
    When select_driver is called with "<uri>"
    Then the returned driver is an instance of IndraDBDriver

    Examples:
      | uri                              |
      | indradb://localhost:27615        |
      | grpc://localhost:27615           |
      | indradb+grpc://localhost:27615   |

  # covers: US-G3/AC-2
  Scenario: select_driver raises InvalidArgumentError for unknown URI scheme
    Given the graphdb dispatch module is imported
    When select_driver is called with "memgraph://localhost:7687"
    Then InvalidArgumentError is raised
    And the error message lists supported schemes

  # covers: US-G3/AC-2 (boundary: empty string)
  Scenario: select_driver raises InvalidArgumentError for empty db_uri
    Given the graphdb dispatch module is imported
    When select_driver is called with ""
    Then InvalidArgumentError is raised

  # covers: US-G3/AC-2 (boundary: missing scheme delimiter)
  Scenario: select_driver raises InvalidArgumentError for URI with no scheme delimiter
    Given the graphdb dispatch module is imported
    When select_driver is called with "localhost:7687"
    Then InvalidArgumentError is raised

  # covers: US-G3/AC-3
  Scenario: cpp_export_to_graphdb uses select_driver not direct Neo4jDriver instantiation
    Given a fake select_driver returning a fake graph driver is patched in
    And a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with that file and a bolt:// URI
    Then select_driver was called with the bolt:// URI
    And Neo4jDriver was not directly instantiated

  # covers: US-G3/AC-4 (error ordering: unknown scheme wins over bad path)
  Scenario: INVALID_ARGUMENT fires before PATH_VIOLATION for unknown scheme with traversal path
    Given the MCP server is running with allowed root for graphdb export
    When cpp_export_to_graphdb is called with file_path_or_dir "../../etc/passwd" and db_uri "mysql://localhost:3306"
    Then the response code is "INVALID_ARGUMENT"
    And the response code is not "PATH_VIOLATION"

  # covers: US-G3/AC-4 (error ordering: unknown scheme wins over missing file)
  Scenario: INVALID_ARGUMENT fires before FILE_NOT_FOUND for unknown scheme
    Given the MCP server is running with allowed root for graphdb export
    When cpp_export_to_graphdb is called with non-existent file and db_uri "surrealdb://localhost:8000"
    Then the response code is "INVALID_ARGUMENT"

  # covers: US-G3/AC-4 (error ordering: DEPENDENCY_MISSING fires after path checks)
  Scenario: DEPENDENCY_MISSING fires after path checks pass, not before
    Given the MCP server is running with allowed root for graphdb export
    And a valid C++ source file "main.cpp" exists in the allowed root
    And the indradb Python package is not importable
    When cpp_export_to_graphdb is called with that file and an indradb:// URI
    Then the response code is "DEPENDENCY_MISSING"
    And the response code is not "PATH_VIOLATION"
    And the response code is not "FILE_NOT_FOUND"

  # covers: US-G3/AC-5 (ADR-12 filed — checked by docs/review stage, not executable here)
  # Note: adr-12.md existence and content is a docs artifact, not a BDD scenario.
```

## Feature: Optional dependency packaging — dual extras

```gherkin
Feature: Optional dependency packaging — dual extras
  # US-G4: pyproject.toml exposes graphdb-neo4j, graphdb-indradb, and graphdb meta-extras.

  # covers: US-G4/AC-1, US-G4/AC-2
  Scenario: pyproject.toml defines all three graphdb extras with correct version pins
    Given pyproject.toml is parsed
    Then optional-dependencies contains extra "graphdb-neo4j" pinned to "neo4j>=5,<6"
    And optional-dependencies contains extra "graphdb-indradb" pinned to "indradb>=3.0,<4"
    And optional-dependencies contains meta-extra "graphdb" referencing both "graphdb-neo4j" and "graphdb-indradb"

  # covers: US-G4/AC-4 (boundary: default install — no extras)
  Scenario: Default uv sync installs neither neo4j nor indradb
    Given a clean virtual environment with no extras installed
    When "uv sync" is run with no extra flags
    Then "uv pip list" output does not contain "neo4j"
    And "uv pip list" output does not contain "indradb"

  # covers: US-G4/AC-1 (install matrix: neo4j only)
  Scenario: Installing graphdb-neo4j extra adds neo4j and not indradb
    Given a clean virtual environment with no extras installed
    When "uv sync --extra graphdb-neo4j" is run
    Then "uv pip list" output contains "neo4j"
    And "uv pip list" output does not contain "indradb"

  # covers: US-G4/AC-1 (install matrix: indradb only)
  Scenario: Installing graphdb-indradb extra adds indradb and not neo4j
    Given a clean virtual environment with no extras installed
    When "uv sync --extra graphdb-indradb" is run
    Then "uv pip list" output contains "indradb"
    And "uv pip list" output does not contain "neo4j"

  # covers: US-G4/AC-1 (install matrix: meta-extra installs both)
  Scenario: Installing graphdb meta-extra adds both neo4j and indradb
    Given a clean virtual environment with no extras installed
    When "uv sync --extra graphdb" is run
    Then "uv pip list" output contains "neo4j"
    And "uv pip list" output contains "indradb"

  # covers: US-G4/AC-3 (runbook content — checked by docs/review stage)
  # Note: runbook.md install commands are a docs artifact reviewed outside BDD.
```

## Feature: IndraDB BDD export coverage

```gherkin
Feature: IndraDB BDD export coverage
  # US-G5: cpp_export_to_graphdb end-to-end with IndraDB, fake-driver unconditional,
  # live-daemon gated on INDRADB_TEST_URI.

  Background:
    Given the MCP server is running with allowed root for graphdb export
    And a fake IndraDB driver is installed as the IndraDB backend

  # covers: US-G5/AC-1 (connect and single-file export — fake driver)
  Scenario: Export a single C++ file to IndraDB via fake driver succeeds
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with that file and an indradb:// URI
    Then the response contains files_processed equal to 1
    And the response contains no errors
    And graph node types include File

  # covers: US-G5/AC-1, US-G5/AC-5 (idempotent re-export — fake driver)
  Scenario: Re-exporting the same file to IndraDB produces the same node count
    Given a valid C++ source file "main.cpp" exists in the allowed root
    And the fake IndraDB driver uses an idempotent upsert store
    When cpp_export_to_graphdb is called with that file and an indradb:// URI
    And cpp_export_to_graphdb is called again with the same file and URI
    Then the node count after the second run equals the node count after the first run
    And the edge count after the second run equals the edge count after the first run

  # covers: US-G5/AC-1 (unreachable-daemon error path — fake driver)
  Scenario: Export to IndraDB with unreachable daemon returns DB_UNREACHABLE
    Given a valid C++ source file "main.cpp" exists in the allowed root
    And the fake IndraDB driver is configured to fail on connect
    When cpp_export_to_graphdb is called with that file and an indradb:// URI
    Then the response code is "DB_UNREACHABLE"
    And no database write occurs

  # covers: US-G5/AC-4 (URI dispatch table — all advertised schemes, no daemon)
  Scenario Outline: select_driver dispatch table covers all IndraDB-advertised schemes
    Given a fake IndraDB driver class is registered
    When select_driver is called with "<uri>"
    Then the returned driver is an instance of IndraDBDriver
    And no gRPC connection is attempted

    Examples:
      | uri                              |
      | indradb://localhost:27615        |
      | grpc://localhost:27615           |
      | indradb+grpc://localhost:27615   |

  # covers: US-G5/AC-5 (path validation mirrors test_export_to_graphdb.py)
  Scenario: Path traversal in file_path_or_dir with indradb URI returns PATH_VIOLATION
    Given the fake IndraDB driver is installed
    When cpp_export_to_graphdb is called with file_path_or_dir "../../etc/passwd" and an indradb:// URI
    Then the response code is "PATH_VIOLATION"
    And no database write occurs

  # covers: US-G5/AC-5 (missing file)
  Scenario: Non-existent file with indradb URI returns FILE_NOT_FOUND
    Given the fake IndraDB driver is installed
    When cpp_export_to_graphdb is called with a non-existent file and an indradb:// URI
    Then the response code is "FILE_NOT_FOUND"
    And no database write occurs

  # covers: US-G5/AC-1, US-G5/AC-2 (live daemon — gated on INDRADB_TEST_URI)
  @indradb
  Scenario: Export a C++ file to a real IndraDB daemon and verify node exists
    Given INDRADB_TEST_URI is set in the environment
    And a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with that file and the INDRADB_TEST_URI
    Then the response contains files_processed equal to 1
    And the response contains no errors
    And the live IndraDB database contains at least one File node

  # covers: US-G5/AC-1 (idempotent re-export — live daemon)
  @indradb
  Scenario: Re-exporting to a real IndraDB daemon is idempotent
    Given INDRADB_TEST_URI is set in the environment
    And a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with that file and the INDRADB_TEST_URI
    And the node count is recorded
    And cpp_export_to_graphdb is called again with the same file and URI
    Then the node count after the second run equals the recorded count
```

## Feature: Documentation completeness

```gherkin
Feature: Documentation completeness
  # US-G6: README, runbook, and wiki page contain backend documentation.
  # These scenarios verify file content; they do not execute runtime behavior.

  # covers: US-G6/AC-1
  Scenario: README contains a "Graph database backends" section
    Given README.md is read
    Then it contains a section named "Graph database backends"
    And the section mentions "Neo4j"
    And the section mentions "IndraDB"

  # covers: US-G6/AC-2
  Scenario: Runbook documents URI schemes, install commands, error codes, and license posture
    Given the v3 runbook.md is read
    Then it contains a URI scheme to driver mapping table
    And it contains an install command for the neo4j backend
    And it contains an install command for the indradb backend
    And it contains a row for error code "DEPENDENCY_MISSING"
    And it contains a license posture note mentioning "GPLv3" and "MPL-2.0"

  # covers: US-G6/AC-3
  Scenario: Wiki page cpp-mcp.md includes IndraDB in the architecture summary
    Given the wiki page at "~/workspace/wiki/pages/code/cpp-mcp.md" is read
    Then it contains a reference to "IndraDB"
    And it describes IndraDB as an alternative graph backend
```

---

# References

- Handoff: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/requirements.md`
- Charter: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v3/CHARTER.md`
- Existing BDD tests (shape reference): `tests/bdd/test_export_to_graphdb.py`, `tests/bdd/features/export_to_graphdb.feature`
- ADR-7 (GraphDriver Protocol): `src/cpp_mcp/graphdb/driver.py`
- ADR-2 (error envelope): referenced in US-G1/AC-4 amendment `adr-13.md`
- Cognee tags: `task:graphdb-multi`, `role:business-analyst`
