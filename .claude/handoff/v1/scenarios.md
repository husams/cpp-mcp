# Scenarios: C++ Semantic Analysis MCP Server
run_id: cpp-mcp-1
stage: business-analyst
date: 2026-05-16
source: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/requirements.md

---

## Requirements Summary

### In-Scope
- 7 MCP tools: cpp_get_definition, cpp_get_references, cpp_get_type_info, cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state, cpp_export_to_graphdb.
- Stateless build context; TU LRU cache; structured error envelope; path-traversal validation; read-only enforcement; stdio and HTTP transports.

### Out-of-Scope
- Persistent index, incremental indexing, refactoring/rename tools, non-C++ languages, authentication, IDE/LSP bridging, Kubernetes deployment.

### Assumptions
- ASM-1 (assumed): "Allowed root" in US-12 means a single directory for v1 pending architect decision on OQ-14.
- ASM-2 (assumed): `PARSE_ERROR` code (listed in US-13/AC-3) is returned when compile_commands.json is malformed or TU parse is entirely unrecoverable with zero AST output. US-4/AC-7 covers the partial-parse case (list, not code).
- ASM-3 (assumed): `build_path` pointing to a non-directory file is treated as `INVALID_ARGUMENT` pending architect confirmation.
- ASM-4 (assumed): Scenario tags (`@SC-US-N-M`) serve as pytest-bdd IDs for traceability to test-report.md.

### Open Questions (forwarded to architect)
- OQ-1: Tool count 9 (dispatch brief) vs. 7 (requirements). No scenarios added for undeclared tools — needs-clarification.
- OQ-2: `flags_source` field placement: per-response vs. metadata envelope — needs-clarification.
- OQ-3: `cpp_get_references` scope: single TU vs. all TUs in compilation DB — needs-clarification.
- OQ-4: AST node count / byte ceiling — needs-clarification.
- OQ-5: `format="graph"` edge type extensibility — needs-clarification.
- OQ-6: "Orphaned include" definition scope — needs-clarification.
- OQ-7: Transitive macro inclusion in cpp_get_preprocessor_state — needs-clarification.
- OQ-8/OQ-9/OQ-10: GraphDB target, idempotency, recursive scope — needs-clarification.
- OQ-11: Concurrency model / libclang thread-safety — needs-clarification.
- OQ-12: Per-call default_flags override — needs-clarification.
- OQ-13: Cache mtime invalidation strategy — needs-clarification.
- OQ-14: Single vs. multiple allowed roots — needs-clarification.
- OQ-15: Symlink handling: follow-and-check vs. deny-all — needs-clarification.
- OQ-16: Partial-success: error envelope vs. warnings field — needs-clarification.
- OQ-17: HTTP authentication in v1 — needs-clarification.
- OQ-NEW-1 (needs-clarification): `build_path` pointing to an existing file (not a directory) — should return INVALID_ARGUMENT or PATH_VIOLATION? No AC covers this case.
- OQ-NEW-2 (needs-clarification): PARSE_ERROR code: returned only when TU parse yields zero AST output, or also for malformed compile_commands.json? US-13/AC-3 lists it but no functional story AC explicitly emits it.

### Edge Cases
- Missing build_path fallback to default_flags — confirmed (US-1/AC-4, US-9/AC-1).
- Path-traversal in file_path and build_path — confirmed (US-12).
- Symlink resolving outside allowed root — confirmed (US-12/AC-3).
- Absolute path within allowed root — confirmed (US-12/AC-4).
- build_path exists but contains no compile_commands.json — confirmed (US-1/AC-7, US-9/AC-2).
- build_path is a non-directory file — needs-clarification (OQ-NEW-1).
- Malformed compile_commands.json — needs-clarification (OQ-NEW-2).
- TU cache hit/miss/eviction — confirmed (US-10).
- TU cache stale on mtime change — confirmed (US-10/AC-6).
- Two build_paths interleaved in the same session — confirmed (US-8/AC-1).
- Symbol at a macro expansion site — assumed (no dedicated AC; INVALID_POSITION or valid result depending on libclang behavior).
- Symbol on auto-typed variable — confirmed (US-3/AC-2).
- AST depth truncation — confirmed (US-4/AC-3).
- AST line range filtering — confirmed (US-4/AC-4).
- start_line > end_line (INVALID_RANGE) — confirmed (US-4/AC-9).
- GraphDB unreachable (DB_UNREACHABLE) — confirmed (US-7/AC-3).
- INTERNAL_ERROR from unexpected server exception — confirmed (US-13/AC-2).
- PARSE_ERROR for totally unrecoverable parse — needs-clarification (OQ-NEW-2).

### Stakeholders
- LLM agent consumers (primary tool callers).
- Operator / server deployer (configures allowed root, cache capacity, default_flags).
- Developer integrator (builds agents against the MCP interface).

---

## Gherkin

Scenario ID convention: `@SC-US-<story>-<n>` as a pytest-bdd tag on each scenario.
AC mapping appears in the scenario title as `[US-N/AC-M]`.

---

### Feature: cpp_get_definition — Navigate to symbol definition (US-1)

