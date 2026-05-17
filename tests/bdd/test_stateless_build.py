"""BDD step implementations for stateless_build feature (Story 7 / US-8)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

from tests.bdd.conftest import copy_fixture, requires_libclang

scenarios("features/stateless_build.feature")


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_stateless(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


@given('the file "tiny.cpp" is in the allowed root for stateless test')
def copy_tiny_stateless(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    dest = copy_fixture("tiny.cpp", tmp_allowed_root)
    ctx["current_file"] = str(dest)


@given("the app is built")
def build_app_stateless(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    from cpp_mcp.core.clang_session import ClangSession

    ctx["session"] = ClangSession(capacity=4)
    ctx["allowed_roots"] = (str(tmp_allowed_root),)


@requires_libclang
@when("get_definition is called via app with build_path None for that file")
def call_no_build_path(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.get_definition import get_definition

    session = ClangSession(capacity=4)
    result = get_definition(
        file_path=ctx["current_file"],
        line=1,
        col=5,
        build_path=None,
        allowed_roots=(str(tmp_allowed_root),),
        default_flags=default_flags,
        session=session,
        request_id="test-stateless-1",
    )
    ctx["result"] = result


@requires_libclang
@when("get_definition is called via app with a non-existent build_path for that file")
def call_nonexistent_build_path(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.get_definition import get_definition

    empty_build = tmp_allowed_root / "empty_build"
    empty_build.mkdir(exist_ok=True)

    session = ClangSession(capacity=4)
    result = get_definition(
        file_path=ctx["current_file"],
        line=1,
        col=5,
        build_path=str(empty_build),
        allowed_roots=(str(tmp_allowed_root),),
        default_flags=default_flags,
        session=session,
        request_id="test-stateless-2",
    )
    ctx["result"] = result


@then('the response has flags_source "default"')
def assert_flags_source_default(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert "code" not in result, f"Got error: {result}"
    assert result.get("flags_source") == "default", f"Expected default, got: {result}"


@then('the app tool list does not contain a tool named "set_project_root"')
def assert_no_set_project_root(ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    names = [t.name for t in asyncio.run(mcp.list_tools())]
    assert "set_project_root" not in names, f"Unexpected: {names}"


@then('the app tool list does not contain a tool named "set_build_path"')
def assert_no_set_build_path(ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    names = [t.name for t in asyncio.run(mcp.list_tools())]
    assert "set_build_path" not in names
