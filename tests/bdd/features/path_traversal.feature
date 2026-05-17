Feature: Path Traversal Validation (US-12)

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_12_1
  Scenario: PATH_VIOLATION for dot-dot in file_path
    When get_definition is called via the app with path "../../etc/passwd" line 1 col 1
    Then the response has code "PATH_VIOLATION"

  @SC_US_12_2
  Scenario: PATH_VIOLATION for dot-dot in build_path
    Given the file "tiny.cpp" is copied to the path traversal root
    When get_definition is called with that file and bad build_path "../../etc"
    Then the response has code "PATH_VIOLATION"

  @SC_US_12_4
  Scenario: Absolute path within allowed root passes validation
    Given the file "tiny.cpp" is copied to the path traversal root
    When get_ast is called via the app for that file
    Then no error envelope is returned

  @SC_US_12_5
  Scenario: Server refuses to start without ALLOWED_ROOTS
    When load_config is called with no ALLOWED_ROOTS set
    Then a ConfigError is raised

  @SC_US_12_6
  Scenario: Absolute path outside allowed root is rejected
    When get_definition is called via the app with path "/home/user/secret.cpp" line 1 col 1
    Then the response has code "PATH_VIOLATION"