```gherkin
Feature: cpp_get_definition

  Background:
    Given the MCP server is running with allowed root "/projects"
    And the file "/projects/src/main.cpp" exists and contains a function definition "foo" at line 10, col 5

  @SC-US-1-1
  Scenario: Happy path — definition found in same file [US-1/AC-1]
    Given build_path "/projects/build" containing "compile_commands.json" listing "/projects/src/main.cpp"
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5
    Then the response contains { file: "/projects/src/main.cpp", line: 10, col: 5, usr: <non-empty string> }
    And "file" is an absolute path

  @SC-US-1-2
  Scenario: Cross-file definition navigation [US-1/AC-2]
    Given the symbol at "/projects/src/caller.cpp" line=5 col=10 is declared in "/projects/include/lib.h" line=3 col=1
    And build_path "/projects/build" contains "compile_commands.json" listing both files
    When cpp_get_definition is called with file_path="/projects/src/caller.cpp" line=5 col=10
    Then the response contains file="/projects/include/lib.h" line=3 col=5
    And file is an absolute path different from the input file_path

  @SC-US-1-3
  Scenario: Compilation DB flags sourced from build_path [US-1/AC-3]
    Given build_path "/projects/build" containing "compile_commands.json" listing "/projects/src/main.cpp" with flags ["-std=c++17", "-DDEBUG"]
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5 build_path="/projects/build"
    Then the response includes flags_source="compilation_db"

  @SC-US-1-4
  Scenario: Default flags fallback when build_path is None [US-1/AC-4, US-9/AC-1]
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5 and build_path=None
    Then the TU is parsed with flags ["-std=c++20", "-I.", "-x", "c++"]
    And the response includes flags_source="default"

  @SC-US-1-5
  Scenario: FILE_NOT_FOUND when file_path does not exist [US-1/AC-5]
    When cpp_get_definition is called with file_path="/projects/src/nonexistent.cpp" line=1 col=1
    Then the response is { code: "FILE_NOT_FOUND", message: <string>, tool: "cpp_get_definition", request_id: <uuid> }
    And no stack trace is exposed

  @SC-US-1-6
  Scenario: INVALID_POSITION when line is beyond end of file [US-1/AC-6]
    Given "/projects/src/main.cpp" has 20 lines
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=999 col=1
    Then the response is { code: "INVALID_POSITION", message: <string>, tool: "cpp_get_definition", request_id: <uuid> }

  @SC-US-1-7
  Scenario: INVALID_POSITION when col is beyond end of line [US-1/AC-6]
    Given "/projects/src/main.cpp" line 10 has 40 characters
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=999
    Then the response is { code: "INVALID_POSITION", message: <string> }

  @SC-US-1-8
  Scenario: Default flags when build_path directory has no compile_commands.json [US-1/AC-7, US-9/AC-2]
    Given build_path "/projects/empty-build" is a directory containing no "compile_commands.json"
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5 build_path="/projects/empty-build"
    Then the response includes flags_source="default"
    And no error is returned

  @SC-US-1-9
  Scenario: PATH_VIOLATION for path-traversal in file_path [US-1/AC-8, US-12/AC-1]
    When cpp_get_definition is called with file_path="../../etc/passwd" line=1 col=1
    Then the response is { code: "PATH_VIOLATION", message: <string>, tool: "cpp_get_definition", request_id: <uuid> }
    And no file I/O is attempted

  @SC-US-1-10
  Scenario: definition_found=false for forward-declared symbol with no reachable definition [US-1/AC-9]
    Given "/projects/src/fwd.cpp" contains only a forward declaration of "Bar" with no definition reachable by libclang
    When cpp_get_definition is called with file_path="/projects/src/fwd.cpp" line=1 col=7
    Then the response includes definition_found=false
    And location is null or empty
    And no error code is returned

  @SC-US-1-11
  Scenario: PATH_VIOLATION for path-traversal in build_path [US-12/AC-2]
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5 build_path="../../etc"
    Then the response is { code: "PATH_VIOLATION" }
    And no file I/O is attempted

  @SC-US-1-12
  Scenario: PATH_VIOLATION for symlink resolving outside allowed root [US-12/AC-3]
    Given "/projects/src/escape.cpp" is a symlink resolving to "/etc/passwd"
    When cpp_get_definition is called with file_path="/projects/src/escape.cpp" line=1 col=1
    Then the response is { code: "PATH_VIOLATION" }

  @SC-US-1-13
  Scenario: build_path pointing to a non-directory file [OQ-NEW-1 — needs-clarification]
    Given "/projects/build/compile_commands.json" is an existing file (not a directory)
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5 build_path="/projects/build/compile_commands.json"
    Then the response is either { code: "INVALID_ARGUMENT" } or { code: "PATH_VIOLATION" }
    # needs-clarification: architect to decide which error code applies

  @SC-US-1-14
  Scenario: Symbol at a macro expansion site [edge case — assumed]
    Given "/projects/src/macro.cpp" contains a macro invocation "MY_MACRO(x)" at line=5 col=3
    When cpp_get_definition is called with file_path="/projects/src/macro.cpp" line=5 col=3
    Then the response either contains the macro definition location or includes definition_found=false
    # assumed: libclang may or may not return a cursor for a macro site; no error should be thrown
```

---

### Feature: cpp_get_references — Find all symbol usages (US-2)

