---
run_id: fastmcp-migration-v2
stage: business-analyst
date: 2026-05-16
source: /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements.md
---

# Scenarios: FastMCP Migration (v2)

---

## Requirements Summary

### In-Scope
- Replace hand-rolled stdio transport with FastMCP while preserving all 7 tool names, argument schemas, response shapes, and error envelopes.
- Implement HTTP transport (closes v1 US-14/AC-2 stub).
- Register tools via `@mcp.tool` decorators, eliminating `_TOOL_SPECS`/`_HANDLERS`.
- Auto-generate tool input schemas from type hints; verify parity against frozen v1 schemas.
- Preserve `{code, message, tool, request_id}` error envelope for all 8 error codes.
- Manage libclang `Index` + TU cache lifecycle via FastMCP `lifespan`.
- Preserve libclang thread-affinity through `ThreadPoolExecutor(max_workers=1)`.
- Pin `fastmcp~=3.1.0` in `pyproject.toml`; commit `uv.lock`.
- Supersede ADR-10 with ADR-11.

### Out-of-Scope
- Middleware (LoggingMiddleware, TimingMiddleware) — deferred per OQ-7.
- HTTP authentication — deferred per US-M2/AC-5 / v1 ADR-10.
- New tool names or argument fields.
- Altering `core/path_guard.py` semantics.

### Assumptions
- ASM-1 (assumed): Tag convention follows existing feature files: `@SC_US_{N}_{M}` with underscores; v2 stories use `@SC_USM{N}_{M}` to distinguish migration stories from v1.
- ASM-2 (assumed): "Semantically equivalent" in US-M4/AC-2 accepts `["string","null"]` ↔ `Optional[str]` as equal and `$defs`/`$ref` inlining as cosmetic — no rename, no added required field, no dropped property.
- ASM-3 (assumed): "N concurrent requests" in US-M7/AC-3 means at least 3 simultaneous HTTP calls to the same tool on the same file.
- ASM-4 (assumed): `session.close()` is a new method on `ClangSession` if absent; the AC creates the obligation to introduce it.
- ASM-5 (assumed): pytest-bdd feature files are the canonical executable form; this `.md` file drives their authoring.

### Open Questions (forwarded to architect)

| OQ  | Question                                                                                                                   | Blocks scenario(s)                     | Status              |
|-----|----------------------------------------------------------------------------------------------------------------------------|----------------------------------------|---------------------|
| OQ-1 | Where does ADR-11 live — `v1/adr-11.md` or `v2/adr-1.md`?                                                               | SC_USM9_1, SC_USM9_2                   | needs-clarification |
| OQ-2 | Error envelope delivery mechanism: return dict, `ToolResult(structured_content={...})`, or custom middleware?             | SC_USM5_5                              | needs-clarification |
| OQ-3 | Dependency injection for tool deps: `Depends(...)`, `ctx.lifespan_context`, or closure capture?                           | SC_USM3_4                              | needs-clarification |
| OQ-4 | Stdio entrypoint: `asyncio.run(_run_stdio())` or FastMCP's `mcp.run()`?                                                   | SC_USM1_5b                             | needs-clarification |
| OQ-5 | HTTP endpoint path: FastMCP default or preserve `/mcp` literal from v1 ADR-10?                                            | SC_USM2_1                              | needs-clarification |
| OQ-6 | Retain `server/schemas.py` as frozen fixture or move to `tests/fixtures/expected_schemas/`?                               | SC_USM4_1                              | needs-clarification |
| OQ-7 | Introduce FastMCP middleware (observability) now or defer to v3?                                                           | none (deferred out-of-scope)           | needs-clarification |
| OQ-8 | Stdio entrypoint: `asyncio.run(...)` vs. `mcp.run()` — KeyboardInterrupt / ConfigError catch behavior?                   | SC_USM1_5b                             | needs-clarification |
| OQ-9 | Sync `def` + `executor.submit(...).result()` pattern — architect to confirm and capture in ADR.                           | SC_USM7_2, SC_USM7_3                   | needs-clarification |

### Edge Cases

