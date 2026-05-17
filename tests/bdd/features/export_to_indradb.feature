Feature: IndraDB BDD export coverage
  # US-G5: ingest_code end-to-end with IndraDB, fake-driver unconditional,
  # live-daemon gated on INDRADB_TEST_URI.

  Background:
    Given the MCP server is running with allowed root for graphdb export
    And a fake IndraDB driver is installed as the IndraDB backend

  # covers: US-G5/AC-1 (connect and single-file export — fake driver)
  @SC_US_G5_1
  Scenario: Export a single C++ file to IndraDB via fake driver succeeds
    Given a valid C++ source file "main.cpp" exists in the allowed root
    When ingest_code is called with that file and an indradb:// URI
    Then the response contains files_processed equal to 1
    And the response contains no errors
    And graph node types include File

  # covers: US-G5/AC-1, US-G5/AC-5 (idempotent re-export — fake driver)
  @SC_US_G5_2
  Scenario: Re-exporting the same file to IndraDB produces the same node count
    Given a valid C++ source file "main.cpp" exists in the allowed root
    And the fake IndraDB driver uses an idempotent upsert store
    When ingest_code is called with that file and an indradb:// URI
    And ingest_code is called again with the same file and URI
    Then the node count after the second run equals the node count after the first run
    And the edge count after the second run equals the edge count after the first run

  # covers: US-G5/AC-1 (unreachable-daemon error path — fake driver)
  @SC_US_G5_3
  Scenario: Export to IndraDB with unreachable daemon returns DB_UNREACHABLE
    Given a valid C++ source file "main.cpp" exists in the allowed root
    And the fake IndraDB driver is configured to fail on connect
    When ingest_code is called with that file and an indradb:// URI
    Then the response code is "DB_UNREACHABLE"
    And no database write occurs

  # covers: US-G5/AC-4 (URI dispatch table — all advertised schemes, no daemon)
  @SC_US_G5_4
  Scenario Outline: select_driver dispatch table covers all IndraDB-advertised schemes
    Given a fake IndraDB driver class is registered
    When select_driver is called with "<uri>"
    Then the returned driver is an instance of IndraDBDriver
    And no gRPC connection is attempted

    Examples:
      | uri                            |
      | indradb://localhost:27615      |
      | grpc://localhost:27615         |
      | indradb+grpc://localhost:27615 |

  # covers: US-G5/AC-5 (path validation mirrors test_export_to_graphdb.py)
  @SC_US_G5_5
  Scenario: Path traversal in file_path_or_dir with indradb URI returns PATH_VIOLATION
    Given the fake IndraDB driver is installed
    When ingest_code is called with file_path_or_dir "../../etc/passwd" and an indradb:// URI
    Then the response code is "PATH_VIOLATION"
    And no database write occurs

  # covers: US-G5/AC-5 (missing file)
  @SC_US_G5_6
  Scenario: Non-existent file with indradb URI returns FILE_NOT_FOUND
    Given the fake IndraDB driver is installed
    When ingest_code is called with a non-existent file and an indradb:// URI
    Then the response code is "FILE_NOT_FOUND"
    And no database write occurs

  # covers: US-G5/AC-1, US-G5/AC-2 (live daemon — gated on INDRADB_TEST_URI)
  @indradb
  Scenario: Export a C++ file to a real IndraDB daemon and verify node exists
    Given INDRADB_TEST_URI is set in the environment
    And a valid C++ source file "main.cpp" exists in the allowed root
    When ingest_code is called with that file and the INDRADB_TEST_URI
    Then the response contains files_processed equal to 1
    And the response contains no errors
    And the live IndraDB database contains at least one File node

  # covers: US-G5/AC-1 (idempotent re-export — live daemon)
  @indradb
  Scenario: Re-exporting to a real IndraDB daemon is idempotent
    Given INDRADB_TEST_URI is set in the environment
    And a valid C++ source file "main.cpp" exists in the allowed root
    When ingest_code is called with that file and the INDRADB_TEST_URI
    And the node count is recorded
    And ingest_code is called again with the same file and URI
    Then the node count after the second run equals the recorded count
