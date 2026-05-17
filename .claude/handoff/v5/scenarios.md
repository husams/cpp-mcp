# Requirements

## In-scope

- Rename seven MCP tool wire names per the table in requirements.md (US-V5-R1).
- Update all test call sites and BDD file names to the new names (US-V5-R2).
- Update README, ADRs 16-18, and wiki pages to the new names (US-V5-R3).
- Bump version 0.2.0 → 0.3.0 and ship CHANGELOG.md with the migration table (US-V5-R4).
- Verify clients calling old names receive standard MCP "tool not found" — no compatibility aliases (AC-R4-3).

## Out-of-scope

- New query-side tools (`query_graphdb`, `translate_query`) — S1/S2 in the CodexGraph-gap roadmap.
- Schema changes (S3 `access_kind`, S4 FIELD/GLOBAL_VARIABLE split).
- Compatibility aliases for old tool names.
- Behavioral changes to argument shapes, return shapes, error codes, or graph wire format.

## Assumptions

- `assumed` — AC-R4-3 ("no compatibility aliases") dominates the AC-R2-4 parenthetical "migration shim from US-V5-R4 (if any)". The shim exception clause in the grep gate is dead. The grep in AC-R2-4 must find zero hits in `src/` and `tests/`, excepting only changelog and README.
- `assumed` — "cache keys untouched" in the NFR means the cache schema (key structure and arguments) is untouched, not the tool-name string embedded in any key. See Open Questions.
- `assumed` — The parity gate counts are exactly 618 pass / 6 skip (unit) and 18 pass (integration, `-m integration`), sourced from the v4 baseline in `project_v4_e2e_tests_shipped.md`.

## Open questions

1. `needs-clarification` (OQ-1) — **Cache keys.** The NFR states "cache keys … untouched." If the LRU translation-unit or result cache embeds the tool name as part of the key, the rename changes the key by definition. Does "untouched" mean "cache schema/arguments untouched" (tool name not a cache dimension), or does it require explicit verification that no tool-name string appears in any cache key? Architect must clarify before implementation.

2. `needs-clarification` (OQ-2) — **Source file paths.** AC-R1-2 requires the Python function/module symbol for `export_to_graphdb` to rename to `ingest_code`. It is silent on whether the source file `src/cpp_mcp/tools/export_to_graphdb.py` also renames, and whether the other six tool source files (named after the old `cpp_`-prefixed identifiers) rename. A partial rename (symbol only, file path unchanged) is observable and should be explicitly decided. Architect must confirm scope.

3. `needs-clarification` (OQ-3) — **Grep scope vs exception list.** AC-R2-4 runs `grep -RE 'cpp_(get|export)_' src/ tests/` but lists exceptions for changelog and README, which are outside the grep's target directories. Either the grep should be broadened to the repo root (excluding changelog/README explicitly), or the exception list is vacuous. QA must confirm the authoritative gate command.

## Edge cases

| ID | Description | Tag |
|----|-------------|-----|
| EC-1 | Client calls any of the 7 old `cpp_*` names post-rename; receives MCP "tool not found" | confirmed |
| EC-2 | Registry exposes exactly 7 tools (not 6, not 8) | confirmed |
| EC-3 | No registered tool name contains the substring `cpp_` | confirmed |
| EC-4 | `ingest_code` Python symbol renamed (not only the wire name) | confirmed |
| EC-5 | `grep -RE 'cpp_(get|export)_' src/ tests/` returns zero hits | confirmed |
| EC-6 | pytest unit count 618 pass / 6 skip, integration 18 pass — exact parity | confirmed |
| EC-7 | Error envelope wording in `DEPENDENCY_MISSING` uses new tool names | confirmed |
| EC-8 | ADR-16/17/18 inline notes added; historical old-name references not erased | confirmed |
| EC-9 | Cache key dimensions unchanged if tool name is not a cache key component (pending OQ-1) | needs-clarification |
| EC-10 | Source file path for `export_to_graphdb` module renames (pending OQ-2) | needs-clarification |

## Stakeholders

- MCP client authors — breaking change; must update client configs from `cpp_*` to new names.
- Project maintainers — test parity and grep gate are hard quality gates.
- Wiki readers / doc consumers — README migration table and wiki updates.

---

# Gherkin

