Feature: cpp_export_to_graphdb — Export AST and symbol relationships to graph DB (US-7)

  Background:
    Given the MCP server is running with allowed root for graphdb export
    And a fake graph database driver is installed

  @SC_US_7_1
  Scenario: Happy path — single file exported successfully [US-7/AC-1, US-7/AC-2]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with that file and a build path
    Then the response contains files_processed equal to 1
    And the response contains no errors
    And graph node types include File

  @SC_US_7_2
  Scenario: DB_UNREACHABLE when db_uri is not reachable [US-7/AC-3]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    And the graph database driver will fail to connect
    When cpp_export_to_graphdb is called with file "main.cpp" and unreachable db_uri
    Then the response code is "DB_UNREACHABLE"
    And no source files are modified

  @SC_US_7_3
  Scenario: Directory input processes all supported C++ file extensions [US-7/AC-4]
    Given the allowed root directory contains C++ files and non-C++ files
    When cpp_export_to_graphdb is called with the directory as input
    Then only C++ files are processed
    And README.md and build.py are not processed

  @SC_US_7_4
  Scenario: Partial failure — successful files committed, failures listed [US-7/AC-5]
    Given the allowed root contains "good.cpp" and "broken.cpp" where broken will fail
    When cpp_export_to_graphdb is called with the directory
    Then files_processed is at least 1
    And the errors list contains an entry for broken.cpp
    And no all-or-nothing rollback occurs

  @SC_US_7_5
  Scenario: FILE_NOT_FOUND for non-existent file_path_or_dir [US-7/AC-6]
    When cpp_export_to_graphdb is called with a non-existent file path
    Then the response code is "FILE_NOT_FOUND"

  @SC_US_7_6
  Scenario: PATH_VIOLATION for path-traversal in file_path_or_dir [US-7/AC-7]
    When cpp_export_to_graphdb is called with file_path_or_dir containing path traversal
    Then the response code is "PATH_VIOLATION"
    And no database write occurs

  @SC_US_7_7
  Scenario: PATH_VIOLATION for path-traversal in build_path [US-7/AC-7]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with build_path containing path traversal
    Then the response code is "PATH_VIOLATION"
    And no database write occurs

  @SC_US_7_8
  Scenario: Read-only enforcement — no source file modified during export [US-7/AC-8]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with that file and a build path
    Then the mtime of "main.cpp" is unchanged after the call
    And no new files exist in the allowed root after the call

  @SC_US_7_9
  Scenario: INVALID_ARGUMENT when db_uri is absent [US-7/AC-9]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called without a db_uri
    Then the response code is "INVALID_ARGUMENT"
    And the message identifies "db_uri"

  @SC_US_7_10
  Scenario: INVALID_ARGUMENT when build_path is absent [US-7/AC-9]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called without a build_path
    Then the response code is "INVALID_ARGUMENT"
    And the message identifies "build_path"

  @SC_US_7_11
  Scenario: INVALID_ARGUMENT when db_uri is empty string [US-7/AC-9]
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When cpp_export_to_graphdb is called with an empty db_uri
    Then the response code is "INVALID_ARGUMENT"