| ID   | Edge case                                                                 | Source                | Status              |
|------|---------------------------------------------------------------------------|-----------------------|---------------------|
| EC-1 | Non-loopback bind value — WARNING emitted (IPv4 `0.0.0.0`)               | US-M2/AC-3            | confirmed           |
| EC-2 | Non-loopback bind: IPv6 any-address `::` — WARNING also emitted?         | US-M2/AC-3            | needs-clarification |
| EC-3 | Tool function raises unwrapped exception (bypass of `wrap_tool`)         | US-M5/AC-1, US-M5/AC-4 | confirmed          |
| EC-4 | Shutdown during in-flight tool call — executor drains not aborts         | US-M6/AC-2            | confirmed           |
| EC-5 | Third-party lib (libclang) writes warning bytes to stdout                | US-M1/AC-4, C-9       | needs-clarification |
| EC-6 | Dependency-injection params appear in published `inputSchema`            | US-M3/AC-4            | confirmed           |
| EC-7 | `additionalProperties: true` in FastMCP-generated schema (default)       | US-M4/AC-2            | confirmed           |
| EC-8 | `format` enum for `cpp_get_ast` preserved in generated schema            | US-M4/AC-2            | confirmed           |
| EC-9 | `uv sync` resolution to newer FastMCP minor breaks protocol              | US-M8, R-1            | confirmed (lockfile verifies; no Gherkin scenario) |
| EC-10| ADR-10 status line not updated in v1 file                                | US-M9/AC-2            | confirmed           |
| EC-11| `CPP_MCP_ALLOWED_ROOTS` unset at startup — lifespan raises ConfigError  | US-M6/AC-5            | confirmed           |
| EC-12| libclang not loadable at startup — lifespan raises ConfigError           | US-M6/AC-5            | confirmed           |
| EC-13| HTTP transport lifespan invoked more than once at process start           | US-M6/AC-4            | confirmed           |
| EC-14| `description` field empty in generated schema for any tool argument      | US-M4/AC-4            | confirmed           |

### Stakeholders
- MCP clients (Claude Code, Claude Desktop) — consuming tool schemas and responses unchanged.
- Operators — relying on env-var configuration and clean process lifecycle.
- Agent-side error handlers — relying on `{code, message, tool, request_id}` envelope.
- Future developers — reading ADR lineage.

---

## Compatibility Constraint Coverage

Constraints C-1 through C-10 are global gates. The table below maps each to the scenario(s) that verify it. Constraints verified only by non-BDD mechanisms are noted.

| C-ID | Constraint summary                                   | Scenario(s)                                                    | Non-BDD verification                        |
|------|------------------------------------------------------|----------------------------------------------------------------|---------------------------------------------|
| C-1  | 7 tool names unchanged in `tools/list`               | SC_USM1_2, SC_C1_TOOLS_LIST                                   | —                                           |
| C-2  | Argument names/types/required unchanged              | SC_USM4_2 (outline), SC_USM4_3, EC-7, EC-8                   | `test_schema_parity.py`                     |
| C-3  | Success-response fields unchanged (327 tests)        | SC_USM1_3 (verified by pytest baseline)                        | `uv run pytest -q` → 327 passed             |
| C-4  | Error envelope wire shape unchanged                  | SC_USM5_2 (outline over 8 codes)                              | —                                           |
| C-5  | All 10 env vars honored; transport routing           | SC_USM1_5a, SC_USM2_1, SC_USM6_5                             | `tests/unit/test_config.py`                 |
| C-6  | Path-guard semantics unchanged                       | SC_C6_PATH_GUARD                                               | `core/path_guard.py` not modified           |
| C-7  | 327 passed / 1 skipped baseline                      | SC_C7_BASELINE                                                 | `uv run pytest -q`                          |
| C-8  | `ThreadPoolExecutor(max_workers=1)` + Lock preserved | SC_USM7_1, SC_USM7_3                                          | `core/clang_session.py` diff               |
| C-9  | All logs on stderr; stdout = MCP bytes only          | SC_USM1_4                                                      | —                                           |
| C-10 | `cpp-mcp` entry point and `python -m cpp_mcp` work  | SC_USM1_1, SC_C10_ENTRY                                        | —                                           |

---

## Gherkin

---

### Feature: Compatibility Gates (C-1, C-4, C-6, C-7, C-10)

