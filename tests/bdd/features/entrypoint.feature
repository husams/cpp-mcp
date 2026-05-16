Feature: Console-script entrypoint (C-10)

  # SC_C10_ENTRY — console-script entrypoint emits a valid JSON-RPC frame on stdio
  @SC_C10_ENTRY
  Scenario: cpp-mcp console-script entry point starts server on stdio  [C-10, US-M1/AC-1]
    Given cpp-mcp is installed as a console script
    When the cpp-mcp command is run with CPP_MCP_ALLOWED_ROOTS set and an initialize request is sent
    Then a JSON-RPC response frame is received on stdout
    And stderr contains no error lines before the first stdout frame
