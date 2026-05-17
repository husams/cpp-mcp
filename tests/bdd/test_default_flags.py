"""BDD step implementations for default_flags feature (Story 7 / US-9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

from tests.bdd.conftest import copy_fixture, requires_libclang

scenarios("features/default_flags.feature")


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_flags(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


@given('the file "tiny.cpp" is copied to the default flags root')
def copy_tiny_flags(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    dest = copy_fixture("tiny.cpp", tmp_allowed_root)
    ctx["current_file"] = str(dest)


@given("an empty build directory exists in the allowed root")
def create_empty_build_dir(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    build_dir = tmp_allowed_root / "build_empty"
    build_dir.mkdir(exist_ok=True)
    ctx["build_path"] = str(build_dir)


@given('the server config has DEFAULT_FLAGS set to "-std=c++17"')
def set_default_flags_config(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.config import load_config

    config = load_config(
        env={
            "CPP_MCP_ALLOWED_ROOTS": str(tmp_allowed_root),
            "CPP_MCP_DEFAULT_FLAGS": "-std=c++17",
        }
    )
    ctx["config"] = config


@requires_libclang
@when("get_definition is called via app with build_path None for that file")
def call_no_build_path_flags(
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
        request_id="test-default-flags-1",
    )
    ctx["result"] = result


@requires_libclang
@when("get_definition is called via app with that build_path for that file")
def call_with_empty_build_path(
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
        build_path=ctx["build_path"],
        allowed_roots=(str(tmp_allowed_root),),
        default_flags=default_flags,
        session=session,
        request_id="test-default-flags-2",
    )
    ctx["result"] = result


@then('the response has flags_source "default"')
def assert_flags_source_default_flags(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert "code" not in result, f"Got error: {result}"
    assert result.get("flags_source") == "default", f"Expected default, got: {result}"


@then('the config default_flags contains "-std=c++17"')
def assert_config_has_std17(ctx: dict[str, Any]) -> None:
    config = ctx["config"]
    assert "-std=c++17" in config.default_flags, f"Expected -std=c++17 in {config.default_flags}"