```gherkin
Feature: Compatibility Gates

  # C-1 — verified independently; also checked in US-M1 scenarios
  @SC_C1_TOOLS_LIST
  Scenario: tools/list returns exactly the 7 expected tool names  [C-1]
    Given the FastMCP server is started in stdio mode with a temp allowed root
    When the client sends initialize and calls tools/list
    Then the tools list contains exactly these names:
      | cpp_get_definition         |
      | cpp_get_references         |
      | cpp_get_type_info          |
      | cpp_get_ast                |
      | cpp_get_header_info        |
      | cpp_get_preprocessor_state |
      | cpp_export_to_graphdb      |
    And the tools list contains no other names

  # C-6 — path guard unchanged
  @SC_C6_PATH_GUARD
  Scenario: PATH_VIOLATION still returned for path-traversal input after FastMCP migration  [C-6]
    Given the FastMCP server is started in stdio mode with a temp allowed root
    When cpp_get_definition is called with file_path "../../etc/passwd" line 1 col 1
    Then the response envelope code is "PATH_VIOLATION"
    And the envelope message does not contain a file path outside the allowed root
    And the envelope contains a non-empty request_id

  # C-7 — pytest baseline (BDD cannot run 327 cases inline; scenario acts as gate trigger)
  @SC_C7_BASELINE
  Scenario: Full pytest suite reports 327 passed and 1 skipped  [C-7]
    Given the FastMCP migration is applied to src/cpp_mcp/
    When "uv run pytest -q" is executed without NEO4J_TEST_URI set
    Then the result is "327 passed, 1 skipped"
    And no additional skips appear

  # C-10 — entry point
  @SC_C10_ENTRY
  Scenario: cpp-mcp console-script entry point starts server on stdio  [C-10]
    Given cpp-mcp is installed via "uv pip install -e ."
    When the command "cpp-mcp" is executed with CPP_MCP_ALLOWED_ROOTS set
    Then the process writes an MCP JSON-RPC frame to stdout
    And no error is written to stderr before the first frame
```

---

### Feature: US-M1 — FastMCP stdio transport parity

```gherkin
Feature: FastMCP stdio transport parity  [US-M1]

  Background:
    Given the FastMCP server is started as "python -m cpp_mcp" with CPP_MCP_ALLOWED_ROOTS set

  @SC_USM1_1
  Scenario: initialize succeeds on FastMCP-backed stdio server  [US-M1/AC-1, C-10]
    When the client sends an initialize request
    Then the initialize response is received successfully
    And the server name is "cpp-mcp"

  @SC_USM1_2
  Scenario: tools/list exposes all 7 tools after FastMCP migration  [US-M1/AC-1, C-1]
    When the client sends initialize and calls tools/list
    Then the tools list contains exactly the 7 expected tool names

  @SC_USM1_3
  Scenario Outline: each of the 7 tools responds successfully over stdio  [US-M1/AC-1, C-3]
    When the client calls "<tool_name>" with valid fixture arguments
    Then the response contains no error code
    And the response contains a request_id field
    And the response contains a cache_hit field

    Examples:
      | tool_name                    |
      | cpp_get_definition           |
      | cpp_get_references           |
      | cpp_get_type_info            |
      | cpp_get_ast                  |
      | cpp_get_header_info          |
      | cpp_get_preprocessor_state   |
      | cpp_export_to_graphdb        |

  @SC_USM1_4
  Scenario: stdout contains only MCP JSON-RPC bytes; no log output  [US-M1/AC-4, C-9]
    When the server receives an initialize request with stderr redirected to /dev/null
    Then the first byte on stdout is the start of a JSON object
    And no log lines appear on stdout

  @SC_USM1_5a
  Scenario: server exits 0 on stdin EOF  [US-M1/AC-5]
    When stdin is closed immediately after the server starts
    Then the process exits with code 0

  @SC_USM1_5b
  Scenario: server exits 1 with sanitized message on ConfigError  [US-M1/AC-5, C-5]
    # OQ-4/OQ-8: exact exit mechanism (asyncio.run vs mcp.run) to be confirmed by architect
    # Tag: needs-clarification on catch boundary only; exit behavior is confirmed
    Given CPP_MCP_ALLOWED_ROOTS is unset
    When "python -m cpp_mcp" is executed
    Then the process exits with code 1
    And stderr contains a human-readable error message
    And stderr does not contain a Python traceback
    And stdout contains no MCP frames

  @SC_USM1_6
  Scenario: server protocol version and name are unchanged or additive only  [US-M1/AC-2]
    When the client sends initialize
    Then the serverInfo name is "cpp-mcp"
    And the serverInfo version is present
    And the instructions field is absent or contains only additive text not present in v1
```

---

