Feature: get_header_info — Inspect include graph and exported symbols (US-5)

  Background:
    Given the server is configured with a temp allowed root
    And the fixture file "header_api.h" exists in the allowed root
    And the fixture file "header_standalone.h" exists in the allowed root

  @SC_US_5_1 @libclang
  Scenario: Happy path full header info returned
    When get_header_info is called on "header_api.h"
    Then the response contains all header info fields

  @SC_US_5_2 @libclang
  Scenario: Header with no includes returns empty include lists
    Given the fixture file "header_standalone.h" exists in the allowed root
    When get_header_info is called on "header_standalone.h"
    Then direct_includes is empty and transitive_includes is empty
    And no error code is returned

  @SC_US_5_3 @libclang
  Scenario: Unresolvable include appears in missing_includes
    Given the fixture file "header_missing_include.h" exists in the allowed root
    When get_header_info is called on "header_missing_include.h"
    Then missing_includes contains the unresolvable header name
    And no error code is returned

  @SC_US_5_4 @libclang
  Scenario: Unreferenced include appears in orphaned_includes
    When get_header_info is called on "header_api.h"
    Then orphaned_includes contains "header_standalone.h"
    And no error code is returned

  @SC_US_5_5 @libclang
  Scenario: Default flags when build_path is None
    When get_header_info is called on "header_standalone.h" with no build_path
    Then the response includes flags_source equal to default

  @SC_US_5_6
  Scenario: FILE_NOT_FOUND for non-existent file
    When get_header_info is called on a non-existent file
    Then the response has code FILE_NOT_FOUND

  @SC_US_5_7
  Scenario: PATH_VIOLATION for path-traversal in file_path
    When get_header_info is called with file_path "../../etc/hosts"
    Then the response has code PATH_VIOLATION
