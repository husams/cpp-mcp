"""Integration smoke tests for the in-memory FastMCP client harness.

Covers:
  SC-V4-1-01 — session-scoped mcp_client fixture yields a connected FastMCP client
  SC-V4-1-02 — get_ast returns cache_hit=False on first call and True on repeat

Both tests use the session-scoped ``mcp_client`` fixture from tests/conftest.py
(ADR-18).  A dedicated file path (fmt-c.cc) is used here so that the cache-hit
toggle assertion is not polluted by other integration tests that also call
``get_ast`` on os.cc.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

# Fixture file chosen to be distinct from the one used in test_all_tools_smoke.py
# (os.cc) so that session cache state does not interfere with the toggle assertion.
_AST_FILE = "test-repo/fmt/src/fmt-c.cc"
_BUILD_PATH = "test-repo/fmt/build"


@pytest.mark.integration
async def test_sc_v4_1_01_mcp_client_is_connected(mcp_client: Client) -> None:
    """SC-V4-1-01: mcp_client fixture yields a live, connected FastMCP client.

    Asserts that the in-process client exposes all seven registered tools.
    No subprocess is spawned — verified by the in-memory transport (ADR-18).
    """
    tools = await mcp_client.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "get_ast",
        "get_definition",
        "get_references",
        "get_type_info",
        "get_header_info",
        "get_preprocessor_state",
        "ingest_code",
    }
    assert expected.issubset(tool_names), (
        f"Missing tools: {expected - tool_names}.  Registered: {tool_names}"
    )


@pytest.mark.integration
async def test_sc_v4_1_02_cache_hit_toggle(mcp_client: Client) -> None:
    """SC-V4-1-02: get_ast returns cache_hit=False first call, True on repeat.

    The session-scoped ClangSession persists across both calls within this test,
    which is required for the toggle to work.  Uses fmt-c.cc (not os.cc) to avoid
    a pre-warmed cache from concurrent integration tests.
    """
    args = {"file_path": _AST_FILE, "build_path": _BUILD_PATH}

    first = await mcp_client.call_tool("get_ast", args)
    assert first.data is not None, "Expected result data from first get_ast call"
    assert first.data.get("cache_hit") is False, (
        f"Expected cache_hit=False on first call; got: {first.data.get('cache_hit')!r}"
    )

    second = await mcp_client.call_tool("get_ast", args)
    assert second.data is not None, "Expected result data from second get_ast call"
    assert second.data.get("cache_hit") is True, (
        f"Expected cache_hit=True on second call; got: {second.data.get('cache_hit')!r}"
    )
