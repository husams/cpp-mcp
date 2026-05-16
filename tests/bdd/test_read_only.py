"""BDD step implementations for read_only_enforcement feature (Story 7 / US-11).

QA additions (mandatory — SC-US-11-1 coverage):
  SC_US_11_1_ALL_TOOLS: Scenario Outline that exercises each of the 6 navigation
  tools and asserts mtime is unchanged after every call. Extends the developer
  baseline (cpp_get_definition only) to cover all tools required by the scenario.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, requires_libclang

scenarios("features/read_only_enforcement.feature")


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_read_only(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


@given('the file "tiny.cpp" is copied to the read-only root')
def copy_tiny_read_only(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    dest = copy_fixture("tiny.cpp", tmp_allowed_root)
    ctx["current_file"] = str(dest)


@given("the mtime of that file is recorded")
def record_mtime(ctx: dict[str, Any]) -> None:
    ctx["mtime_before"] = Path(ctx["current_file"]).stat().st_mtime_ns


@given("the app is built")
def build_app_fixture(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.app import build_app
    from cpp_mcp.server.config import load_config

    config = load_config(
        env={
            "CPP_MCP_ALLOWED_ROOTS": str(tmp_allowed_root),
            "CPP_MCP_CACHE_CAPACITY": "4",
        }
    )
    server, session = build_app(config)
    ctx["server"] = server
    ctx["session"] = session


@requires_libclang
@when("cpp_get_definition is called via the app for that file at line 1 col 5")
def call_get_definition_app_read_only(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.server.app import build_app
    from cpp_mcp.server.config import load_config

    config = load_config(
        env={
            "CPP_MCP_ALLOWED_ROOTS": str(tmp_allowed_root),
            "CPP_MCP_CACHE_CAPACITY": "4",
        }
    )
    _server, session = build_app(config)

    from cpp_mcp.tools.get_definition import get_definition

    try:
        result = asyncio.run(
            get_definition(
                file_path=ctx["current_file"],
                line=1,
                col=5,
                build_path=None,
                allowed_roots=(str(tmp_allowed_root),),
                default_flags=default_flags,
                session=session,
                request_id="test-read-only",
            )
        )
        ctx["result"] = result
    except Exception as exc:
        ctx["result"] = {"exception": str(exc)}


@requires_libclang
@when(parsers.parse("{tool_name} is called via the app for that file"))
def call_any_nav_tool(
    tool_name: str,
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    """Dispatch any of the 6 navigation tools and record the result.

    SC-US-11-1: each tool must leave the file mtime unchanged.
    This step handles the Scenario Outline rows in SC_US_11_1_ALL_TOOLS.
    """
    from cpp_mcp.server.app import build_app
    from cpp_mcp.server.config import load_config

    config = load_config(
        env={
            "CPP_MCP_ALLOWED_ROOTS": str(tmp_allowed_root),
            "CPP_MCP_CACHE_CAPACITY": "4",
        }
    )
    _server, session = build_app(config)

    file_path = ctx["current_file"]
    allowed_roots = (str(tmp_allowed_root),)
    request_id = f"test-read-only-{tool_name}"

    _DISPATCH: dict[str, Any] = {
        "cpp_get_definition": lambda: _run_get_definition(
            file_path, allowed_roots, default_flags, session, request_id
        ),
        "cpp_get_references": lambda: _run_get_references(
            file_path, allowed_roots, default_flags, session, request_id
        ),
        "cpp_get_type_info": lambda: _run_get_type_info(
            file_path, allowed_roots, default_flags, session, request_id
        ),
        "cpp_get_ast": lambda: _run_get_ast(file_path, allowed_roots, default_flags, session),
        "cpp_get_header_info": lambda: _run_get_header_info(
            file_path, allowed_roots, default_flags, session
        ),
        "cpp_get_preprocessor_state": lambda: _run_get_preprocessor_state(
            file_path, allowed_roots, default_flags, session
        ),
    }

    if tool_name not in _DISPATCH:
        raise ValueError(f"Unknown tool_name in parametrised step: {tool_name!r}")

    try:
        result = asyncio.run(_DISPATCH[tool_name]())
        ctx["result"] = result
    except Exception as exc:
        ctx["result"] = {"exception": str(exc)}


# ---------------------------------------------------------------------------
# Tool dispatch helpers (thin shims for the parametrised step above)
# ---------------------------------------------------------------------------


async def _run_get_definition(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    from cpp_mcp.tools.get_definition import get_definition

    return await get_definition(
        file_path=file_path,
        line=1,
        col=5,
        build_path=None,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )


async def _run_get_references(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    from cpp_mcp.tools.get_references import get_references

    return await get_references(
        file_path=file_path,
        line=1,
        col=5,
        build_path=None,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )


async def _run_get_type_info(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    from cpp_mcp.tools.get_type_info import get_type_info

    return await get_type_info(
        file_path=file_path,
        line=1,
        col=5,
        build_path=None,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )


async def _run_get_ast(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
) -> dict[str, Any]:
    from cpp_mcp.tools.get_ast import cpp_get_ast

    return await cpp_get_ast(
        file_path=file_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        build_path=None,
    )


async def _run_get_header_info(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
) -> dict[str, Any]:
    from cpp_mcp.tools.get_header_info import cpp_get_header_info

    return await cpp_get_header_info(
        file_path=file_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        build_path=None,
    )


async def _run_get_preprocessor_state(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
) -> dict[str, Any]:
    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state

    return await cpp_get_preprocessor_state(
        file_path=file_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        build_path=None,
    )


@then("no error envelope is returned")
def assert_no_error_envelope_read_only(ctx: dict[str, Any]) -> None:
    result = ctx.get("result", {})
    assert "code" not in result, f"Got error envelope: {result}"


@then("the mtime of that file is unchanged")
def assert_mtime_unchanged(ctx: dict[str, Any]) -> None:
    mtime_after = Path(ctx["current_file"]).stat().st_mtime_ns
    assert mtime_after == ctx["mtime_before"], (
        f"mtime changed: before={ctx['mtime_before']}, after={mtime_after}"
    )


@then('the app tool list does not contain a tool named "write_file"')
def assert_no_write_file(ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.app import _TOOL_SPECS

    names = [name for name, _, _ in _TOOL_SPECS]
    assert "write_file" not in names, f"Unexpected tool: write_file in {names}"


@then('the app tool list does not contain a tool named "patch_source"')
def assert_no_patch_source(ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.app import _TOOL_SPECS

    names = [name for name, _, _ in _TOOL_SPECS]
    assert "patch_source" not in names
