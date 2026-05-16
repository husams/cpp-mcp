Feature: cpp_get_ast — Retrieve scoped annotated AST subtree (US-4)

  Background:
    Given the server is configured with a temp allowed root
    And the fixture file "ast_test.cpp" exists in the allowed root

  @SC_US_4_1 @libclang
  Scenario: Happy path JSON AST returned
    When cpp_get_ast is called with format="json"
    Then the response contains a root node with kind and children fields
    And each node contains kind, spelling, usr, type, storage_class fields
    And each node contains start_line, start_col, end_line, end_col fields

  @SC_US_4_2 @libclang
  Scenario: Graph format AST returned
    When cpp_get_ast is called with format="graph"
    Then the response contains nodes and edges lists
    And all edge_type values are in CHILD TYPE_REF CALL

  @SC_US_4_3 @libclang
  Scenario: Depth truncation at specified depth 2
    When cpp_get_ast is called with format="json" and depth=2
    Then the returned tree has at most 2 levels of nesting
    And any node at max depth that has children carries truncated=true

  @SC_US_4_4 @libclang
  Scenario: Default depth of 3 applied when depth not specified
    When cpp_get_ast is called with format="json" and no depth
    Then the returned tree has at most 3 levels of nesting

  @SC_US_4_5 @libclang
  Scenario: Line range filtering — only overlapping nodes returned
    When cpp_get_ast is called with start_line=1 and end_line=10
    Then all returned AST node source ranges overlap lines 1 to 10

  @SC_US_4_6 @libclang
  Scenario: Partial AST with parse error list for file with missing include
    Given the fixture file "broken_partial.cpp" exists in the allowed root
    When cpp_get_ast is called on "broken_partial.cpp" with format="json"
    Then the response includes parse_errors list that is non-empty
    And no top-level error code is returned

  @SC_US_4_7
  Scenario: FILE_NOT_FOUND for non-existent file
    When cpp_get_ast is called on a non-existent file
    Then the response has code FILE_NOT_FOUND

  @SC_US_4_8
  Scenario: INVALID_RANGE when start_line greater than end_line
    When cpp_get_ast is called with start_line=30 and end_line=10
    Then the response has code INVALID_RANGE

  @SC_US_4_9
  Scenario: PATH_VIOLATION for path-traversal in file_path
    When cpp_get_ast is called with file_path "../../etc/passwd"
    Then the response has code PATH_VIOLATION

  @SC_US_4_10 @libclang
  Scenario: Default flags when build_path is None
    When cpp_get_ast is called with no build_path
    Then the response includes flags_source equal to default
