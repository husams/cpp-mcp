# Requirements Analysis

## In-Scope

- US-V4-1: In-memory FastMCP client harness with session-scoped `mcp_client` fixture
- US-V4-2: Real IndraDB end-to-end export test (env-gated, daemon autostart optional)
- US-V4-3: Fix `nodes_written` / `edges_written` to count actual inserts, not attempts
- US-V4-4: Pin `protobuf<4` in `graphdb-indradb` extra; verify import on fresh venv
- US-V4-5: Commit the uncommitted `Identifier → str` patch in `indradb_driver.py`
- US-V4-6: Remove / replace broken Docker fixture (`indradb/indradb:5.0.0`); update README and runbook
- US-V4-7: README install section lists all three extras; `DEPENDENCY_MISSING` error carries exact `--extra` flag

## Out-of-Scope

- Live Neo4j daemon tests (AC-3-3 is code-review only; no daemon available — OQ-3-1)
- Wiring the integration suite into GitLab CI (v5)
- New graphdb backends (Memgraph, Kuzu, etc.)
- Network fault scenarios (timeout, TLS, partial write) not evidenced in post-ship findings

## Assumptions

- `build_server()` entry point exists and returns a FastMCP server instance (confirmed by [[project-fastmcp-migration]])
- `fastmcp.Client(server_instance)` in-memory transport is available (confirmed by FastMCP 3.x)
- `test-repo/fmt/src/os.cc` with `test-repo/fmt/build/compile_commands.json` is present in the repo (confirmed by post-ship memory)
- `~/.cargo/bin/indradb-server` is the supported local daemon binary; Docker image is known-broken
- `indradb` Python package version is 3.0.1; `protobuf>=4` is incompatible (confirmed by defect 2)
- The `Identifier → str` patch is already applied in the working tree but uncommitted (confirmed by post-ship memory)

## Open Questions

- **OQ-2-1** (needs-clarification): Exact pinned vertex/edge counts for `os.cc` after US-V4-3 and US-V4-5 land. Placeholders `<EXPECTED_VERTICES>` and `<EXPECTED_EDGES>` are used in SC-V4-2-03; QA engineer replaces with confirmed values before signoff.
- **OQ-3-1** (needs-clarification): Whether Neo4j MERGE-affected-rows verification requires a live daemon test or is code-review only. Requirements state code-review only (AC-3-3); escalate if stakeholder disagrees. No Gherkin scenario written for this AC.
- **OQ-6-1** (needs-clarification): Whether Docker fixture should be replaced with a self-built image on the senussi registry or removed entirely in favour of cargo-only. Architect owns the ADR. SC-V4-6-01 is written for the cargo-only outcome; if architect chooses registry, the scenario step must be updated.

## Edge Cases

- `INDRADB_TEST_URI` unset → integration+indradb tests skip cleanly (confirmed by AC-2-1)
- `INDRADB_AUTOSTART=0` and daemon unreachable → `pytest.skip`, not failure (confirmed by AC-2-2)
- Second export of same file → `nodes_written == 0`, `edges_written == 0` (confirmed by AC-2-4, defect 4/5)
- Missing `graphdb-indradb` extra → `DEPENDENCY_MISSING` error (confirmed by defect 1)
- `DEPENDENCY_MISSING` error string must contain the literal `--extra` flag (confirmed by AC-7-2)
- `import indradb` on fresh venv with `protobuf>=4` → `TypeError` crash (confirmed by defect 2)
- `uv run pytest` without env vars → zero failures, all integration tests skipped (confirmed by AC-1-5)

## Stakeholders

- cpp-mcp maintainer (primary consumer of harness and export metrics)
- Developer installing `cpp-mcp[graphdb-indradb]` on a clean venv (install UX)
- New user reading README for first-time setup (documentation)

---

# Gherkin

## Scenario-to-AC Mapping

| Scenario ID   | Story    | AC(s) covered                        |
|---------------|----------|--------------------------------------|
| SC-V4-1-01    | US-V4-1  | AC-1-1                               |
| SC-V4-1-02    | US-V4-1  | AC-1-2                               |
| SC-V4-1-03    | US-V4-1  | AC-1-3 (all 7 tools)                 |
| SC-V4-1-04    | US-V4-1  | AC-1-4, AC-1-5                       |
| SC-V4-2-01    | US-V4-2  | AC-2-1                               |
| SC-V4-2-02    | US-V4-2  | AC-2-2                               |
| SC-V4-2-03    | US-V4-2  | AC-2-3, AC-2-5 (needs-clarification) |
| SC-V4-2-04    | US-V4-2  | AC-2-4 (idempotency)                 |
| SC-V4-3-01    | US-V4-3  | AC-3-1, AC-3-4                       |
| SC-V4-3-02    | US-V4-3  | AC-3-2 (optional attempts fields)    |
| SC-V4-4-01    | US-V4-4  | AC-4-1                               |
| SC-V4-4-02    | US-V4-4  | AC-4-2, AC-4-3                       |
| SC-V4-5-01    | US-V4-5  | AC-5-1, AC-5-2                       |
| SC-V4-6-01    | US-V4-6  | AC-6-1                               |
| SC-V4-6-02    | US-V4-6  | AC-6-2, AC-6-3                       |
| SC-V4-7-01    | US-V4-7  | AC-7-1                               |
| SC-V4-7-02    | US-V4-7  | AC-7-2                               |