```gherkin
Feature: cpp_get_references

  Background:
    Given the MCP server is running with allowed root "/projects"
    And "/projects/src/lib.cpp" exists with symbol "calculate" defined at line 5 col 6

  @SC-US-2-1
  Scenario: Happy path — references returned [US-2/AC-1]
    Given build_path "/projects/build" containing compile_commands.json listing "/projects/src/lib.cpp"
    And "calculate" has 3 reference sites in the TU
    When cpp_get_references is called with file_path="/projects/src/lib.cpp" line=5 col=6
    Then the response contains a list of 3 entries each with { file: <absolute path>, line, col, context_snippet }

  @SC-US-2-2
  Scenario: Zero references returns empty list — not an error [US-2/AC-2]
    Given "calculate" has no callers in the parsed TU
    When cpp_get_references is called with file_path="/projects/src/lib.cpp" line=5 col=6
    Then the response contains an empty list
    And no error code is returned

  @SC-US-2-3
  Scenario: Default flags when build_path=None [US-2/AC-3, US-9/AC-1]
    When cpp_get_references is called with file_path="/projects/src/lib.cpp" line=5 col=6 build_path=None
    Then flags_source="default" is used

  @SC-US-2-4
  Scenario: FILE_NOT_FOUND for non-existent file [US-2/AC-4]
    When cpp_get_references is called with file_path="/projects/src/missing.cpp" line=1 col=1
    Then the response is { code: "FILE_NOT_FOUND" }

  @SC-US-2-5
  Scenario: INVALID_POSITION for out-of-range line/col [US-2/AC-5]
    When cpp_get_references is called with file_path="/projects/src/lib.cpp" line=9999 col=1
    Then the response is { code: "INVALID_POSITION" }

  @SC-US-2-6
  Scenario: PATH_VIOLATION for path-traversal in file_path [US-2/AC-6, US-12/AC-1]
    When cpp_get_references is called with file_path="../secret/passwords.cpp" line=1 col=1
    Then the response is { code: "PATH_VIOLATION" }

  @SC-US-2-7
  Scenario: Large reference list returns all entries or truncated flag [US-2/AC-7]
    Given "calculate" has 1500 reference sites across the TU
    When cpp_get_references is called with file_path="/projects/src/lib.cpp" line=5 col=6
    Then the response either contains 1500 entries
    Or contains entries up to a limit with truncated=true and omitted_count >= 1
    And no silent data loss occurs
```

---

### Feature: cpp_get_type_info — Retrieve type details for a symbol (US-3)

```gherkin
Feature: cpp_get_type_info

  Background:
    Given the MCP server is running with allowed root "/projects"
    And "/projects/src/types.cpp" exists

  @SC-US-3-1
  Scenario: Happy path — full type info for a concrete type [US-3/AC-1]
    Given "/projects/src/types.cpp" contains "int x = 42;" at line 3 col 5
    When cpp_get_type_info is called with file_path="/projects/src/types.cpp" line=3 col=5
    Then the response contains { display_type, canonical_type, size_bytes, alignment_bytes, is_pod, is_const, is_reference, is_pointer }
    And size_bytes and alignment_bytes are non-null integers

  @SC-US-3-2
  Scenario: Auto-typed variable resolves to concrete canonical type [US-3/AC-2]
    Given "/projects/src/types.cpp" contains "auto val = 3.14f;" at line 7 col 6
    When cpp_get_type_info is called with file_path="/projects/src/types.cpp" line=7 col=6
    Then canonical_type is "float" (not "auto")

  @SC-US-3-3
  Scenario: Template instantiation shows expanded type [US-3/AC-3]
    Given "/projects/src/types.cpp" contains "std::vector<int> v;" at line 12 col 20
    When cpp_get_type_info is called with file_path="/projects/src/types.cpp" line=12 col=20
    Then display_type includes template arguments (e.g., "std::vector<int>")
    And canonical_type is the fully expanded form

  @SC-US-3-4
  Scenario: Incomplete type returns null size and alignment — not an error [US-3/AC-4]
    Given "/projects/src/types.cpp" contains a forward declaration "struct Opaque;" at line 2 col 1
    And "Opaque *p;" at line 3 col 8
    When cpp_get_type_info is called for the "Opaque" type at its forward-declaration location
    Then size_bytes=null and alignment_bytes=null
    And no error code is returned

  @SC-US-3-5
  Scenario: Default flags when build_path=None [US-3/AC-5, US-9/AC-1]
    When cpp_get_type_info is called with file_path="/projects/src/types.cpp" line=3 col=5 build_path=None
    Then flags_source="default" is used

  @SC-US-3-6
  Scenario: FILE_NOT_FOUND for non-existent file [US-3/AC-6]
    When cpp_get_type_info is called with file_path="/projects/src/gone.cpp" line=1 col=1
    Then the response is { code: "FILE_NOT_FOUND" }

  @SC-US-3-7
  Scenario: INVALID_POSITION for out-of-range position [US-3/AC-6]
    When cpp_get_type_info is called with file_path="/projects/src/types.cpp" line=0 col=0
    Then the response is { code: "INVALID_POSITION" }

  @SC-US-3-8
  Scenario: PATH_VIOLATION for path-traversal in file_path [US-3/AC-7, US-12/AC-1]
    When cpp_get_type_info is called with file_path="../../etc/shadow" line=1 col=1
    Then the response is { code: "PATH_VIOLATION" }
```

---

### Feature: cpp_get_ast — Retrieve scoped annotated AST subtree (US-4)

