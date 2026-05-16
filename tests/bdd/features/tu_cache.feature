Feature: TU Cache with LRU Eviction (US-10)

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_10_1
  Scenario: Cache hit on second call for same file
    Given the file "tiny.cpp" is in the allowed root for cache test
    When cpp_get_definition is called via app twice for the same file
    Then the second response has cache_hit true

  @SC_US_10_2
  Scenario: Cache miss on first call for new file
    Given the file "tiny.cpp" is in the allowed root for cache test
    When cpp_get_definition is called via app once for that file
    Then the response has cache_hit false

  @SC_US_10_4
  Scenario: Cache stats are exposed in tool responses
    Given the file "tiny.cpp" is in the allowed root for cache test
    When cpp_get_definition is called via app once for that file
    Then the session exposes cache stats with cache_size and cache_capacity

  @SC_US_10_6
  Scenario: Cache capacity is configurable at startup
    Given the server config has CACHE_CAPACITY set to 64
    Then the config cache_capacity is 64
