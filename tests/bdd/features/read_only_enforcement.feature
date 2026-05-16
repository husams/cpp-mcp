Feature: Read-Only Enforcement (US-11)

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_11_1
  Scenario: Navigation tools make no filesystem writes
    Given the file "tiny.cpp" is copied to the read-only root
    And the mtime of that file is recorded
    When cpp_get_definition is called via the app for that file at line 1 col 5
    Then no error envelope is returned
    And the mtime of that file is unchanged

  @SC_US_11_1_ALL_TOOLS
  Scenario Outline: All navigation tools make no filesystem writes [SC-US-11-1]
    Given the file "tiny.cpp" is copied to the read-only root
    And the mtime of that file is recorded
    When <tool_name> is called via the app for that file
    Then the mtime of that file is unchanged

    Examples:
      | tool_name                  |
      | cpp_get_definition         |
      | cpp_get_references         |
      | cpp_get_type_info          |
      | cpp_get_ast                |
      | cpp_get_header_info        |
      | cpp_get_preprocessor_state |

  @SC_US_11_3
  Scenario: No write-back tool endpoint is exposed
    Given the app is built
    Then the app tool list does not contain a tool named "write_file"
    And the app tool list does not contain a tool named "patch_source"
