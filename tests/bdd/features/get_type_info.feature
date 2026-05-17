Feature: get_type_info — Retrieve type details for a symbol

  Background:
    Given the MCP server is configured with a temp allowed root

  @SC_US_3_1
  Scenario: Happy path — full type info for a concrete type
    Given the file "types_test.cpp" is copied to the allowed root
    When get_type_info is called with that file at line 5 col 5
    Then the response contains display_type canonical_type size_bytes alignment_bytes is_pod is_const is_reference is_pointer
    And size_bytes and alignment_bytes are non-null integers

  @SC_US_3_2
  Scenario: Auto-typed variable resolves to concrete canonical type
    Given the file "types_test.cpp" is copied to the allowed root
    When get_type_info is called with that file at line 8 col 6
    Then canonical_type is not "auto"
    And canonical_type is "float"

  @SC_US_3_3
  Scenario: Template instantiation shows expanded type
    Given the file "types_test.cpp" is copied to the allowed root
    When get_type_info is called with that file at line 18 col 10
    Then display_type contains "Box"
    And canonical_type is not "auto"

  @SC_US_3_4
  Scenario: Incomplete type returns null size and alignment — not an error
    Given the file "types_test.cpp" is copied to the allowed root
    When get_type_info is called with that file at line 21 col 8
    Then size_bytes is null
    And alignment_bytes is null
    And no error code is returned

  @SC_US_3_6
  Scenario: FILE_NOT_FOUND for non-existent file
    When get_type_info is called with a non-existent file at line 1 col 1
    Then the response code is "FILE_NOT_FOUND"

  @SC_US_3_7
  Scenario: INVALID_POSITION for out-of-range position
    Given the file "types_test.cpp" is copied to the allowed root
    When get_type_info is called with that file at line 0 col 0
    Then the response code is "INVALID_POSITION"

  @SC_US_3_8
  Scenario: PATH_VIOLATION for path-traversal in file_path
    When get_type_info is called with file_path "../../etc/shadow" at line 1 col 1
    Then the response code is "PATH_VIOLATION"
