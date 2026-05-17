"""BDD step implementations for tu_cache feature (Story 7 / US-10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

from tests.bdd.conftest import copy_fixture, requires_libclang

scenarios("features/tu_cache.feature")


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_cache(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


@given('the file "tiny.cpp" is in the allowed root for cache test')
def copy_tiny_cache(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    dest = copy_fixture("tiny.cpp", tmp_allowed_root)
    ctx["current_file"] = str(dest)


@given("the server config has CACHE_CAPACITY set to 64")
def set_cache_capacity_config(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    from cpp_mcp.server.config import load_config

    config = load_config(
        env={
            "CPP_MCP_ALLOWED_ROOTS": str(tmp_allowed_root),
            "CPP_MCP_CACHE_CAPACITY": "64",
        }
    )
    ctx["config"] = config


@requires_libclang
@when("get_definition is called via app twice for the same file")
def call_twice(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.get_definition import get_definition

    session = ClangSession(capacity=4)
    ctx["session"] = session

    # First call
    get_definition(
        file_path=ctx["current_file"],
        line=1,
        col=5,
        build_path=None,
        allowed_roots=(str(tmp_allowed_root),),
        default_flags=default_flags,
        session=session,
        request_id="cache-call-1",
    )

    # Second call — should hit cache
    result = get_definition(
        file_path=ctx["current_file"],
        line=1,
        col=5,
        build_path=None,
        allowed_roots=(str(tmp_allowed_root),),
        default_flags=default_flags,
        session=session,
        request_id="cache-call-2",
    )
    ctx["result"] = result


@requires_libclang
@when("get_definition is called via app once for that file")
def call_once(
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.get_definition import get_definition

    session = ClangSession(capacity=4)
    ctx["session"] = session

    result = get_definition(
        file_path=ctx["current_file"],
        line=1,
        col=5,
        build_path=None,
        allowed_roots=(str(tmp_allowed_root),),
        default_flags=default_flags,
        session=session,
        request_id="cache-miss-1",
    )
    ctx["result"] = result


@then("the second response has cache_hit true")
def assert_cache_hit(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert "code" not in result, f"Got error: {result}"
    assert result.get("cache_hit") is True, f"Expected cache_hit=True, got: {result}"


@then("the response has cache_hit false")
def assert_cache_miss(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert "code" not in result, f"Got error: {result}"
    assert result.get("cache_hit") is False, f"Expected cache_hit=False, got: {result}"


@then("the session exposes cache stats with cache_size and cache_capacity")
def assert_cache_stats(ctx: dict[str, Any]) -> None:
    session = ctx["session"]
    stats = session.cache_stats()
    assert "cache_size" in stats, f"Missing cache_size: {stats}"
    assert "cache_capacity" in stats, f"Missing cache_capacity: {stats}"
    assert stats["cache_size"] >= 1


@then("the config cache_capacity is 64")
def assert_config_capacity(ctx: dict[str, Any]) -> None:
    assert ctx["config"].cache_capacity == 64
