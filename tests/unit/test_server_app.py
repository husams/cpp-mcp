"""Unit tests for server/app.py tool registration (S3 rewrite).

S3 removes _TOOL_SPECS and build_app(); tests now use build_server() and
await mcp.list_tools() to verify tool registration.

Coverage:
  - All 7 tools are registered via @mcp.tool (US-M3/AC-1, US-M3/AC-2).
  - Each tool has a non-empty description (US-M3/AC-3).
  - Error envelopes are returned by wrap_tool for domain exceptions.
  - The 8 error codes map correctly (US-13/AC-2).
"""

from __future__ import annotations

import asyncio

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES: list[str] = [
    "get_definition",
    "get_references",
    "get_type_info",
    "get_ast",
    "get_header_info",
    "get_preprocessor_state",
    "ingest_code",
    "query_graphdb",
    "describe_graph_schema",
]

VALID_ERROR_CODES = {
    "FILE_NOT_FOUND",
    "INVALID_POSITION",
    "INVALID_RANGE",
    "INVALID_ARGUMENT",
    "PATH_VIOLATION",
    "DB_UNREACHABLE",
    "DEPENDENCY_MISSING",
    "PARSE_ERROR",
    "INTERNAL_ERROR",
    # v6 query-surface codes (ADR-22 / ADR-23)
    "READ_ONLY_VIOLATION",
    "QUERY_PARSE_ERROR",
    "QUERY_UNSUPPORTED",
    "QUERY_TIMEOUT",
}


@pytest.fixture()
def mcp_server():
    """Return a built FastMCP server (no transport)."""
    from cpp_mcp.server.app import build_server

    return build_server()


@pytest.fixture()
def registered_tools(mcp_server):
    """Return the list of FunctionTool objects from a fresh server."""
    return asyncio.run(mcp_server.list_tools())


# ---------------------------------------------------------------------------
# 1. Tool catalogue completeness
# ---------------------------------------------------------------------------


class TestToolCatalogue:
    """All 9 tools must be registered via @mcp.tool (7 base + 2 v6 additions)."""

    def test_tool_count_is_nine(self, registered_tools):
        names = [t.name for t in registered_tools]
        assert len(names) == 9, f"Expected 9 tools, found {len(names)}: {names}"

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_expected_tool_registered(self, tool_name: str, registered_tools):
        names = [t.name for t in registered_tools]
        assert tool_name in names, f"{tool_name!r} not found in registered tools: {names}"

    def test_no_undeclared_tools(self, registered_tools):
        names = {t.name for t in registered_tools}
        extras = names - set(EXPECTED_TOOL_NAMES)
        assert not extras, f"Undeclared tools registered: {extras}"

    def test_ingest_code_in_catalogue(self, registered_tools):
        """Explicit regression: ingest_code must appear; old name must be absent (v5 rename)."""
        names = [t.name for t in registered_tools]
        assert "ingest_code" in names
        old_name = "cpp_" + "export_to_graphdb"
        assert old_name not in names


# ---------------------------------------------------------------------------
# 2. JSON Schema shape validation
# ---------------------------------------------------------------------------


