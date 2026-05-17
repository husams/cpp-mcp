"""BDD step implementations for path_traversal feature (Story 7 / US-12)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

from tests.bdd.conftest import copy_fixture, requires_libclang

scenarios("features/path_traversal.feature")


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_traversal(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


@given('the file "tiny.cpp" is copied to the path traversal root')
def copy_tiny_traversal(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    dest = copy_fixture("tiny.cpp", tmp_allowed_root)
    ctx["current_file"] = str(dest)


@when('get_definition is called via the app with path "../../etc/passwd" line 1 col 1')
def call_path_traversal_file(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import wrap_tool
    from cpp_mcp.tools.get_definition import get_definition

    @wrap_tool("get_definition")
    async def _call() -> dict[str, Any]:
        return get_definition(
            file_path="../../etc/passwd",
            line=1,
            col=1,
            build_path=None,
            allowed_roots=(str(tmp_allowed_root),),
            default_flags=default_flags,
            session=None,
            request_id="test-traversal",
        )

    ctx["result"] = asyncio.run(_call())


@when('get_definition is called with that file and bad build_path "../../etc"')
def call_path_traversal_build(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import wrap_tool
    from cpp_mcp.tools.get_definition import get_definition

    @wrap_tool("get_definition")
    async def _call() -> dict[str, Any]:
        return get_definition(
            file_path=ctx["current_file"],
            line=1,
            col=1,
            build_path="../../etc",
            allowed_roots=(str(tmp_allowed_root),),
            default_flags=default_flags,
            session=None,
            request_id="test-traversal-build",
        )

    ctx["result"] = asyncio.run(_call())


@requires_libclang
@when("get_ast is called via the app for that file")
def call_get_ast_in_root(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.core.error_envelope import wrap_tool
    from cpp_mcp.tools.get_ast import get_ast

    session = ClangSession(capacity=4)

    @wrap_tool("get_ast")
    async def _call() -> dict[str, Any]:
        return get_ast(
            file_path=ctx["current_file"],
            allowed_roots=(str(tmp_allowed_root),),
            default_flags=default_flags,
            session=session,
        )

    ctx["result"] = asyncio.run(_call())


@when("load_config is called with no ALLOWED_ROOTS set")
def call_load_config_no_roots(ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.config import ConfigError, load_config

    try:
        load_config(env={})
        ctx["config_error"] = None
    except ConfigError as exc:
        ctx["config_error"] = exc


@when('get_definition is called via the app with path "/home/user/secret.cpp" line 1 col 1')
def call_outside_allowed_root(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import wrap_tool
    from cpp_mcp.tools.get_definition import get_definition

    @wrap_tool("get_definition")
    async def _call() -> dict[str, Any]:
        return get_definition(
            file_path="/home/user/secret.cpp",
            line=1,
            col=1,
            build_path=None,
            allowed_roots=(str(tmp_allowed_root),),
            default_flags=default_flags,
            session=None,
            request_id="test-outside-root",
        )

    ctx["result"] = asyncio.run(_call())


@then('the response has code "PATH_VIOLATION"')
def assert_code_path_violation_traversal(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert result.get("code") == "PATH_VIOLATION", f"Expected PATH_VIOLATION, got: {result}"


@then("no error envelope is returned")
def assert_no_error_traversal(ctx: dict[str, Any]) -> None:
    result = ctx.get("result", {})
    assert "code" not in result, f"Got error envelope: {result}"


@then("a ConfigError is raised")
def assert_config_error(ctx: dict[str, Any]) -> None:
    assert ctx.get("config_error") is not None, "Expected ConfigError but none was raised"