```gherkin
Feature: cpp_get_ast

  Background:
    Given the MCP server is running with allowed root "/projects"
    And "/projects/src/ast_test.cpp" exists with valid parseable C++ content (50 lines, 5 nesting levels)

  @SC-US-4-1
  Scenario: Happy path — JSON format AST returned [US-4/AC-1]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" format="json"
    Then the response is a valid JSON tree
    And each node contains { kind, spelling, usr, type, storage_class, start_line, start_col, end_line, end_col, children }

  @SC-US-4-2
  Scenario: Graph format AST returned [US-4/AC-2]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" format="graph"
    Then the response contains { nodes: [{ id, kind, spelling, usr, type }], edges: [{ source_id, target_id, edge_type }] }
    And all edge_type values are in { "CHILD", "TYPE_REF", "CALL" }

  @SC-US-4-3
  Scenario: Depth truncation at specified depth N [US-4/AC-3]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" format="json" depth=2
    Then the returned tree has at most 2 levels of nesting (root = level 0)
    And nodes at depth 2 that have children carry truncated=true

  @SC-US-4-4
  Scenario: Default depth of 3 applied when depth not specified [US-4/AC-5]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" format="json"
    Then the returned tree has at most 3 levels of nesting

  @SC-US-4-5
  Scenario: Line range filtering — only overlapping nodes returned [US-4/AC-4]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" start_line=10 end_line=20
    Then all returned AST nodes have source ranges overlapping [10, 20]
    And no nodes outside [10, 20] appear in the result

  @SC-US-4-6
  Scenario: Partial AST with parse error list for unresolvable file [US-4/AC-7]
    Given "/projects/src/broken.cpp" includes a missing header "nonexistent.h" causing a parse warning
    When cpp_get_ast is called with file_path="/projects/src/broken.cpp" format="json"
    Then the response includes the partial AST that libclang could recover
    And the response includes parse_errors=[{ severity, message, file, line, col }] (non-empty)
    And no top-level error code is returned

  @SC-US-4-7
  Scenario: FILE_NOT_FOUND for non-existent file [US-4/AC-8]
    When cpp_get_ast is called with file_path="/projects/src/nofile.cpp"
    Then the response is { code: "FILE_NOT_FOUND" }

  @SC-US-4-8
  Scenario: INVALID_RANGE when start_line > end_line [US-4/AC-9]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" start_line=30 end_line=10
    Then the response is { code: "INVALID_RANGE", message: <string>, tool: "cpp_get_ast", request_id: <uuid> }

  @SC-US-4-9
  Scenario: PATH_VIOLATION for path-traversal in file_path [US-4/AC-10, US-12/AC-1]
    When cpp_get_ast is called with file_path="../../tmp/evil.cpp"
    Then the response is { code: "PATH_VIOLATION" }

  @SC-US-4-10
  Scenario: Default flags when build_path=None [US-4/AC-6, US-9/AC-1]
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" build_path=None
    Then flags_source="default" is used

  @SC-US-4-11
  Scenario: PARSE_ERROR for totally unrecoverable parse (zero AST output) [US-13/AC-3, OQ-NEW-2 — needs-clarification]
    Given "/projects/src/unparseable.cpp" causes libclang to produce zero AST nodes with fatal diagnostics
    When cpp_get_ast is called with file_path="/projects/src/unparseable.cpp"
    Then the response is either { code: "PARSE_ERROR" } or contains an empty AST with a populated parse_errors list
    # needs-clarification: architect to define threshold for PARSE_ERROR vs. partial AST (AC-7)

  @SC-US-4-12
  Scenario: Malformed compile_commands.json falls back to default flags [OQ-NEW-2 — needs-clarification]
    Given build_path "/projects/bad-build" contains a "compile_commands.json" with invalid JSON syntax
    When cpp_get_ast is called with file_path="/projects/src/ast_test.cpp" build_path="/projects/bad-build"
    Then the server either returns { code: "PARSE_ERROR" } or falls back to default_flags with flags_source="default"
    # needs-clarification: architect to decide whether malformed compile_commands.json is PARSE_ERROR or silent fallback
```

---

### Feature: cpp_get_header_info — Inspect include graph and exported symbols (US-5)

```gherkin
Feature: cpp_get_header_info

  Background:
    Given the MCP server is running with allowed root "/projects"
    And "/projects/include/api.h" exists

  @SC-US-5-1
  Scenario: Happy path — full header info returned [US-5/AC-1]
    Given "/projects/include/api.h" includes two headers and exports three symbols
    When cpp_get_header_info is called with file_path="/projects/include/api.h"
    Then the response contains {
        direct_includes: [<2 paths>],
        transitive_includes: [<paths>],
        exported_symbols: [{ kind, name, usr, signature }, ...],
        missing_includes: [],
        orphaned_includes: []
      }

  @SC-US-5-2
  Scenario: Header with no includes returns empty include lists — not an error [US-5/AC-2]
    Given "/projects/include/standalone.h" has no #include directives
    When cpp_get_header_info is called with file_path="/projects/include/standalone.h"
    Then direct_includes=[] and transitive_includes=[]
    And no error code is returned

  @SC-US-5-3
  Scenario: Unresolvable include appears in missing_includes [US-5/AC-3]
    Given "/projects/include/api.h" includes <nonexistent_lib.h> that cannot be resolved
    When cpp_get_header_info is called with file_path="/projects/include/api.h"
    Then "nonexistent_lib.h" appears in missing_includes
    And no hard error is returned

  @SC-US-5-4
  Scenario: Unreferenced include appears in orphaned_includes [US-5/AC-4]
    Given "/projects/include/api.h" includes "/projects/include/util.h"
    And no symbol from "util.h" is referenced in "api.h"
    When cpp_get_header_info is called with file_path="/projects/include/api.h"
    Then "/projects/include/util.h" appears in orphaned_includes

  @SC-US-5-5
  Scenario: Default flags when build_path=None [US-5/AC-5, US-9/AC-1]
    When cpp_get_header_info is called with file_path="/projects/include/api.h" build_path=None
    Then flags_source="default" is used

  @SC-US-5-6
  Scenario: FILE_NOT_FOUND for non-existent file [US-5/AC-6]
    When cpp_get_header_info is called with file_path="/projects/include/missing.h"
    Then the response is { code: "FILE_NOT_FOUND" }

  @SC-US-5-7
  Scenario: PATH_VIOLATION for path-traversal in file_path [US-5/AC-7, US-12/AC-1]
    When cpp_get_header_info is called with file_path="../../etc/hosts"
    Then the response is { code: "PATH_VIOLATION" }
```

