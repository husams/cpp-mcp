Feature: Stateless Build Context (US-8)

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_8_1
  Scenario: Two calls with different build_paths use independent flags
    Given the file "tiny.cpp" is in the allowed root for stateless test
    When cpp_get_definition is called via app with build_path None for that file
    Then the response has flags_source "default"
    When cpp_get_definition is called via app with a non-existent build_path for that file
    Then the response has flags_source "default"

  @SC_US_8_4
  Scenario: No global project root endpoint is exposed
    Given the app is built
    Then the app tool list does not contain a tool named "set_project_root"
    And the app tool list does not contain a tool named "set_build_path"
