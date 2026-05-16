Feature: Transport — HTTP (Story S6 / US-M2)

  @SC_USM2_1
  Scenario: HTTP transport responds on /mcp endpoint [US-M2/AC-1]
    Given the server is started in http mode on a free port
    When an MCP client initializes over the HTTP transport
    Then the initialize response is valid
    And the HTTP server exposes all 7 tools

  @SC_USM2_4
  Scenario: GET /health returns 200 OK when HTTP transport is active [US-M2/AC-4]
    Given the server is started in http mode on a free port
    When an HTTP GET request is sent to "/health"
    Then the health response status is 200
    And the health response body is "OK"
