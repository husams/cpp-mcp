Feature: Default Flags Fallback (US-9)

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_9_1
  Scenario: build_path None applies default_flags
    Given the file "tiny.cpp" is copied to the default flags root
    When get_definition is called via app with build_path None for that file
    Then the response has flags_source "default"

  @SC_US_9_2
  Scenario: File absent from compile_commands.json falls back to default
    Given the file "tiny.cpp" is copied to the default flags root
    And an empty build directory exists in the allowed root
    When get_definition is called via app with that build_path for that file
    Then the response has flags_source "default"

  @SC_US_9_4
  Scenario: Default flags are configurable at startup
    Given the server config has DEFAULT_FLAGS set to "-std=c++17"
    Then the config default_flags contains "-std=c++17"