---

### Feature: cpp_get_preprocessor_state — Retrieve macro definitions and conditional state (US-6)

```gherkin
Feature: cpp_get_preprocessor_state

  Background:
    Given the MCP server is running with allowed root "/projects"
    And "/projects/src/config.cpp" exists with macro definitions and #ifdef blocks

  @SC-US-6-1
  Scenario: Happy path — macros and conditionals returned [US-6/AC-1]
    Given "/projects/src/config.cpp" defines macros and contains #ifdef blocks
    When cpp_get_preprocessor_state is called with file_path="/projects/src/config.cpp"
    Then the response contains {
        macros: [{ name, value, defined_at: { file, line } }],
        conditionals: [{ directive, condition, evaluated_result, start_line, end_line }]
      }

  @SC-US-6-2
  Scenario: Macro from -D flag appears with defined_at=null [US-6/AC-2]
    Given build_path "/projects/build" flags include "-DDEBUG=1"
    When cpp_get_preprocessor_state is called with file_path="/projects/src/config.cpp" build_path="/projects/build"
    Then macros includes { name: "DEBUG", value: "1", defined_at: null }

  @SC-US-6-3
  Scenario: #ifdef block conditional evaluated correctly [US-6/AC-3]
    Given "/projects/src/config.cpp" contains "#ifdef DEBUG ... #endif" and DEBUG is defined in flags
    When cpp_get_preprocessor_state is called
    Then conditionals includes an entry with directive="#ifdef", condition="DEBUG", evaluated_result=true

  @SC-US-6-4
  Scenario: File with no macros or conditionals returns empty lists — not an error [US-6/AC-4]
    Given "/projects/src/simple.cpp" has no macro definitions and no #ifdef blocks
    When cpp_get_preprocessor_state is called with file_path="/projects/src/simple.cpp"
    Then macros=[] and conditionals=[]
    And no error code is returned

  @SC-US-6-5
  Scenario: Default flags when build_path=None [US-6/AC-5, US-9/AC-1]
    When cpp_get_preprocessor_state is called with file_path="/projects/src/config.cpp" build_path=None
    Then flags_source="default" is used

  @SC-US-6-6
  Scenario: FILE_NOT_FOUND for non-existent file [US-6/AC-6]
    When cpp_get_preprocessor_state is called with file_path="/projects/src/gone.cpp"
    Then the response is { code: "FILE_NOT_FOUND" }

  @SC-US-6-7
  Scenario: PATH_VIOLATION for path-traversal in file_path [US-6/AC-7, US-12/AC-1]
    When cpp_get_preprocessor_state is called with file_path="../../etc/environment"
    Then the response is { code: "PATH_VIOLATION" }
```

---

### Feature: cpp_export_to_graphdb — Export AST and symbol relationships to graph DB (US-7)

```gherkin
Feature: cpp_export_to_graphdb

  Background:
    Given the MCP server is running with allowed root "/projects"
    And a reachable graph database at db_uri="bolt://localhost:7687"

  @SC-US-7-1
  Scenario: Happy path — single file exported successfully [US-7/AC-1, US-7/AC-2]
    Given "/projects/src/main.cpp" is a valid C++ file
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" build_path="/projects/build" db_uri="bolt://localhost:7687"
    Then the response contains { files_processed: 1, nodes_written: <int>, edges_written: <int>, errors: [] }
    And graph nodes include types: File, Namespace, Class, Function, Variable, Macro, TypeAlias
    And graph edges include types: DEFINES, DECLARES, CALLS, INHERITS, REFERENCES, INCLUDES, MEMBER_OF

  @SC-US-7-2
  Scenario: DB_UNREACHABLE when db_uri is not reachable [US-7/AC-3]
    Given db_uri="bolt://unreachable-host:7687" is not reachable
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" build_path="/projects/build" db_uri="bolt://unreachable-host:7687"
    Then the response is { code: "DB_UNREACHABLE", message: <string>, tool: "cpp_export_to_graphdb", request_id: <uuid> }
    And no source files are modified

  @SC-US-7-3
  Scenario: Directory input processes all supported C++ file extensions [US-7/AC-4]
    Given "/projects/src/" contains: main.cpp, util.h, algo.hpp, impl.cc, module.cxx, README.md, build.py
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/" build_path="/projects/build" db_uri="bolt://localhost:7687"
    Then files_processed=5 (main.cpp, util.h, algo.hpp, impl.cc, module.cxx)
    And README.md and build.py are not processed

  @SC-US-7-4
  Scenario: Partial failure — successful files committed, failures listed [US-7/AC-5]
    Given "/projects/src/" contains two valid files and one unparseable file "broken.cpp"
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/" db_uri="bolt://localhost:7687"
    Then files_processed >= 2
    And errors contains { file: "broken.cpp", code: <error_code>, message: <string> }
    And no all-or-nothing rollback of the successful files occurs

  @SC-US-7-5
  Scenario: FILE_NOT_FOUND for non-existent file_path_or_dir [US-7/AC-6]
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/nonexistent.cpp" db_uri="bolt://localhost:7687"
    Then the response is { code: "FILE_NOT_FOUND" }

  @SC-US-7-6
  Scenario: PATH_VIOLATION for path-traversal in file_path_or_dir [US-7/AC-7, US-12/AC-1]
    When cpp_export_to_graphdb is called with file_path_or_dir="../../etc" db_uri="bolt://localhost:7687"
    Then the response is { code: "PATH_VIOLATION" }
    And no database write occurs

  @SC-US-7-7
  Scenario: PATH_VIOLATION for path-traversal in build_path [US-7/AC-7, US-12/AC-2]
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" build_path="../../etc" db_uri="bolt://localhost:7687"
    Then the response is { code: "PATH_VIOLATION" }
    And no database write occurs

  @SC-US-7-8
  Scenario: Read-only enforcement — no source file modified during export [US-7/AC-8, US-11/AC-2]
    Given "/projects/src/main.cpp" exists before the export call
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" db_uri="bolt://localhost:7687"
    Then the mtime and content of "/projects/src/main.cpp" are identical before and after the call
    And no new files exist under "/projects/src/" after the call

  @SC-US-7-9
  Scenario: INVALID_ARGUMENT when db_uri is absent [US-7/AC-9]
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" build_path="/projects/build" and db_uri is absent
    Then the response is { code: "INVALID_ARGUMENT", message: <string identifying "db_uri"> }
    And no execution occurs

  @SC-US-7-10
  Scenario: INVALID_ARGUMENT when build_path is absent [US-7/AC-9]
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" db_uri="bolt://localhost:7687" and build_path is absent
    Then the response is { code: "INVALID_ARGUMENT", message: <string identifying "build_path"> }
    And no execution occurs

  @SC-US-7-11
  Scenario: INVALID_ARGUMENT when db_uri is empty string [US-7/AC-9]
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/main.cpp" build_path="/projects/build" db_uri=""
    Then the response is { code: "INVALID_ARGUMENT" }
```