### Feature: US-M2 — HTTP transport (closes v1 US-14/AC-2)

```gherkin
Feature: HTTP transport via FastMCP  [US-M2]

  @SC_USM2_1
  # OQ-5: endpoint path (FastMCP default vs /mcp) unresolved — needs-clarification
  Scenario: server starts and accepts MCP requests over HTTP on configured port  [US-M2/AC-1]
    Given CPP_MCP_TRANSPORT is "http"
    And CPP_MCP_HTTP_PORT is "8765"
    And CPP_MCP_HTTP_BIND is "127.0.0.1"
    When the server process starts
    Then an MCP initialize request to the server HTTP endpoint on port 8765 returns a valid response
    And the HTTP status is 200

  @SC_USM2_2
  Scenario Outline: tool responses are identical over HTTP vs stdio (modulo request_id)  [US-M2/AC-2, C-3]
    Given the same fixture C++ file is loaded for both transports
    When "<tool_name>" is called over stdio transport and the response is captured
    And "<tool_name>" is called over HTTP transport and the response is captured
    Then the two responses are equal except for the request_id field

    Examples:
      | tool_name                    |
      | cpp_get_definition           |
      | cpp_get_references           |
      | cpp_get_type_info            |
      | cpp_get_ast                  |
      | cpp_get_header_info          |
      | cpp_get_preprocessor_state   |
      | cpp_export_to_graphdb        |

  @SC_USM2_3
  Scenario: non-loopback bind address emits WARNING log line  [US-M2/AC-3]
    Given CPP_MCP_TRANSPORT is "http"
    And CPP_MCP_HTTP_BIND is "0.0.0.0"
    When the server starts
    Then a WARNING line appears on stderr containing the non-loopback address

  @SC_USM2_3b
  # EC-2: IPv6 any-address — needs-clarification whether WARNING also triggers
  Scenario: IPv6 any-address bind also emits WARNING  [US-M2/AC-3, EC-2]
    Given CPP_MCP_TRANSPORT is "http"
    And CPP_MCP_HTTP_BIND is "::"
    When the server starts
    Then a WARNING line appears on stderr
    # needs-clarification: confirm "::" is treated as non-loopback by existing warning logic

  @SC_USM2_4
  Scenario: GET /health returns 200 OK when HTTP transport is active  [US-M2/AC-4]
    Given CPP_MCP_TRANSPORT is "http" and the server is running on a free port
    When an HTTP GET request is sent to "/health"
    Then the response HTTP status is 200
    And the response body is plain text

  @SC_USM2_5
  Scenario: HTTP transport has no authentication requirement in v2  [US-M2/AC-5]
    Given CPP_MCP_TRANSPORT is "http" and the server is running
    When an unauthenticated MCP initialize request is sent
    Then the response is a valid initialize result with no 401 or 403 status
```

---

### Feature: US-M3 — Tool registration via @mcp.tool decorators

```gherkin
Feature: Tool registration via @mcp.tool decorators  [US-M3]

  @SC_USM3_1
  Scenario: _TOOL_SPECS list and _HANDLERS dict are removed from app.py  [US-M3/AC-1]
    Given the FastMCP migration is applied
    When app.py is inspected
    Then no symbol named "_TOOL_SPECS" exists in app.py
    And no symbol named "_HANDLERS" exists in app.py
    And each of the 7 tool functions carries exactly one @mcp.tool decorator

  @SC_USM3_2
  Scenario: tool names in tools/list match existing names exactly  [US-M3/AC-2, C-1]
    Given the FastMCP server is started in stdio mode
    When the client calls tools/list
    Then each tool name in the response matches the corresponding name used in v1 exactly

  @SC_USM3_3
  Scenario: tool descriptions in tools/list match existing descriptions  [US-M3/AC-3]
    Given the FastMCP server is started in stdio mode
    When the client calls tools/list
    Then each tool description matches the v1 description string

  @SC_USM3_4
  # OQ-3: DI mechanism unresolved — needs-clarification; scenario asserts the outcome regardless of mechanism
  Scenario: session and allowed_roots do not appear in the published inputSchema  [US-M3/AC-4, EC-6]
    Given the FastMCP server is started in stdio mode
    When the client calls tools/list
    Then no tool's inputSchema contains a property named "session"
    And no tool's inputSchema contains a property named "allowed_roots"
    And no tool's inputSchema contains a property named "default_flags"
    And no tool's inputSchema contains a property named "ast_max_nodes"
    And no tool's inputSchema contains a property named "ast_max_bytes"

  @SC_USM3_5
  Scenario: mypy --strict passes on src/ after @mcp.tool migration  [US-M3/AC-5]
    Given the FastMCP migration is applied to src/cpp_mcp/
    When "mypy --strict src/" is executed
    Then the exit code is 0
    And no type errors are reported
```