---

```gherkin
# =============================================================================
# Feature: US-V4-1 — In-memory FastMCP client harness
# File: tests/integration/test_harness.feature
# =============================================================================

Feature: US-V4-1 In-memory FastMCP client harness
  As a cpp-mcp maintainer
  I want a pytest fixture wrapping the FastMCP server via in-memory transport
  So that all tools can be invoked through the real MCP request/response path
  without spawning a subprocess

  Background:
    Given the project has a C++ fixture file at "test-repo/fmt/src/os.cc"
    And the build directory "test-repo/fmt/build" contains "compile_commands.json"

  # SC-V4-1-01: fixture wiring
  @integration
  Scenario: SC-V4-1-01 session-scoped mcp_client fixture yields a connected FastMCP client
    Given "tests/conftest.py" defines a session-scoped fixture named "mcp_client"
    When the fixture is requested by a test
    Then the fixture yields a connected "fastmcp.Client" bound to "build_server()"
    And the client is connected to the in-memory transport without spawning a subprocess

  # SC-V4-1-02: cache miss then cache hit (boundary)
  @integration
  Scenario: SC-V4-1-02 cpp_get_ast returns cache_hit=False on first call and True on repeat
    Given the "mcp_client" fixture is active
    And no AST has been cached for "test-repo/fmt/src/os.cc"
    When "cpp_get_ast" is called via client.call_tool with file "test-repo/fmt/src/os.cc"
    Then the result field "cache_hit" equals False
    When "cpp_get_ast" is called again via client.call_tool with the same arguments
    Then the result field "cache_hit" equals True

  # SC-V4-1-03: seven tool smoke tests (Scenario Outline)
  @integration
  Scenario Outline: SC-V4-1-03 each exposed tool returns a non-error response via mcp_client
    Given the "mcp_client" fixture is active
    When "<tool_name>" is called via client.call_tool with valid arguments for "test-repo/fmt/src/os.cc"
    Then the response does not contain an "error" key
    And the response contains at least one result field

    Examples:
      | tool_name                  |
      | cpp_get_ast                |
      | cpp_get_definition         |
      | cpp_get_references         |
      | cpp_get_type_info          |
      | cpp_get_header_info        |
      | cpp_get_preprocessor_state |
      | cpp_export_to_graphdb      |

  # SC-V4-1-04: marker discipline
  @integration
  Scenario: SC-V4-1-04 running pytest without -m integration skips all integration tests cleanly
    Given the test suite under "tests/integration/" is decorated "@pytest.mark.integration"
    When "uv run pytest" is executed without the "-m integration" flag
    Then the exit code is 0
    And no integration test is reported as failed or errored
    And all integration tests are reported as skipped or deselected


# =============================================================================
# Feature: US-V4-2 — Real IndraDB end-to-end test
# File: tests/integration/test_indradb_e2e.feature
# =============================================================================

Feature: US-V4-2 Real IndraDB end-to-end export
  As a cpp-mcp maintainer
  I want an end-to-end test that exports a real C++ file to a live IndraDB daemon
  So that the 2026-05-17 regressions cannot recur silently

  Background:
    Given the project has a C++ fixture file at "test-repo/fmt/src/os.cc"
    And the build directory "test-repo/fmt/build" contains "compile_commands.json"

  # SC-V4-2-01: skip when INDRADB_TEST_URI unset
  @integration @indradb
  Scenario: SC-V4-2-01 test is skipped when INDRADB_TEST_URI environment variable is unset
    Given the environment variable "INDRADB_TEST_URI" is not set
    When the indradb end-to-end test is collected by pytest
    Then the test is skipped with a message indicating "INDRADB_TEST_URI" is required
    And the exit code is 0

  # SC-V4-2-02: daemon autostart and unreachable guard
  @integration @indradb
  Scenario: SC-V4-2-02 test skips gracefully when INDRADB_AUTOSTART is off and daemon is unreachable
    Given the environment variable "INDRADB_TEST_URI" is set to "grpc://127.0.0.1:27615"
    And the environment variable "INDRADB_AUTOSTART" is set to "0"
    And no IndraDB daemon is listening on "127.0.0.1:27615"
    When the indradb session fixture attempts to connect
    Then the fixture calls pytest.skip rather than raising an error
    And the test is reported as skipped, not failed

  # SC-V4-2-03: export and verify counts (pinned — needs-clarification)
  @integration @indradb
  Scenario: SC-V4-2-03 exporting os.cc to IndraDB writes the expected vertex and edge counts
    # needs-clarification OQ-2-1: <EXPECTED_VERTICES> and <EXPECTED_EDGES> are placeholders;
    # QA engineer replaces with values re-confirmed after US-V4-3 and US-V4-5 land.
    Given the environment variable "INDRADB_TEST_URI" is set to "grpc://127.0.0.1:27615"
    And an IndraDB daemon is running and reachable at "127.0.0.1:27615"
    And the daemon contains no previously imported data for "os.cc"
    When "cpp_export_to_graphdb" is called via mcp_client with:
      | file_path_or_dir | test-repo/fmt/src/os.cc        |
      | build_path       | test-repo/fmt/build            |
      | db_uri           | indradb://localhost:27615       |
    Then the tool response field "nodes_written" equals <EXPECTED_VERTICES>
    And the tool response field "edges_written" equals <EXPECTED_EDGES>
    When the test queries IndraDB directly for all vertices
    Then the vertex count returned by the daemon equals "nodes_written" from the tool response
    When the test queries IndraDB directly for all edges
    Then the edge count returned by the daemon equals "edges_written" from the tool response

  # SC-V4-2-04: idempotent re-export
  @integration @indradb
  Scenario: SC-V4-2-04 a second export of the same file writes zero nodes and zero edges
    Given the environment variable "INDRADB_TEST_URI" is set to "grpc://127.0.0.1:27615"
    And an IndraDB daemon is running and reachable at "127.0.0.1:27615"
    And "cpp_export_to_graphdb" has already been called once for "test-repo/fmt/src/os.cc"
    When "cpp_export_to_graphdb" is called again via mcp_client with the same arguments
    Then the tool response field "nodes_written" equals 0
    And the tool response field "edges_written" equals 0


# =============================================================================
# Feature: US-V4-3 — Fix edges_written and nodes_written to count inserts
# File: tests/integration/test_export_counts.feature
# =============================================================================

Feature: US-V4-3 Export metrics count actual inserts not attempts
  As a caller of cpp_export_to_graphdb
  I want nodes_written and edges_written to reflect rows actually inserted
  So that metrics are usable for progress and idempotency reporting

  Background:
    Given the environment variable "INDRADB_TEST_URI" is set to "grpc://127.0.0.1:27615"
    And an IndraDB daemon is running and reachable at "127.0.0.1:27615"
    And the daemon contains no previously imported data for "os.cc"

  # SC-V4-3-01: counts track inserts, not attempts
  @integration @indradb
  Scenario: SC-V4-3-01 nodes_written and edges_written reflect insert counts not attempt counts
    Given "cpp_export_to_graphdb" has been called once for "test-repo/fmt/src/os.cc"
    And the tool response recorded "nodes_written" as N and "edges_written" as M
    When the test queries IndraDB directly for all vertices
    Then the daemon vertex count equals N
    When the test queries IndraDB directly for all edges
    Then the daemon edge count equals M
    And M is substantially less than the number of edge write attempts (confirmed by defect-5)

  # SC-V4-3-02: optional attempts fields documented (assumed — no daemon required)
  @integration
  Scenario: SC-V4-3-02 if nodes_attempted and edges_attempted are present they are non-negative integers
    Given "cpp_export_to_graphdb" has been called with a valid file and db_uri
    When the tool response is inspected
    Then if the key "nodes_attempted" is present its value is an integer >= "nodes_written"
    And if the key "edges_attempted" is present its value is an integer >= "edges_written"


# =============================================================================
# Feature: US-V4-4 — Pin protobuf<4 in graphdb-indradb extra
# File: tests/integration/test_install.feature
# =============================================================================

Feature: US-V4-4 graphdb-indradb extra installs without protobuf crash
  As a user installing cpp-mcp[graphdb-indradb]
  I want a working install on a clean venv
  So that I do not hit TypeError on first import

  # SC-V4-4-01: pyproject.toml contains the pin (no daemon, structural check)
  @integration
  Scenario: SC-V4-4-01 pyproject.toml graphdb-indradb extra contains protobuf<4 constraint
    Given the file "pyproject.toml" is read
    When the "[project.optional-dependencies]" section "graphdb-indradb" is inspected
    Then the dependency list contains a constraint matching "protobuf<4"

  # SC-V4-4-02: import succeeds on fresh venv (no daemon needed)
  @integration
  Scenario: SC-V4-4-02 import indradb and indradb_driver succeed after uv sync --extra graphdb-indradb
    Given a virtual environment created with "uv sync --extra graphdb-indradb"
    When "import indradb" is executed in that environment
    Then no TypeError or ImportError is raised
    When "import cpp_mcp.graphdb.indradb_driver" is executed in that environment
    Then no TypeError or ImportError is raised


# =============================================================================
# Feature: US-V4-5 — Commit the Identifier → str driver patch
# File: tests/integration/test_indradb_driver_patch.feature
# =============================================================================

Feature: US-V4-5 indradb_driver uses plain str labels not Identifier wrapper
  As a maintainer
  I want the uncommitted Identifier-to-str fix landed in indradb_driver.py
  So that the v3 ship is actually functional

  # SC-V4-5-01: structural check — Identifier() absent, str labels present
  @integration
  Scenario: SC-V4-5-01 indradb_driver.py does not reference indradb.Identifier and module docstring is clean
    Given the file "src/cpp_mcp/graphdb/indradb_driver.py" is read
    When the source text is searched for "indradb.Identifier"
    Then no match is found anywhere in the file
    When the module docstring lines are inspected
    Then the docstring does not mention "Identifier(...)" on any line
    And the Vertex constructor call uses a plain str for the type label
    And the Edge constructor call uses a plain str for the "t" field


# =============================================================================
# Feature: US-V4-6 — Replace broken Docker fixture with cargo-install instructions
# File: tests/integration/test_docker_fixture.feature
# =============================================================================

Feature: US-V4-6 Broken IndraDB Docker image reference removed
  As a developer setting up local IndraDB
  I want working setup docs and fixtures
  So that the non-existent Docker image is never referenced

  # SC-V4-6-01: compose file does not reference broken image
  # Note: if architect ADR chooses registry image, update step to match resolved image URI.
  # needs-clarification OQ-6-1: cargo-only outcome assumed here per PM position.
  @integration
  Scenario: SC-V4-6-01 compose file does not reference the non-existent indradb Docker image
    Given the fixture path "tests/fixtures/indradb-compose.yml" either does not exist or exists with changed content
    When the file is checked for the string "indradb/indradb:5.0.0"
    Then the string "indradb/indradb:5.0.0" is not found

  # SC-V4-6-02: README and runbook carry cargo-install instructions
  @integration
  Scenario: SC-V4-6-02 README contains cargo-install local development subsection and runbook is updated
    Given the file "README.md" is read
    When the graphdb section is inspected
    Then the README contains the string "cargo install indradb"
    And the README contains the string "indradb-server memory"
    Given the file ".claude/handoff/v3/runbook.md" is read
    When the runbook text is searched for "indradb/indradb:5.0.0"
    Then the string "indradb/indradb:5.0.0" is not found in the runbook


# =============================================================================
# Feature: US-V4-7 — README install fix for graphdb extras
# File: tests/integration/test_readme_extras.feature
# =============================================================================

Feature: US-V4-7 README install section documents all graphdb extras
  As a new user
  I want the README to list all extra flags explicitly
  So that I do not hit DEPENDENCY_MISSING on the first export call

  # SC-V4-7-01: README lists all three extras
  @integration
  Scenario: SC-V4-7-01 README install section contains uv sync examples for all three graphdb extras
    Given the file "README.md" is read
    When the install section is inspected
    Then the README contains the string "graphdb-neo4j"
    And the README contains the string "graphdb-indradb"
    And the README contains the string "graphdb" as a standalone extra name
    And each extra appears in a concrete "uv sync --extra <name>" example

  # SC-V4-7-02: DEPENDENCY_MISSING error carries the exact --extra flag string
  @integration
  Scenario: SC-V4-7-02 calling cpp_export_to_graphdb without the graphdb extra returns DEPENDENCY_MISSING with --extra flag
    Given the "mcp_client" fixture is active
    And the graphdb backend extras are NOT installed in the active environment
    When "cpp_export_to_graphdb" is called via client.call_tool with db_uri "indradb://localhost:27615"
    Then the response contains error code "DEPENDENCY_MISSING"
    And the error message contains the string "--extra graphdb-indradb"
```

---

# References

- Handoff requirements: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v4/requirements.md`
- Project memory (post-ship findings): `/Users/husam/.claude/projects/-Users-husam-workspace-cpp-mcp/memory/project_graphdb_v3_post_ship_findings.md`
- Project memory (graphdb multi): `/Users/husam/.claude/projects/-Users-husam-workspace-cpp-mcp/memory/project_graphdb_multi.md`
- Wiki: `[[pages/code/cpp-mcp]]`
- Skill: `bdd-e2e-testing` (shape guidance)
- Cognee tags: `task:cpp-mcp-v4`, `role:business-analyst`
