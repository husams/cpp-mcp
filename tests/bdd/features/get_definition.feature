Feature: get_definition — Navigate to symbol definition

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_1_1
  Scenario: Happy path — definition found in same file
    Given the file "definition_test.cpp" is copied to the allowed root
    When get_definition is called with that file at line 4 col 5
    Then the response contains definition_found true
    And the response contains a non-empty usr
    And the file field is an absolute path

  @SC_US_1_5
  Scenario: FILE_NOT_FOUND when file_path does not exist
    When get_definition is called with a non-existent file at line 1 col 1
    Then the response code is "FILE_NOT_FOUND"
    And no stack trace is exposed

  @SC_US_1_6
  Scenario: INVALID_POSITION when line is beyond end of file
    Given the file "definition_test.cpp" is copied to the allowed root
    When get_definition is called with that file at line 9999 col 1
    Then the response code is "INVALID_POSITION"

  @SC_US_1_7
  Scenario: INVALID_POSITION when col is beyond end of line
    Given the file "definition_test.cpp" is copied to the allowed root
    When get_definition is called with that file at line 4 col 9999
    Then the response code is "INVALID_POSITION"

  @SC_US_1_9
  Scenario: PATH_VIOLATION for path-traversal in file_path
    When get_definition is called with file_path "../../etc/passwd" at line 1 col 1
    Then the response code is "PATH_VIOLATION"

  @SC_US_1_10
  Scenario: definition_found false for forward-declared symbol with no reachable definition
    Given the file "forward_decl.cpp" is copied to the allowed root
    When get_definition is called with that file at line 4 col 8
    Then the response contains definition_found false
    And no error code is returned

  @SC_US_1_11
  Scenario: PATH_VIOLATION for path-traversal in build_path
    Given the file "definition_test.cpp" is copied to the allowed root
    When get_definition is called with that file and bad build_path "../../etc" line 4 col 5
    Then the response code is "PATH_VIOLATION"

  @SC_US_1_14
  Scenario: Symbol at a macro expansion site — no error thrown
    Given the file "macro_test.cpp" is copied to the allowed root
    When get_definition is called with that file at line 8 col 12
    Then the response either has definition_found true or definition_found false
    And no error code is returned