---

### Feature: US-M4 — Schema parity: FastMCP-generated vs. v1 hand-written

```gherkin
Feature: FastMCP-generated input schema parity  [US-M4]

  Background:
    Given a live FastMCP instance with all 7 tools registered

  @SC_USM4_1
  # OQ-6: frozen fixture location unresolved (schemas.py vs tests/fixtures/) — needs-clarification
  Scenario: server/schemas.py is removed or moved to tests/fixtures/  [US-M4/AC-1]
    Given the FastMCP migration is applied
    When the src/cpp_mcp/server/ directory is listed
    Then "schemas.py" does not exist under src/cpp_mcp/server/
    And the v1 schema dicts exist under tests/fixtures/expected_schemas/

  @SC_USM4_2
  Scenario Outline: FastMCP-generated inputSchema is semantically equivalent to v1 schema  [US-M4/AC-2, C-2]
    When the FastMCP-generated inputSchema for "<tool_name>" is fetched from a live instance
    Then it has the same required fields as the v1 schema
    And it has the same property names and types (allowing Optional[str] ↔ ["string","null"])
    And additionalProperties is false
    And enum values for "format" (if applicable) match the v1 enum

    Examples:
      | tool_name                    |
      | cpp_get_definition           |
      | cpp_get_references           |
      | cpp_get_type_info            |
      | cpp_get_ast                  |
      | cpp_get_header_info          |
      | cpp_get_preprocessor_state   |
      | cpp_export_to_graphdb        |

  @SC_USM4_3
  Scenario: test_schema_parity.py fails loudly on any rename or type change  [US-M4/AC-3]
    Given a modified FastMCP tool registration that renames one property
    When tests/unit/test_schema_parity.py is executed
    Then the test fails with an assertion error identifying the changed field

  @SC_USM4_4
  Scenario: test_schema_parity.py fails when any argument description is empty  [US-M4/AC-4, EC-14]
    Given a tool registered without a description on one argument
    When tests/unit/test_schema_parity.py is executed
    Then the test fails and names the argument with the missing description

  @SC_USM4_5
  Scenario: additionalProperties is false in every generated tool schema  [US-M4/AC-2, EC-7]
    When the inputSchema for each of the 7 tools is fetched
    Then every schema has "additionalProperties": false

  @SC_USM4_6
  Scenario: cpp_get_ast format enum is preserved in generated schema  [US-M4/AC-2, EC-8]
    When the inputSchema for cpp_get_ast is fetched
    Then the "format" property has enum values ["json", "sexpr", "graph"]
    And the default for "format" is "json"
```

---

### Feature: US-M5 — Error envelope preservation