```gherkin
Feature: v5 Tool Rename — drop cpp_ prefix and rename export_to_graphdb to ingest_code

  # =========================================================
  # US-V5-R1: Rename tool wire names in the server registry
  # =========================================================

  @AC-R1-1 @AC-R1-4
  Scenario Outline: Each renamed tool is registered under its new wire name
    Given the MCP server is running at version 0.3.0
    When a client requests the list of registered tools
    Then the tool "<new_name>" is present in the registry
    And  the tool "<old_name>" is absent from the registry

    Examples:
      | old_name                  | new_name                  |
      | cpp_get_ast               | get_ast                   |
      | cpp_get_definition        | get_definition            |
      | cpp_get_references        | get_references            |
      | cpp_get_type_info         | get_type_info             |
      | cpp_get_header_info       | get_header_info           |
      | cpp_get_preprocessor_state | get_preprocessor_state   |
      | cpp_export_to_graphdb     | ingest_code               |

  @AC-R1-4
  Scenario: Registry exposes exactly seven tools after rename
    Given the MCP server is running at version 0.3.0
    When a client requests the list of registered tools
    Then the registry contains exactly 7 tools
    And  no registered tool name contains the substring "cpp_"

  @AC-R1-2
  Scenario: ingest_code Python symbol is renamed (not only the wire name)
    Given the source file for the graphdb ingestion tool
    When the module is imported
    Then the callable is accessible as "ingest_code"
    And  no callable named "cpp_export_to_graphdb" is exposed by that module

  @AC-R1-3
  Scenario: Schema fixtures and expected-tool-descriptions reflect new names
    Given the files under "tests/fixtures/expected_schemas/" and "tests/fixtures/expected_tool_descriptions.py"
    When the fixture content is inspected
    Then every tool name in the fixtures matches the new names from the rename table
    And  no fixture entry contains a name prefixed with "cpp_"

  @AC-R1-5
  Scenario: DEPENDENCY_MISSING error envelope uses new tool names
    Given a request that triggers a DEPENDENCY_MISSING error
    When the error envelope is returned
    Then the error message references the new tool name (e.g. "ingest_code")
    And  the error message does not reference any old "cpp_" prefixed name

  # =========================================================
  # US-V5-R2: Update all tests to call tools by new names
  # =========================================================

  @AC-R2-1
  Scenario: No test file calls a tool by an old cpp_ name
    Given the test suite under "tests/"
    When all "client.call_tool(...)" invocations are scanned
    Then no call site uses a name matching the pattern "cpp_(get|export)_"

  @AC-R2-2
  Scenario: BDD feature files and step modules are renamed per the mapping
    Given the BDD test directory "tests/bdd/"
    When the file listing is inspected
    Then a file named "test_ingest_code.py" exists
    And  a file named "test_ingest_code_indradb.py" exists
    And  no file named "test_export_to_graphdb.py" exists
    And  no file named "test_export_to_indradb.py" exists

  @AC-R2-3
  Scenario: pytest unit suite maintains exact v4 parity after rename
    Given the renamed codebase with no other behavioral changes
    When "uv run pytest" is executed without the integration marker
    Then the result is exactly 618 passed and 6 skipped
    And  zero tests are newly failing or newly erroring relative to the v4 baseline

  @AC-R2-3
  Scenario: pytest integration suite maintains exact v4 parity after rename
    Given the renamed codebase with accessible graphdb backends
    When "uv run pytest -m integration" is executed
    Then the result is exactly 18 passed
    And  zero tests are newly failing or newly erroring relative to the v4 baseline

  @AC-R2-4 @EC-5
  Scenario: grep gate — no cpp_ prefix survives in src/ or tests/
    Given the renamed source tree
    When "grep -RE 'cpp_(get|export)_' src/ tests/" is executed
    Then the command returns exit code 1 (no matches found)

  # =========================================================
  # US-V5-R3: Update documentation and wiki
  # =========================================================

  @AC-R3-1
  Scenario: README lists new tool names and includes a migration table
    Given "README.md" at the project root
    When the document is read
    Then a section headed "Migration from 0.2.x" (or equivalent) is present
    And  the section contains a table mapping each old name to its new name
    And  all tool-name references outside the migration table use the new names

  @AC-R3-2
  Scenario: ADRs 16-18 annotate old names with inline rename notes
    Given the files "adr-16.md", "adr-17.md", and "adr-18.md" in the handoff dir or project docs
    When each file is read
    Then any occurrence of an old tool name in body text is accompanied by an inline note of the form "(renamed to `<new_name>` in v5)"
    And  historical context sentences that describe v3/v4 behavior are not rewritten

  @AC-R3-3
  Scenario: Wiki page cpp-mcp.md reflects new tool names
    Given "~/workspace/wiki/pages/code/cpp-mcp.md"
    When the page is read
    Then all seven tool names in the page match the new names
    And  the page version reference indicates v0.3.0

  @AC-R3-3
  Scenario: Wiki page cpp-mcp-v4.md carries a rename notice
    Given "~/workspace/wiki/pages/code/cpp-mcp-v4.md"
    When the page is read
    Then a note is present stating that tool names were renamed in v5

  @AC-R3-3
  Scenario: Wiki planning page reaffirms unprefixed future tool names
    Given "~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md"
    When the S1 and S2 proposed tool names are read
    Then the names are "query_graphdb" and "translate_query"
    And  no proposed future tool name carries the "cpp_" prefix

  @AC-R3-4
  Scenario: wiki index.md description lines reference v0.3.0 and new names
    Given "~/workspace/wiki/index.md"
    When the entry lines for cpp-mcp pages are read
    Then at least one entry references "v0.3.0"
    And  no entry uses old "cpp_" prefixed tool names in a current-state description

  # =========================================================
  # US-V5-R4: Version bump and changelog
  # =========================================================

  @AC-R4-1
  Scenario: pyproject.toml version is 0.3.0
    Given "pyproject.toml" at the project root
    When the version field is read
    Then the value is "0.3.0"

  @AC-R4-2
  Scenario: CHANGELOG.md documents the rename with the full old-to-new table
    Given "CHANGELOG.md" at the project root (created if absent)
    When the changelog is read
    Then a version entry for "0.3.0" is present
    And  the entry contains a table mapping each old tool name to its new name
    And  the entry contains a rationale sentence linking to "pages/planning/cpp-mcp-codexgraph-gap"

  @AC-R4-3 @EC-1
  Scenario Outline: Client calling an old tool name receives MCP tool-not-found
    Given the MCP server is running at version 0.3.0 with no compatibility aliases
    When a client calls tool "<old_name>" with any valid argument payload
    Then the server returns the standard MCP error for an unknown tool name
    And  the response does not contain a successful result payload

    Examples:
      | old_name                   |
      | cpp_get_ast                |
      | cpp_get_definition         |
      | cpp_get_references         |
      | cpp_get_type_info          |
      | cpp_get_header_info        |
      | cpp_get_preprocessor_state |
      | cpp_export_to_graphdb      |

  # =========================================================
  # Negative paths and boundary conditions
  # =========================================================

  @EC-6
  Scenario: Test count does not increase beyond baseline (no phantom test additions)
    Given the renamed codebase
    When "uv run pytest --collect-only -q" is executed
    Then the collected test count equals 624 (618 pass + 6 skip items)
    And  no duplicate test IDs are reported

  @EC-7
  Scenario: Tool argument shapes are unchanged after rename
    Given the server at version 0.3.0
    When a client retrieves the JSON schema for tool "get_ast"
    Then the inputSchema is identical to the v4 schema for "cpp_get_ast"
    And  no new required or optional parameters have been added or removed

  @EC-8 @AC-R3-2
  Scenario: No historical ADR claim is silently rewritten
    Given ADR-16, ADR-17, and ADR-18 before and after the v5 rename edit
    When a diff of each file is produced
    Then no sentence describing a factual past event has been deleted or paraphrased
    And  only additive inline "(renamed to … in v5)" annotations appear as changes
```

---

# References

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/requirements.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/requirements-raw.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v5/CHARTER.md`
- `[[pages/code/cpp-mcp]]` — current code wiki page
- `[[pages/code/cpp-mcp-v4]]` — v4 delta page (618 unit + 18 integration baseline)
- `[[pages/planning/cpp-mcp-codexgraph-gap]]` — S1/S2 future tool names
- `project_v4_e2e_tests_shipped.md` — test count baseline source
- Cognee tags: `task:cpp-mcp-v5-rename`, `role:business-analyst`
