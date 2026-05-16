"""BDD step implementations for error_envelope feature (Story 7 / US-13)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

scenarios("features/error_envelope.feature")

_VALID_ERROR_CODES = {
    "FILE_NOT_FOUND",
    "INVALID_POSITION",
    "INVALID_RANGE",
    "INVALID_ARGUMENT",
    "PATH_VIOLATION",
    "DB_UNREACHABLE",
    "PARSE_ERROR",
    "INTERNAL_ERROR",
}


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_envelope(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root
    ctx["allowed_roots"] = (str(tmp_allowed_root),)


@when('cpp_get_definition is called via the app with path "../../etc/passwd" line 1 col 1')
def call_via_app_path_traversal(ctx: dict[str, Any], default_flags: tuple[str, ...]) -> None:
    from cpp_mcp.core.error_envelope import wrap_tool
    from cpp_mcp.tools.get_definition import get_definition

    allowed_roots = ctx["allowed_roots"]

    @wrap_tool("cpp_get_definition")
    async def _call() -> dict[str, Any]:
        return await get_definition(
            file_path="../../etc/passwd",
            line=1,
            col=1,
            build_path=None,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=None,  # never reached — path guard raises first
            request_id="test-envelope",
        )

    ctx["result"] = asyncio.run(_call())


@when("an unexpected exception is injected into the app call")
def inject_unexpected_exception(ctx: dict[str, Any]) -> None:
    from cpp_mcp.core.error_envelope import wrap_tool

    @wrap_tool("cpp_get_definition")
    async def _bad_tool() -> dict[str, Any]:
        raise RuntimeError("unexpected boom")

    ctx["result"] = asyncio.run(_bad_tool())


@then('the response has code "PATH_VIOLATION"')
def assert_code_path_violation(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "PATH_VIOLATION", ctx["result"]


@then("the response has a non-empty message")
def assert_non_empty_message(ctx: dict[str, Any]) -> None:
    msg = ctx["result"].get("message", "")
    assert msg, f"message is empty: {ctx['result']}"


@then('the response has tool "cpp_get_definition"')
def assert_tool_name(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("tool") == "cpp_get_definition", ctx["result"]


@then("the response has a request_id")
def assert_request_id(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("request_id"), ctx["result"]


@then('the response has code "INTERNAL_ERROR"')
def assert_code_internal_error(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "INTERNAL_ERROR", ctx["result"]


@then("the message does not contain a traceback")
def assert_no_traceback(ctx: dict[str, Any]) -> None:
    msg = ctx["result"].get("message", "")
    assert "Traceback" not in msg, f"Traceback found in message: {msg!r}"
    assert "File " not in msg or "<" not in msg, f"Internal path in message: {msg!r}"


@then('the response is a dict with a "code" field')
def assert_response_is_dict_with_code(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "code" in result, f"No 'code' field: {result}"


@then("the code is one of the valid error codes")
def assert_code_is_valid(ctx: dict[str, Any]) -> None:
    code = ctx["result"].get("code")
    assert code in _VALID_ERROR_CODES, f"Invalid error code {code!r}"