```gherkin
Feature: Error envelope shape preserved after FastMCP migration  [US-M5]

  Background:
    Given the FastMCP server is started in stdio mode with a temp allowed root

  @SC_USM5_1
  Scenario: wrap_tool decorator is applied to all 7 registered tool functions  [US-M5/AC-1]
    Given the FastMCP migration is applied
    When app.py and tool handler files are inspected
    Then every @mcp.tool-registered function is wrapped by error_envelope.wrap_tool
    And wrap_tool is the outermost decorator

  @SC_USM5_2
  Scenario Outline: each of the 8 error codes produces the correct envelope shape  [US-M5/AC-2, C-4]
    When a tool call is triggered that produces "<error_code>"
    Then the response envelope has key "code" equal to "<error_code>"
    And the response envelope has key "message" with non-empty string value
    And the response envelope has key "tool" identifying the called tool
    And the response envelope has key "request_id" with a non-empty value
    And the response envelope contains no additional top-level keys

    Examples:
      | error_code        |
      | FILE_NOT_FOUND    |
      | INVALID_POSITION  |
      | INVALID_RANGE     |
      | INVALID_ARGUMENT  |
      | PATH_VIOLATION    |
      | DB_UNREACHABLE    |
      | PARSE_ERROR       |
      | INTERNAL_ERROR    |

  @SC_USM5_3
  Scenario: _sanitize_message redacts absolute paths from error messages  [US-M5/AC-3]
    When a tool call results in an error whose raw message contains an absolute path outside the response
    Then the error envelope message does not contain that absolute path
    And the path is replaced with "<redacted>"

  @SC_USM5_4
  Scenario: mask_error_details=True is set on the FastMCP constructor  [US-M5/AC-4]
    Given the FastMCP migration is applied
    When the FastMCP constructor call is inspected in app.py
    Then the keyword argument mask_error_details=True is present

  @SC_USM5_5
  # OQ-2: exact wire mechanism unresolved — needs-clarification
  Scenario: envelope is visible to MCP client as tool result payload  [US-M5/AC-5]
    When a tool call produces a PATH_VIOLATION error
    Then the MCP response type is a tool result (not a JSON-RPC error)
    And the result payload contains the keys code, message, tool, request_id
    # needs-clarification: mechanism (return dict / ToolResult structured_content / middleware) confirmed in ADR

  @SC_USM5_6
  Scenario: unwrapped exception from tool function does not leak stack trace to client  [EC-3, US-M5/AC-4]
    Given a tool function that raises a bare RuntimeError bypassing wrap_tool
    When that tool is called
    Then the client response does not contain a Python traceback
    And the client response has code "INTERNAL_ERROR" or an opaque FastMCP error (mask_error_details=True)
```

---

### Feature: US-M6 — Lifespan: libclang index + TU cache lifecycle

```gherkin
Feature: FastMCP lifespan manages ClangSession lifecycle  [US-M6]

  @SC_USM6_1
  Scenario: lifespan constructs ClangSession and yields it to tools  [US-M6/AC-1]
    Given the FastMCP migration is applied
    When the server starts and the first tool call is made
    Then a ClangSession instance was constructed during lifespan startup
    And the session is accessible to the tool handler (not from a module-level global)

  @SC_USM6_2
  Scenario: server shutdown drains executor and clears cache  [US-M6/AC-2]
    Given the FastMCP server has processed at least one tool call
    When the server receives a shutdown signal
    Then session.close() is called during lifespan teardown
    And no pending executor tasks are left running after exit

  @SC_USM6_3
  Scenario: tool handlers access session via lifespan context, not module globals  [US-M6/AC-3]
    Given the FastMCP migration is applied
    When app.py and tool handler files are inspected
    Then no tool handler references a module-level ClangSession variable
    And each handler accesses the session via ctx.lifespan_context or a Depends resolver

  @SC_USM6_4
  Scenario: lifespan is invoked exactly once when HTTP transport starts  [US-M6/AC-4, EC-13]
    Given CPP_MCP_TRANSPORT is "http" and the server starts
    When the lifespan entry count is checked
    Then the lifespan context manager was entered exactly once

  @SC_USM6_5
  Scenario: ConfigError on missing CPP_MCP_ALLOWED_ROOTS causes exit 1 in lifespan  [US-M6/AC-5, EC-11, C-5]
    Given CPP_MCP_ALLOWED_ROOTS is unset
    When the server is started
    Then the lifespan raises ConfigError
    And the process exits with code 1
    And a sanitized error message appears on stderr
    And no MCP frames appear on stdout

  @SC_USM6_6
  Scenario: ConfigError when libclang cannot be loaded causes exit 1 in lifespan  [US-M6/AC-5, EC-12]
    Given libclang is not available (LD_LIBRARY_PATH excludes it)
    When the server is started
    Then the lifespan raises ConfigError
    And the process exits with code 1
    And a sanitized error message appears on stderr

  @SC_USM6_7
  Scenario: in-flight tool call completes before lifespan teardown closes executor  [EC-4, US-M6/AC-2]
    Given the server has received a tool call that takes non-trivial time
    When a shutdown signal arrives during that call
    Then the in-flight call returns a result before the process exits
    And session.close() is called only after the in-flight call completes
```

---

### Feature: US-M7 — libclang thread-affinity preservation (ADR-2)

