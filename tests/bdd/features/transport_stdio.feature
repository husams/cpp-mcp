Feature: Transport — stdio (US-14)

  @SC_US_14_1
  Scenario: stdio server responds with initialize result
    Given the server subprocess is started in stdio mode with a temp allowed root
    When the client sends initialize
    Then the initialize response is received successfully

  @SC_US_14_3
  Scenario: stdio server exposes all 7 tools
    Given the server subprocess is started in stdio mode with a temp allowed root
    When the client sends initialize
    And the client calls tools/list
    Then the tools list contains "cpp_get_definition"
    And the tools list contains "cpp_get_references"
    And the tools list contains "cpp_get_type_info"
    And the tools list contains "cpp_get_ast"
    And the tools list contains "cpp_get_header_info"
    And the tools list contains "cpp_get_preprocessor_state"
    And the tools list contains "cpp_export_to_graphdb"

  @SC_US_14_4
  Scenario: server starts without orchestration system
    Given the server subprocess is started in stdio mode with a temp allowed root
    When the client sends initialize
    Then the initialize response is received successfully

  @SC_US_14_CALL_ENVELOPE
  Scenario: tools/call with path-traversal input returns error envelope not raw traceback [SC-US-13-2]
    Given the server subprocess is started in stdio mode with a temp allowed root
    When the client calls cpp_get_definition with a path-traversal file_path
    Then the response is a structured error envelope
    And the envelope code is "PATH_VIOLATION"
    And the envelope message does not contain "Traceback"
    And the envelope contains a request_id field