---

### Feature: Stateless Build Context — no cross-call state contamination (US-8)

```gherkin
Feature: Stateless Build Context

  Background:
    Given the MCP server is running with allowed root "/projects"

  @SC-US-8-1
  Scenario: Two calls with different build_paths use independent flags [US-8/AC-1]
    Given "/projects/repo-a/src/foo.cpp" exists and build_path="/projects/repo-a/build" has flags ["-DREPO_A"]
    And "/projects/repo-b/src/bar.cpp" exists and build_path="/projects/repo-b/build" has flags ["-DREPO_B"]
    When cpp_get_definition is called with file_path="/projects/repo-a/src/foo.cpp" build_path="/projects/repo-a/build"
    And cpp_get_definition is called with file_path="/projects/repo-b/src/bar.cpp" build_path="/projects/repo-b/build"
    Then the first call's response includes flags_source="compilation_db" with repo-a flags
    And the second call's response includes flags_source="compilation_db" with repo-b flags
    And neither call's flags appear in the other's response

  @SC-US-8-2
  Scenario: Call without build_path followed by call with build_path — no state mutation [US-8/AC-2]
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" build_path=None
    Then the response includes flags_source="default"
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" build_path="/projects/build"
    Then the response includes flags_source="compilation_db"
    And the first call's default_flags are not observable in the second call

  @SC-US-8-3
  Scenario: Server restart clears TU cache and project roots [US-8/AC-3]
    Given a server session has processed several tool calls and the TU cache is non-empty
    When the server is restarted
    And cpp_get_definition is called with file_path="/projects/src/main.cpp"
    Then cache_hit=false (TU cache started empty)
    And no state from the previous session affects the response

  @SC-US-8-4
  Scenario: No global project root endpoint is exposed [US-8/AC-4]
    When an attempt is made to call a hypothetical "set_project_root" or "set_build_path" endpoint
    Then the server returns a method-not-found or equivalent MCP error
    And no global state is mutated
```

---

### Feature: Default Flags Fallback (US-9)

```gherkin
Feature: Default Flags Fallback

  Background:
    Given the MCP server is running with allowed root "/projects"

  @SC-US-9-1
  Scenario: build_path=None applies default_flags [US-9/AC-1]
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" build_path=None
    Then the TU is parsed with flags ["-std=c++20", "-I.", "-x", "c++"]

  @SC-US-9-2
  Scenario: File absent from compile_commands.json falls back to default_flags [US-9/AC-2]
    Given build_path "/projects/build" contains compile_commands.json that does NOT list "/projects/src/unlisted.cpp"
    When cpp_get_definition is called with file_path="/projects/src/unlisted.cpp" build_path="/projects/build"
    Then flags_source="default" in the response
    And no error is returned

  @SC-US-9-3
  Scenario: File present in compile_commands.json uses compilation_db flags [US-9/AC-3]
    Given build_path "/projects/build" contains compile_commands.json listing "/projects/src/main.cpp" with specific flags
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" build_path="/projects/build"
    Then flags_source="compilation_db" in the response

  @SC-US-9-4
  Scenario: Default flags are configurable at startup [US-9/AC-4]
    Given the server is started with DEFAULT_FLAGS="-std=c++17 -I/usr/include"
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" build_path=None
    Then the TU is parsed with flags ["-std=c++17", "-I/usr/include"]
```

---

### Feature: TU Cache with LRU Eviction (US-10)