```gherkin
Feature: libclang serialized through single-worker executor  [US-M7]

  @SC_USM7_1
  Scenario: all libclang work runs inside ThreadPoolExecutor(max_workers=1)  [US-M7/AC-1, C-8]
    Given the FastMCP migration is applied
    When clang_session.py is inspected
    Then ThreadPoolExecutor(max_workers=1) is still used
    And no tool handler calls clang.cindex methods directly outside executor.submit()

  @SC_USM7_2
  # OQ-9: sync def + executor.submit().result() pattern to be confirmed — needs-clarification
  Scenario: sync tool handlers dispatch libclang calls via ClangSession.executor  [US-M7/AC-2]
    Given the FastMCP migration converts all 7 handlers to sync def
    When a tool handler body is inspected
    Then no handler calls clang.cindex directly on the calling thread
    And each handler submits libclang work via ClangSession.executor.submit(...).result()

  @SC_USM7_3
  Scenario: N concurrent HTTP requests to cpp_get_ast all succeed with parse_count == 1  [US-M7/AC-3, C-8]
    # N = 3 minimum; confirmed per ASM-3
    # OQ-9: sync+executor pattern to be validated here
    Given the FastMCP server is running with HTTP transport and a pre-populated TU cache
    When 3 concurrent HTTP requests call cpp_get_ast on the same file
    Then all 3 responses are correct and equal
    And no clang.cindex exception is raised
    And the parse count for that file is 1 (cache hit on all but the first concurrent request)

  @SC_USM7_4
  Scenario: ADR documents sync def convention with rationale  [US-M7/AC-4]
    Given the FastMCP migration ADR is written
    When the ADR is read
    Then it states that all 7 tool handlers are sync def
    And it explains why sync def + executor.submit() is preferred over async def + asyncio.run_in_executor()
```

---

### Feature: US-M8 — fastmcp version pin

```gherkin
Feature: fastmcp dependency version-pinned  [US-M8]

  @SC_USM8_1
  Scenario: pyproject.toml pins fastmcp to a minor version  [US-M8/AC-1]
    When pyproject.toml is read
    Then the fastmcp dependency specifier is "~=3.1.0" or stricter

  @SC_USM8_2
  Scenario: uv.lock is committed and consistent with pyproject.toml  [US-M8/AC-2]
    Given uv.lock exists at the project root
    When "uv lock --check" is executed
    Then the exit code is 0 (lockfile is up-to-date)

  @SC_USM8_3
  Scenario: runbook.md documents the FastMCP upgrade check procedure  [US-M8/AC-3]
    When runbook.md is read
    Then it contains a section describing how to evaluate a new FastMCP release before upgrading
    And it references the "~=3.1.0" pin rationale
```

---

### Feature: US-M9 — ADR-10 supersession

```gherkin
Feature: ADR-10 superseded by ADR-11  [US-M9]

  @SC_USM9_1
  # OQ-1: ADR-11 location (v1/ vs v2/) unresolved — needs-clarification
  Scenario: adr-11.md exists with Status accepted and Supersedes ADR-10  [US-M9/AC-1]
    Given the FastMCP migration ADRs are written
    When adr-11.md is read
    Then Status is "accepted"
    And the header contains "Supersedes: ADR-10"
    # needs-clarification: exact file path (v1/adr-11.md vs v2/adr-1.md) confirmed by architect

  @SC_USM9_2
  Scenario: ADR-10's Status line is updated to superseded  [US-M9/AC-2, EC-10]
    When adr-10.md in the v1 handoff directory is read
    Then the Status line reads "superseded by ADR-11"

  @SC_USM9_3
  Scenario: wiki cpp-mcp ADR table reflects the supersession  [US-M9/AC-3]
    When the wiki page pages/code/cpp-mcp is read
    Then the ADR table lists ADR-11 with status "accepted"
    And ADR-10 is listed as "superseded by ADR-11"

  @SC_USM9_4
  Scenario: ADR-11 cites the FastMCP wiki pages as evidence  [US-M9/AC-4]
    When adr-11.md is read
    Then it references "[[pages/manuals/fastmcp/getting-started]]"
    And it references "[[pages/manuals/fastmcp/servers]]"
```

---

## References

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements.md` — PM output (authoritative)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/CHARTER.md` — pipeline invariants
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md` — v1 scenario baseline
- `/Users/husam/workspace/cpp-mcp/tests/bdd/features/` — existing feature files (tag convention source)
- `[[pages/code/cpp-mcp]]` — architecture, ADR table, env-var list, 327/1 test baseline
- `[[pages/manuals/fastmcp/servers]]` — FastMCP lifespan, tool decorator, custom routes
- Cognee dataset: `agent-memory` (tags: `task:fastmcp-migration`, `role:business-analyst`)
