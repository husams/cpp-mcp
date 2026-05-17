"""S4: Verify wrap_tool decorator is applied to every registered tool callable.

SC_USM5_1: Each registered tool's fn attribute carries __wrapped__, confirming
wrap_tool sits between the function body and FastMCP's registration shim.

US-M5/AC-1.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

EXPECTED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_definition",
        "get_references",
        "get_type_info",
        "get_ast",
        "get_header_info",
        "get_preprocessor_state",
        "ingest_code",
        "query_graphdb",
        "describe_graph_schema",
    }
)


@pytest.fixture(scope="module")
def registered_tools() -> list[Any]:
    """Build the FastMCP server and return all registered FunctionTool objects."""
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    return asyncio.run(mcp.list_tools())


class TestDecoratorOrder:
    """SC_USM5_1: wrap_tool appears in the decorator chain for every tool."""

    def test_all_tools_have_wrapped_attribute(self, registered_tools: list[Any]) -> None:
        """Every registered tool's fn must have __wrapped__ set by @wrap_tool."""
        names = {t.name for t in registered_tools}
        assert names == EXPECTED_TOOL_NAMES, (
            f"Tool name mismatch — missing: {EXPECTED_TOOL_NAMES - names}, "
            f"extra: {names - EXPECTED_TOOL_NAMES}"
        )
        for tool in registered_tools:
            fn = tool.fn
            assert hasattr(fn, "__wrapped__"), (
                f"Tool {tool.name!r}: fn does not have __wrapped__. "
                "Ensure @wrap_tool(...) is applied between @mcp.tool(...) and def."
            )

    @pytest.mark.parametrize(
        "tool_name",
        sorted(EXPECTED_TOOL_NAMES),
    )
    def test_individual_tool_is_wrapped(self, registered_tools: list[Any], tool_name: str) -> None:
        """Each tool checked individually for clearer failure messages."""
        tool = next((t for t in registered_tools if t.name == tool_name), None)
        assert tool is not None, f"Tool {tool_name!r} not registered"
        assert hasattr(tool.fn, "__wrapped__"), (
            f"Tool {tool_name!r}: @wrap_tool not applied — fn has no __wrapped__"
        )
