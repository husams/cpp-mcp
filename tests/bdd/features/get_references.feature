Feature: get_references — Find all symbol usages

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_2_1
  Scenario: Happy path — references returned for a defined symbol
    Given the file "references_test.cpp" is copied to the allowed root
    When get_references is called with that file at line 4 col 5
    Then the response contains a references list
    And each reference has file line col and context_snippet fields

  @SC_US_2_2
  Scenario: Zero references returns empty list — not an error
    Given the file "definition_test.cpp" is copied to the allowed root
    When get_references is called with that file at line 14 col 5
    Then the references list is empty
    And no error code is returned

  @SC_US_2_4
  Scenario: FILE_NOT_FOUND for non-existent file
    When get_references is called with a non-existent file at line 1 col 1
    Then the response code is "FILE_NOT_FOUND"

  @SC_US_2_5
  Scenario: INVALID_POSITION for out-of-range line
    Given the file "references_test.cpp" is copied to the allowed root
    When get_references is called with that file at line 9999 col 1
    Then the response code is "INVALID_POSITION"

  @SC_US_2_6
  Scenario: PATH_VIOLATION for path-traversal in file_path
    When get_references is called with file_path "../secret/passwords.cpp" at line 1 col 1
    Then the response code is "PATH_VIOLATION"