class TestToolSchemas:
    """Each tool's parameters schema must be a well-formed JSON Schema object."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_schema_top_level_type_is_object(self, tool_name: str, registered_tools):
        tool = next(t for t in registered_tools if t.name == tool_name)
        schema = tool.parameters
        assert schema.get("type") == "object", (
            f"{tool_name}: expected schema['type'] == 'object', got {schema.get('type')!r}"
        )

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_schema_has_properties(self, tool_name: str, registered_tools):
        tool = next(t for t in registered_tools if t.name == tool_name)
        schema = tool.parameters
        assert "properties" in schema, f"{tool_name}: schema missing 'properties' key"
        assert isinstance(schema["properties"], dict), (
            f"{tool_name}: schema['properties'] is not a dict"
        )
        assert len(schema["properties"]) > 0, f"{tool_name}: schema['properties'] is empty"

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_schema_has_required(self, tool_name: str, registered_tools):
        tool = next(t for t in registered_tools if t.name == tool_name)
        schema = tool.parameters
        assert "required" in schema, f"{tool_name}: schema missing 'required' key"
        assert isinstance(schema["required"], list), (
            f"{tool_name}: schema['required'] is not a list"
        )
        assert len(schema["required"]) > 0, f"{tool_name}: schema['required'] is empty"

    # Graph query tools (v6) do not take file paths; they take db_uri.
    _GRAPHDB_TOOLS: frozenset[str] = frozenset({"query_graphdb", "describe_graph_schema"})

    @pytest.mark.parametrize(
        "tool_name",
        [n for n in EXPECTED_TOOL_NAMES if n not in {"query_graphdb", "describe_graph_schema"}],
    )
    def test_schema_file_path_in_required(self, tool_name: str, registered_tools):
        """file_path (or file_path_or_dir for graphdb) must be required for C++ tools."""
        tool = next(t for t in registered_tools if t.name == tool_name)
        required = tool.parameters.get("required", [])
        has_path_param = "file_path" in required or "file_path_or_dir" in required
        assert has_path_param, (
            f"{tool_name}: neither 'file_path' nor 'file_path_or_dir' in required={required}"
        )

    @pytest.mark.parametrize("tool_name", ["query_graphdb", "describe_graph_schema"])
    def test_schema_db_uri_in_required_for_graph_tools(self, tool_name: str, registered_tools):
        """Graph query tools (v6) require db_uri instead of file_path."""
        tool = next(t for t in registered_tools if t.name == tool_name)
        required = tool.parameters.get("required", [])
        assert "db_uri" in required, f"{tool_name}: 'db_uri' not in required={required}"

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_schema_additional_properties_false(self, tool_name: str, registered_tools):
        """additionalProperties=False prevents schema drift from silently passing."""
        tool = next(t for t in registered_tools if t.name == tool_name)
        schema = tool.parameters
        assert schema.get("additionalProperties") is False, (
            f"{tool_name}: schema should have additionalProperties=False"
        )

    def test_tool_descriptions_non_empty(self, registered_tools):
        """Every tool must have a non-empty description for MCP clients."""
        for tool in registered_tools:
            assert tool.description and tool.description.strip(), (
                f"{tool.name}: description is empty"
            )


# ---------------------------------------------------------------------------
# 3. Dispatch wiring — wrap_tool converts errors to envelope (SC-US-13-2)
# ---------------------------------------------------------------------------


class TestDispatchErrorEnvelope:
    """Verify that exceptions in tool handlers return error envelopes, not raw exceptions."""

    def test_path_violation_returns_envelope_not_exception(self):
        """Calling a tool with a path-traversal input must return an error envelope dict."""
        from cpp_mcp.core.error_envelope import PathViolationError, wrap_tool

        @wrap_tool("get_definition")
        def _bomb(file_path: str, line: int, col: int) -> dict:  # type: ignore[return]
            raise PathViolationError("path traversal detected")

        result = _bomb(file_path="../../etc/passwd", line=1, col=1)

        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result!r}"
        assert result.get("code") == "PATH_VIOLATION", f"code={result.get('code')!r}"
        assert "tool" in result, "envelope missing 'tool' field"
        assert "message" in result, "envelope missing 'message' field"
        assert "request_id" in result, "envelope missing 'request_id' field"
        msg = result.get("message", "")
        assert "Traceback" not in msg, f"Traceback leaked into message: {msg!r}"

    def test_internal_error_returns_envelope_not_exception(self):
        """Unexpected exceptions (RuntimeError, etc.) become INTERNAL_ERROR envelopes."""
        from cpp_mcp.core.error_envelope import wrap_tool

        @wrap_tool("get_ast")
        def _crash(file_path: str) -> dict:  # type: ignore[return]
            raise RuntimeError("unexpected segfault in libclang binding")

        result = _crash(file_path="/projects/main.cpp")

        assert isinstance(result, dict)
        assert result.get("code") == "INTERNAL_ERROR"
        msg = result.get("message", "")
        assert "Traceback" not in msg, f"Traceback leaked: {msg!r}"
        assert "segfault" not in msg, f"Internal detail leaked: {msg!r}"
        assert "request_id" in result

    @pytest.mark.parametrize(
        "exc_class,expected_code",
        [
            ("PathViolationError", "PATH_VIOLATION"),
            ("FileNotFoundError_", "FILE_NOT_FOUND"),
            ("InvalidPositionError", "INVALID_POSITION"),
            ("InvalidRangeError", "INVALID_RANGE"),
            ("InvalidArgumentError", "INVALID_ARGUMENT"),
            ("DBUnreachableError", "DB_UNREACHABLE"),
            ("FatalParseError", "PARSE_ERROR"),
        ],
    )
    def test_all_domain_exceptions_mapped(self, exc_class: str, expected_code: str):
        """Every domain exception in the closed set maps to the correct ErrorCode."""
        import cpp_mcp.core.error_envelope as ee

        exc_type = getattr(ee, exc_class)

        @ee.wrap_tool("get_definition")
        def _raise(file_path: str, line: int, col: int) -> dict:  # type: ignore[return]
            raise exc_type("test message")

        result = _raise(file_path="/projects/x.cpp", line=1, col=1)
        assert result.get("code") == expected_code, (
            f"{exc_class} -> expected {expected_code}, got {result.get('code')!r}"
        )

    def test_error_code_is_from_valid_set(self):
        """ErrorCode enum values must be exactly the 8 codes in US-13/AC-1."""
        from cpp_mcp.core.error_envelope import ErrorCode

        actual = {str(c) for c in ErrorCode}
        assert actual == VALID_ERROR_CODES, (
            f"ErrorCode mismatch.\n  expected: {VALID_ERROR_CODES}\n  actual:   {actual}"
        )
