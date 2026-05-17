Feature: query_graphdb and describe_graph_schema — unit-testable BDD scenarios
  # Maps to US-V6-Q1 (AC-Q1-1..AC-Q1-10) and US-V6-Q2 (AC-Q2-1..AC-Q2-8)
  # These scenarios run without a live daemon (fake_indradb or monkeypatching).
  # Live-daemon scenarios are in tests/integration/.

  # ---------------------------------------------------------------------------
  # AC-Q1-1 / AC-Q1-6 — row_limit defaults and truncation
  # ---------------------------------------------------------------------------

  @AC_Q1_1 @AC_Q1_6
  Scenario: row_limit defaults to 200 and result under cap — truncated false
    Given an IndraDB executor backed by the fake client
    And 50 Function vertices are inserted into the fake client
    When I execute all_vertices with no row_limit override (default 200)
    Then rows_returned equals 50
    And truncated is false
    And the rows list has length 50

  @AC_Q1_1 @AC_Q1_6
  Scenario: Result exceeds row_limit — rows capped, truncated true, no error raised
    Given an IndraDB executor backed by the fake client
    And 10 Function vertices are inserted into the fake client
    When I execute all_vertices with row_limit 5
    Then truncated is true
    And the rows list has length 5
    And the result does not contain a code key

  @AC_Q1_6
  Scenario: Result count equals row_limit exactly — truncated false
    Given an IndraDB executor backed by the fake client
    And 5 Namespace vertices are inserted into the fake client
    When I execute all_vertices with row_limit 5
    Then truncated is false
    And the rows list has length 5

  # ---------------------------------------------------------------------------
  # AC-Q1-5 / OQ-Q1-2 — Cypher string to IndraDB URI returns QUERY_PARSE_ERROR
  # ---------------------------------------------------------------------------

  @AC_Q1_5 @OQ_Q1_2
  Scenario: Cypher-shaped string sent to IndraDB URI returns QUERY_PARSE_ERROR
    Given an IndraDB executor backed by the fake client
    When I dispatch the query string "MATCH (n:Function) RETURN n.name LIMIT 5"
    Then a QueryParseError is raised matching "valid JSON"

  # ---------------------------------------------------------------------------
  # AC-Q1-5 — IndraDB unsupported verb returns QUERY_UNSUPPORTED
  # ---------------------------------------------------------------------------

  @AC_Q1_5
  Scenario: IndraDB query type outside the supported subset returns QUERY_UNSUPPORTED
    Given an IndraDB executor backed by the fake client
    When I dispatch the unsupported verb query
    Then a QueryUnsupportedError is raised matching "Unsupported query verb"

  # ---------------------------------------------------------------------------
  # AC-Q1-7 — Malformed IndraDB JSON returns QUERY_PARSE_ERROR
  # ---------------------------------------------------------------------------

  @AC_Q1_7
  Scenario: Malformed IndraDB JSON query returns QUERY_PARSE_ERROR
    Given an IndraDB executor backed by the fake client
    When I dispatch the query string "{query: all_vertices}"
    Then a QueryParseError is raised matching "valid JSON"

  # ---------------------------------------------------------------------------
  # AC-Q1-8 — CPP_MCP_QUERY_TIMEOUT_SECONDS clamp and default
  # ---------------------------------------------------------------------------

  @AC_Q1_8
  Scenario: CPP_MCP_QUERY_TIMEOUT_SECONDS below 1 is clamped to 1
    Given the env var CPP_MCP_QUERY_TIMEOUT_SECONDS is set to "0"
    When the server resolves the effective timeout
    Then the effective timeout is 1 second

  @AC_Q1_8
  Scenario: CPP_MCP_QUERY_TIMEOUT_SECONDS above 120 is clamped to 120
    Given the env var CPP_MCP_QUERY_TIMEOUT_SECONDS is set to "999"
    When the server resolves the effective timeout
    Then the effective timeout is 120 seconds

  @AC_Q1_8
  Scenario: CPP_MCP_QUERY_TIMEOUT_SECONDS default when unset is 30
    Given the env var CPP_MCP_QUERY_TIMEOUT_SECONDS is unset
    When the server resolves the effective timeout
    Then the effective timeout is 30 seconds

  # ---------------------------------------------------------------------------
  # AC-Q1-4 — IndraDB executor purity (no write symbols)
  # ---------------------------------------------------------------------------

  @AC_Q1_4
  Scenario: IndraDB executor module exports no write symbols
    Given the module cpp_mcp.graphdb.indradb_query_executor is imported with fake indradb
    When the module namespace is inspected for set_ or delete symbols
    Then no such write symbols are present

  # ---------------------------------------------------------------------------
  # AC-Q1-9 / AC-Q1-10 / AC-Q2-8 — Tool registration invariants
  # ---------------------------------------------------------------------------

  @AC_Q1_9 @AC_Q1_10 @AC_Q2_8
  Scenario: Server registers exactly 9 tools including query_graphdb and describe_graph_schema
    Given the MCP server is built via build_server
    When the tool registry is inspected
    Then exactly 9 tools are registered
    And the tool named query_graphdb is present
    And the tool named describe_graph_schema is present

  @AC_Q1_10
  Scenario: No registered tool name starts with cpp_
    Given the MCP server is built via build_server
    When the tool registry is inspected
    Then no registered tool name starts with cpp_

  # ---------------------------------------------------------------------------
  # OQ-Q2-1 — Schema-version mismatch note
  # ---------------------------------------------------------------------------

  @OQ_Q2_1
  Scenario: Schema version mismatch between writer schema and live graph surfaces a warning note
    Given an IndraDB schema introspector with a fake client containing a File vertex stamped with schema version "v0"
    When describe is called on the introspector
    Then the notes list contains a string indicating schema version mismatch
