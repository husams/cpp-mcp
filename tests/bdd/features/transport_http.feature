Feature: Transport — HTTP (Story 7b / US-14)

  @SC_US_14_2
  Scenario: HTTP transport responds on /mcp endpoint [US-14/AC-2]
    Given the server is started in http mode on a free port
    When an MCP client initializes over the HTTP transport
    Then the initialize response is valid
    And the HTTP server exposes all 7 tools