```gherkin
Feature: TU Cache

  Background:
    Given the MCP server is running with allowed root "/projects"
    And cache capacity is 3 TUs

  @SC-US-10-1
  Scenario: Cache hit on second call for same (file_path, build_path) [US-10/AC-1]
    Given cpp_get_definition was already called with file_path="/projects/src/a.cpp" build_path="/projects/build"
    When cpp_get_definition is called again with the same file_path and build_path
    Then the response includes cache_hit=true
    And libclang parse is NOT invoked again

  @SC-US-10-2
  Scenario: Cache miss on first call for a new (file_path, build_path) [US-10/AC-1 negative]
    When cpp_get_definition is called for the first time with file_path="/projects/src/new.cpp" build_path="/projects/build"
    Then the response includes cache_hit=false

  @SC-US-10-3
  Scenario: LRU eviction when cache is full [US-10/AC-2]
    Given the cache already holds entries for (a.cpp, build), (b.cpp, build), (c.cpp, build) in that access order
    And (a.cpp, build) was the least-recently-used
    When cpp_get_definition is called with file_path="/projects/src/d.cpp" build_path="/projects/build"
    Then the entry for (a.cpp, build) is evicted from cache
    And (d.cpp, build) is inserted

  @SC-US-10-4
  Scenario: Cache stats endpoint returns hit rate [US-10/AC-3]
    Given the server has processed some tool calls
    When a cache status request is made (e.g., health/stats endpoint)
    Then the response contains { cache_size: <int>, cache_capacity: 3, cache_hit_rate: <float 0.0-1.0> }

  @SC-US-10-5
  Scenario: Different build_paths for same file occupy separate cache entries [US-10/AC-4]
    When cpp_get_definition is called with file_path="/projects/src/a.cpp" build_path="/projects/build-debug"
    And cpp_get_definition is called with file_path="/projects/src/a.cpp" build_path="/projects/build-release"
    Then the cache contains two separate entries
    And each entry's flags are independent

  @SC-US-10-6
  Scenario: Cache capacity configurable at startup [US-10/AC-5]
    Given the server is started with CACHE_CAPACITY=64
    When a cache status request is made
    Then cache_capacity=64

  @SC-US-10-7
  Scenario: Stale TU evicted on mtime change [US-10/AC-6]
    Given cpp_get_definition was called for "/projects/src/a.cpp" and the TU is cached
    And "/projects/src/a.cpp" is subsequently modified (mtime updated)
    When cpp_get_definition is called again for "/projects/src/a.cpp"
    Then the stale TU is evicted
    And the file is re-parsed
    And cache_hit=false in the response
```

---

### Feature: Read-Only Enforcement (US-11)

```gherkin
Feature: Read-Only Enforcement

  Background:
    Given the MCP server is running with allowed root "/projects"
    And the filesystem under "/projects" is monitored for write events

  @SC-US-11-1
  Scenario: Navigation tools (US-1..US-6) make no filesystem writes [US-11/AC-1]
    Given "/projects/src/main.cpp" exists with a known mtime
    When each of cpp_get_definition, cpp_get_references, cpp_get_type_info, cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state is called with file_path="/projects/src/main.cpp"
    Then no file under "/projects" is created, modified, or deleted during or after any call
    And mtime of "/projects/src/main.cpp" is unchanged

  @SC-US-11-2
  Scenario: cpp_export_to_graphdb makes no source file writes [US-11/AC-2, US-7/AC-8]
    Given "/projects/src/" contains "main.cpp" with a known mtime
    When cpp_export_to_graphdb is called with file_path_or_dir="/projects/src/" db_uri="bolt://localhost:7687"
    Then no file under "/projects/src/" is created, modified, or deleted
    And db_uri receives the written data

  @SC-US-11-3
  Scenario: No write-back tool endpoint is exposed [US-11/AC-3]
    When an attempt is made to call a hypothetical write-to-file or patch-source endpoint
    Then the server returns a method-not-found or equivalent MCP error
```

---

### Feature: Path Traversal Validation (US-12)

```gherkin
Feature: Path Traversal Validation

  Background:
    Given the MCP server is running with allowed root "/projects"

  @SC-US-12-1
  Scenario: PATH_VIOLATION for .. components in file_path [US-12/AC-1]
    When any tool is called with file_path="../../etc/passwd"
    Then the response is { code: "PATH_VIOLATION" }
    And no file I/O is attempted

  @SC-US-12-2
  Scenario: PATH_VIOLATION for .. components in build_path [US-12/AC-2]
    When any tool is called with a valid file_path and build_path="../../etc"
    Then the response is { code: "PATH_VIOLATION" }

  @SC-US-12-3
  Scenario: PATH_VIOLATION for symlink resolving outside allowed root [US-12/AC-3]
    Given "/projects/src/escape_link.cpp" is a symlink pointing to "/private/etc/passwd"
    When cpp_get_definition is called with file_path="/projects/src/escape_link.cpp" line=1 col=1
    Then the response is { code: "PATH_VIOLATION" }

  @SC-US-12-4
  Scenario: Absolute path within allowed root passes validation [US-12/AC-4]
    Given "/projects/src/main.cpp" is a real file (not a symlink) within "/projects"
    When cpp_get_definition is called with file_path="/projects/src/main.cpp" line=10 col=5
    Then path validation passes
    And the tool proceeds to parse and return a result

  @SC-US-12-5
  Scenario: Server refuses all calls if ALLOWED_ROOT is not configured [US-12/AC-5]
    Given the server is started without the ALLOWED_ROOT environment variable
    When any tool is called
    Then the server returns a startup or configuration error
    And no tool executes

  @SC-US-12-6
  Scenario: Absolute path outside allowed root is rejected [US-12/AC-1 — boundary]
    Given the allowed root is "/projects"
    When any tool is called with file_path="/home/user/secret.cpp"
    Then the response is { code: "PATH_VIOLATION" }
    # file is real and has no .. components but is outside the allowed root
```

---

### Feature: Structured Error Envelope (US-13)

