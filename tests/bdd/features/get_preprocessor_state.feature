Feature: get_preprocessor_state — Retrieve macro definitions and conditional state (US-6)

  Background:
    Given the server is configured with a temp allowed root
    And the fixture file "config_macros.cpp" exists in the allowed root

  @SC_US_6_1 @libclang
  Scenario: Happy path macros and conditionals returned
    When get_preprocessor_state is called on "config_macros.cpp"
    Then the response contains macros and conditionals lists
    And macros list has at least one entry with name and value fields

  @SC_US_6_2 @libclang
  Scenario: Macro from -D flag appears with defined_at null
    When get_preprocessor_state is called on "config_macros.cpp" with flags including "-DDEBUG=1"
    Then the macros list includes an entry with name "DEBUG" and defined_at null

  @SC_US_6_3 @libclang
  Scenario: ifdef block conditional evaluated correctly
    When get_preprocessor_state is called on "config_macros.cpp"
    Then the conditionals list includes an entry with directive starting with #ifdef or #ifndef

  @SC_US_6_4 @libclang
  Scenario: File with no macros or conditionals returns empty lists
    Given the fixture file "ast_test.cpp" exists in the allowed root
    When get_preprocessor_state is called on "ast_test.cpp"
    Then macros may be empty or contain built-ins only
    And no error code is returned

  @SC_US_6_5 @libclang
  Scenario: Default flags when build_path is None
    When get_preprocessor_state is called on "config_macros.cpp" with no build_path
    Then the response includes flags_source equal to default

  @SC_US_6_6
  Scenario: FILE_NOT_FOUND for non-existent file
    When get_preprocessor_state is called on a non-existent file
    Then the response has code FILE_NOT_FOUND

  @SC_US_6_7
  Scenario: PATH_VIOLATION for path-traversal in file_path
    When get_preprocessor_state is called with file_path "../../etc/environment"
    Then the response has code PATH_VIOLATION
