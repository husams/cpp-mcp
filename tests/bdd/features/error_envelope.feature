Feature: Structured Error Envelope (US-13)

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_13_1
  Scenario: PATH_VIOLATION error conforms to envelope schema
    When cpp_get_definition is called via the app with path "../../etc/passwd" line 1 col 1
    Then the response has code "PATH_VIOLATION"
    And the response has a non-empty message
    And the response has tool "cpp_get_definition"
    And the response has a request_id

  @SC_US_13_2
  Scenario: INTERNAL_ERROR exposes no stack trace
    When an unexpected exception is injected into the app call
    Then the response has code "INTERNAL_ERROR"
    And the message does not contain a traceback

  @SC_US_13_3
  Scenario: All errors are structured JSON with a code field
    When cpp_get_definition is called via the app with path "../../etc/passwd" line 1 col 1
    Then the response is a dict with a "code" field
    And the code is one of the valid error codes
