"""Unit tests for Story S3 tool registration (US-M3 acceptance criteria).

SC_USM3_1: 7 tools registered with v1 names.
SC_USM3_2: Tool input schemas exclude dependency parameters.
SC_USM3_3: Tool descriptions match v1 description strings.
SC_USM3_4: No schema property named session/allowed_roots/default_flags/ast_*.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.fixtures.expected_tool_descriptions import EXPECTED_TOOL_DESCRIPTIONS

EXPECTED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "cpp_get_definition",
        "cpp_get_references",
        "cpp_get_type_info",
        "cpp_get_ast",
        "cpp_get_header_info",
        "cpp_get_preprocessor_state",
        "cpp_export_to_graphdb",
    }
)

DEPENDENCY_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "session",
        "allowed_roots",
        "default_flags",
        "ast_max_nodes",
        "ast_max_bytes",
    }
)


@pytest.fixture(scope="module")
def registered_tools() -> list[Any]:
    """Build server and return the list of registered FunctionTool objects."""
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    return asyncio.run(mcp.list_tools())


class TestToolCatalogue:
    """SC_USM3_1: exactly 7 tools registered with the correct v1 names."""

    def test_seven_tools_registered_with_v1_names(self, registered_tools: list[Any]) -> None:
        names = {t.name for t in registered_tools}
        assert names == EXPECTED_TOOL_NAMES, (
            f"Registered tool names differ from expected.\n"
            f"  Missing: {EXPECTED_TOOL_NAMES - names}\n"
            f"  Extra:   {names - EXPECTED_TOOL_NAMES}"
        )


class TestToolSchemas:
    """SC_USM3_2 / SC_USM3_4: dependency params excluded from input schema."""

    def test_dependency_params_excluded_from_input_schema(
        self, registered_tools: list[Any]
    ) -> None:
        for tool in registered_tools:
            schema: dict[str, Any] = tool.parameters or {}
            props: dict[str, Any] = schema.get("properties", {})
            leaked = DEPENDENCY_PARAM_NAMES & set(props.keys())
            assert not leaked, (
                f"Tool {tool.name!r} leaks dependency params into input schema: {leaked}"
            )


class TestToolDescriptions:
    """SC_USM3_3: registered description strings match the v1 strings."""

    def test_tool_descriptions_non_empty_match_v1(self, registered_tools: list[Any]) -> None:
        for tool in registered_tools:
            if tool.name not in EXPECTED_TOOL_DESCRIPTIONS:
                continue
            expected = EXPECTED_TOOL_DESCRIPTIONS[tool.name]
            actual = tool.description or ""
            assert actual, f"Tool {tool.name!r} has empty description"
            assert actual == expected, (
                f"Tool {tool.name!r} description mismatch:\n"
                f"  expected: {expected!r}\n"
                f"  actual:   {actual!r}"
            )
