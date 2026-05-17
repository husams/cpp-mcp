"""P5: MCP tool input-schema snapshot test.

Imports the FastMCP server, lists the three graph-related tools
(ingest_code, query_graphdb, describe_graph_schema), and asserts their
input JSON schemas match the committed reference fixture.

The fixture was generated on 2026-05-17 by running:
    uv run python -c "
    from cpp_mcp.server.app import build_server
    mcp = build_server()
    import asyncio, json
    tools = asyncio.run(mcp.list_tools())
    for t in tools:
        if t.name in ('ingest_code','query_graphdb','describe_graph_schema'):
            print(t.name, json.dumps(t.to_mcp_tool().inputSchema))
    "

Satisfies AC: S1-4 AC6, SC6, NC-1 (tool signature stability guarantee).
Design ref: §8 (tool signature unchanged).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture path
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tool_signatures.json"

_GRAPHDB_TOOL_NAMES = frozenset({"ingest_code", "query_graphdb", "describe_graph_schema"})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _load_fixture() -> dict[str, dict]:
    with _FIXTURE_PATH.open() as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _get_live_schemas() -> dict[str, dict]:
    """Build the FastMCP server and collect input schemas for graphdb tools."""
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    tools = asyncio.run(mcp.list_tools())
    schemas: dict[str, dict] = {}
    for tool in tools:
        if tool.name in _GRAPHDB_TOOL_NAMES:
            schemas[tool.name] = tool.to_mcp_tool().inputSchema
    return schemas


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMcpToolSignatures:
    """Snapshot tests for graph-related tool input schemas (S1-4 AC6, NC-1)."""

    def test_fixture_file_exists(self) -> None:
        """The committed snapshot fixture exists (setup guard)."""
        assert _FIXTURE_PATH.exists(), (
            f"Snapshot fixture missing: {_FIXTURE_PATH}. "
            "Re-generate with the command in this module's docstring."
        )

    @pytest.mark.parametrize("tool_name", sorted(_GRAPHDB_TOOL_NAMES))
    def test_tool_name_in_fixture(self, tool_name: str) -> None:
        """Each expected tool has an entry in the snapshot fixture."""
        fixture = _load_fixture()
        assert tool_name in fixture, (
            f"Tool {tool_name!r} missing from fixture {_FIXTURE_PATH}. "
            f"Available keys: {list(fixture.keys())}"
        )

    @pytest.mark.parametrize("tool_name", sorted(_GRAPHDB_TOOL_NAMES))
    def test_tool_input_schema_matches_snapshot(self, tool_name: str) -> None:
        """Live tool input schema matches the committed snapshot (NC-1)."""
        fixture = _load_fixture()
        live = _get_live_schemas()

        assert tool_name in live, (
            f"Tool {tool_name!r} not found in live server. Available: {list(live.keys())}"
        )

        expected = fixture[tool_name]
        actual = live[tool_name]

        assert actual == expected, (
            f"Tool {tool_name!r} input schema changed.\n"
            f"Expected:\n{json.dumps(expected, indent=2)}\n"
            f"Actual:\n{json.dumps(actual, indent=2)}\n"
            "Update the snapshot fixture if this change is intentional."
        )

    def test_all_three_graphdb_tools_present_in_server(self) -> None:
        """All three graphdb tools are registered in the server (NC-1 guard)."""
        live = _get_live_schemas()
        missing = _GRAPHDB_TOOL_NAMES - set(live.keys())
        assert not missing, f"Graph tools not registered in server: {missing}"