```gherkin
Feature: Structured Error Envelope

  Background:
    Given the MCP server is running with allowed root "/projects"

  @SC-US-13-1
  Scenario: All error responses conform to envelope schema [US-13/AC-1]
    When any tool returns an error (any error code)
    Then the response conforms to { code: "<ERROR_CODE>", message: "<string>", tool: "<tool_name>", request_id: "<uuid>" }
    And code is one of: FILE_NOT_FOUND, INVALID_POSITION, INVALID_RANGE, INVALID_ARGUMENT, PATH_VIOLATION, DB_UNREACHABLE, PARSE_ERROR, INTERNAL_ERROR

  @SC-US-13-2
  Scenario: INTERNAL_ERROR for unexpected server exception exposes no stack trace [US-13/AC-2]
    Given the server encounters an unexpected exception during tool execution (e.g., segfault in libclang binding)
    When the tool call returns
    Then the response is { code: "INTERNAL_ERROR", message: <non-empty string>, tool: <tool_name>, request_id: <uuid> }
    And message does not contain a Python traceback, file path, or internal variable names

  @SC-US-13-3
  Scenario: No unstructured string returned as error [US-13/AC-3]
    When any tool call results in an error condition
    Then the response is always JSON with a "code" field from the valid error code set
    And the response is never a plain string or unstructured payload
```

---

### Feature: Transport — stdio and HTTP (US-14)

```gherkin
Feature: Transport

  @SC-US-14-1
  Scenario: stdio transport responds on stdout [US-14/AC-1]
    Given the server is started in stdio mode
    When a valid MCP JSON-RPC request for cpp_get_definition is written to stdin
    Then the response is written to stdout within the same session
    And the response is valid MCP JSON-RPC

  @SC-US-14-2
  Scenario: HTTP transport responds on /mcp endpoint [US-14/AC-2]
    Given the server is started in http mode with --port 8080
    When an HTTP POST to "http://localhost:8080/mcp" is made with a valid MCP request body
    Then the HTTP response has status 200
    And the body is a valid MCP response

  @SC-US-14-3
  Scenario: Both transports expose identical tool set [US-14/AC-3]
    Given the server is started in stdio mode
    Then tools cpp_get_definition, cpp_get_references, cpp_get_type_info, cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state, cpp_export_to_graphdb are all available
    Given the server is started in http mode
    Then the same 7 tools are available with identical behavior

  @SC-US-14-4
  Scenario: Server starts without orchestration system [US-14/AC-4]
    Given no Docker, Docker Compose, or Kubernetes is running
    When the server is started in stdio mode or http mode from a plain shell
    Then the server starts successfully and accepts tool calls
```

---

## Coverage Matrix

| Story | AC Count | Scenarios | Error Codes Covered |
|---|---|---|---|
| US-1 | 9 | SC-US-1-1..14 | FILE_NOT_FOUND, INVALID_POSITION, PATH_VIOLATION |
| US-2 | 7 | SC-US-2-1..7 | FILE_NOT_FOUND, INVALID_POSITION, PATH_VIOLATION |
| US-3 | 7 | SC-US-3-1..8 | FILE_NOT_FOUND, INVALID_POSITION, PATH_VIOLATION |
| US-4 | 10 | SC-US-4-1..12 | FILE_NOT_FOUND, INVALID_RANGE, PATH_VIOLATION, PARSE_ERROR* |
| US-5 | 7 | SC-US-5-1..7 | FILE_NOT_FOUND, PATH_VIOLATION |
| US-6 | 7 | SC-US-6-1..7 | FILE_NOT_FOUND, PATH_VIOLATION |
| US-7 | 9 | SC-US-7-1..11 | DB_UNREACHABLE, FILE_NOT_FOUND, PATH_VIOLATION, INVALID_ARGUMENT |
| US-8 | 4 | SC-US-8-1..4 | (behavioral, no error codes) |
| US-9 | 4 | SC-US-9-1..4 | (behavioral, no error codes) |
| US-10 | 6 | SC-US-10-1..7 | (behavioral, no error codes) |
| US-11 | 3 | SC-US-11-1..3 | (behavioral, no error codes) |
| US-12 | 5 | SC-US-12-1..6 | PATH_VIOLATION |
| US-13 | 3 | SC-US-13-1..3 | INTERNAL_ERROR, all codes |
| US-14 | 4 | SC-US-14-1..4 | (behavioral, no error codes) |

Error code coverage:
- FILE_NOT_FOUND: SC-US-1-5, SC-US-2-4, SC-US-3-6, SC-US-4-7, SC-US-5-6, SC-US-6-6, SC-US-7-5
- INVALID_POSITION: SC-US-1-6, SC-US-1-7, SC-US-2-5, SC-US-3-7
- INVALID_RANGE: SC-US-4-8
- INVALID_ARGUMENT: SC-US-7-9, SC-US-7-10, SC-US-7-11
- PATH_VIOLATION: SC-US-1-9..12, SC-US-2-6, SC-US-3-8, SC-US-4-9, SC-US-5-7, SC-US-6-7, SC-US-7-6, SC-US-7-7, SC-US-12-1..3, SC-US-12-6
- DB_UNREACHABLE: SC-US-7-2
- PARSE_ERROR: SC-US-4-11* (needs-clarification)
- INTERNAL_ERROR: SC-US-13-2

*PARSE_ERROR: no functional story AC unambiguously returns this code. SC-US-4-11 and SC-US-4-12 are tagged needs-clarification pending architect decision on OQ-NEW-2.

No further cases identified beyond those enumerated.

---

## References
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/requirements.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/CHARTER.md
- Cognee tags: task:cpp-mcp, role:business-analyst
