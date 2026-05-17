"""Integration smoke tests: all seven tools via the in-process mcp_client.

Covers:
  SC-V4-1-03 — each of the seven exposed tools returns a non-error response
                (or, for cpp_export_to_graphdb, a structured error envelope)
                when called with minimum valid arguments.

Design §3.1: for ``cpp_export_to_graphdb`` the parametrised smoke uses
``db_uri="bolt://invalid"`` and asserts a structured error envelope with code
``DB_UNREACHABLE`` or ``DEPENDENCY_MISSING``.  This exercises the dispatch path
through real MCP serialisation without requiring a live database daemon.

All tests use ``os.cc`` (not ``fmt-c.cc``, which is reserved for the cache-hit
toggle in test_harness_smoke.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from fastmcp import Client

_OS_CC = "test-repo/fmt/src/os.cc"
_BUILD_PATH = "test-repo/fmt/build"

# Structured error codes that are acceptable for cpp_export_to_graphdb when no
# live db is available.  Both are valid depending on whether the graphdb extra
# is installed.
_EXPORT_ACCEPTABLE_ERROR_CODES = {"DB_UNREACHABLE", "DEPENDENCY_MISSING"}

# Minimum valid arguments for each tool.
_TOOL_ARGS: list[tuple[str, dict[str, Any]]] = [
    (
        "cpp_get_ast",
        {"file_path": _OS_CC, "build_path": _BUILD_PATH},
    ),
    (
        "cpp_get_definition",
        {"file_path": _OS_CC, "line": 1, "col": 1, "build_path": _BUILD_PATH},
    ),
    (
        "cpp_get_references",
        {"file_path": _OS_CC, "line": 1, "col": 1, "build_path": _BUILD_PATH},
    ),
    (
        "cpp_get_type_info",
        {"file_path": _OS_CC, "line": 1, "col": 1, "build_path": _BUILD_PATH},
    ),
    (
        "cpp_get_header_info",
        {"file_path": _OS_CC, "build_path": _BUILD_PATH},
    ),
    (
        "cpp_get_preprocessor_state",
        {"file_path": _OS_CC, "build_path": _BUILD_PATH},
    ),
    (
        "cpp_export_to_graphdb",
        {
            "file_path_or_dir": _OS_CC,
            "build_path": _BUILD_PATH,
            "db_uri": "bolt://invalid",
        },
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize("tool_name,args", _TOOL_ARGS, ids=[t for t, _ in _TOOL_ARGS])
async def test_sc_v4_1_03_tool_smoke(
    mcp_client: Client, tool_name: str, args: dict[str, Any]
) -> None:
    """SC-V4-1-03: each tool returns a non-error or structured-error response via mcp_client.

    For all tools except ``cpp_export_to_graphdb``: asserts ``is_error=False``
    and that ``result.data`` is a non-empty mapping.

    For ``cpp_export_to_graphdb``: asserts the response is a structured error
    envelope with a recognised error code (no live daemon required).
    """
    result = await mcp_client.call_tool(tool_name, args)

    if tool_name == "cpp_export_to_graphdb":
        # Structured envelope expected — DEPENDENCY_MISSING (extra not installed)
        # or DB_UNREACHABLE (extra installed but host unreachable).
        assert result.data is not None, (
            f"{tool_name}: expected a structured error envelope, got None data"
        )
        assert isinstance(result.data, Mapping), (
            f"{tool_name}: result.data is not a mapping: {result.data!r}"
        )
        code = result.data.get("code")
        assert code in _EXPORT_ACCEPTABLE_ERROR_CODES, (
            f"{tool_name}: expected error code in {_EXPORT_ACCEPTABLE_ERROR_CODES!r}, "
            f"got {code!r}.  Full response: {result.data!r}"
        )
    else:
        assert not result.is_error, (
            f"{tool_name}: unexpected MCP-level error.  data={result.data!r}"
        )
        assert result.data is not None and isinstance(result.data, Mapping), (
            f"{tool_name}: result.data is empty or not a mapping: {result.data!r}"
        )
        assert len(result.data) > 0, f"{tool_name}: result.data is an empty mapping"
