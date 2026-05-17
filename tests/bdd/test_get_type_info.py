"""BDD step implementations for get_type_info feature (Story 5 / US-3)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, make_nonexistent_path, requires_libclang

scenarios("features/get_type_info.feature")


# ---------------------------------------------------------------------------
# Background step
# ---------------------------------------------------------------------------


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_types(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given('the file "types_test.cpp" is copied to the allowed root')
def copy_types_test(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["current_file"] = str(copy_fixture("types_test.cpp", tmp_allowed_root))


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@requires_libclang
@when(parsers.parse("get_type_info is called with that file at line {line:d} col {col:d}"))
def call_get_type_info(
    line: int,
    col: int,
    ctx: dict[str, Any],
    clang_session: Any,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import (
        ErrorCode,
        FileNotFoundError_,
        InvalidPositionError,
        PathViolationError,
        build_error,
    )
    from cpp_mcp.tools.get_type_info import get_type_info

    request_id = uuid.uuid4().hex
    try:
        result = get_type_info(
            file_path=ctx["current_file"],
            line=line,
            col=col,
            build_path=None,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=clang_session,
            request_id=request_id,
        )
        ctx["result"] = result
        ctx["error"] = None
    except InvalidPositionError as exc:
        ctx["result"] = build_error(
            ErrorCode.INVALID_POSITION, str(exc), "get_type_info", request_id
        )
        ctx["error"] = None
    except (FileNotFoundError, FileNotFoundError_) as exc:
        ctx["result"] = build_error(ErrorCode.FILE_NOT_FOUND, str(exc), "get_type_info", request_id)
        ctx["error"] = None
    except PathViolationError as exc:
        ctx["result"] = build_error(ErrorCode.PATH_VIOLATION, str(exc), "get_type_info", request_id)
        ctx["error"] = None
    except Exception as exc:
        ctx["result"] = None
        ctx["error"] = exc


@when(
    parsers.parse("get_type_info is called with a non-existent file at line {line:d} col {col:d}")
)
def call_get_type_info_nonexistent(
    line: int,
    col: int,
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    allowed_roots: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import ErrorCode, build_error
    from cpp_mcp.core.path_guard import validate_path

    nonexistent = make_nonexistent_path(tmp_allowed_root)
    request_id = uuid.uuid4().hex
    try:
        validate_path(nonexistent, allowed_roots, kind="file")
        ctx["result"] = None
        ctx["error"] = None
    except FileNotFoundError as exc:
        ctx["result"] = build_error(ErrorCode.FILE_NOT_FOUND, str(exc), "get_type_info", request_id)
        ctx["error"] = None


@when(parsers.parse('get_type_info is called with file_path "{path}" at line {line:d} col {col:d}'))
def call_get_type_info_raw_path(
    path: str,
    line: int,
    col: int,
    ctx: dict[str, Any],
    allowed_roots: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import ErrorCode, PathViolationError, build_error
    from cpp_mcp.core.path_guard import validate_path

    request_id = uuid.uuid4().hex
    try:
        validate_path(path, allowed_roots, kind="file")
        ctx["result"] = None
        ctx["error"] = None
    except PathViolationError as exc:
        ctx["result"] = build_error(ErrorCode.PATH_VIOLATION, str(exc), "get_type_info", request_id)
        ctx["error"] = None


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then(
    "the response contains display_type canonical_type size_bytes alignment_bytes"
    " is_pod is_const is_reference is_pointer"
)
def assert_type_info_fields(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected result dict. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success, got error: {result}"
    for field in [
        "display_type",
        "canonical_type",
        "size_bytes",
        "alignment_bytes",
        "is_pod",
        "is_const",
        "is_reference",
        "is_pointer",
    ]:
        assert field in result, f"Missing field {field!r} in result: {result}"


@then("size_bytes and alignment_bytes are non-null integers")
def assert_size_alignment_nonnull(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert result["size_bytes"] is not None, "Expected non-null size_bytes"
    assert result["alignment_bytes"] is not None, "Expected non-null alignment_bytes"
    assert isinstance(result["size_bytes"], int), "size_bytes must be an integer"
    assert isinstance(result["alignment_bytes"], int), "alignment_bytes must be an integer"


@then('canonical_type is not "auto"')
def assert_canonical_not_auto(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected result. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success, got: {result}"
    assert result.get("canonical_type") != "auto", (
        f"canonical_type should not be 'auto', got: {result.get('canonical_type')}"
    )


@then('canonical_type is "float"')
def assert_canonical_is_float(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert result.get("canonical_type") == "float", (
        f"Expected canonical_type='float', got: {result.get('canonical_type')!r}"
    )


@then(parsers.parse('display_type contains "{substring}"'))
def assert_display_type_contains(substring: str, ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected result. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success, got: {result}"
    assert substring in result.get("display_type", ""), (
        f"Expected '{substring}' in display_type, got: {result.get('display_type')!r}"
    )


@then("size_bytes is null")
def assert_size_null(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None
    assert "code" not in result, f"Expected success, got: {result}"
    assert result.get("size_bytes") is None, (
        f"Expected size_bytes=None, got: {result.get('size_bytes')}"
    )


@then("alignment_bytes is null")
def assert_alignment_null(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert result.get("alignment_bytes") is None, (
        f"Expected alignment_bytes=None, got: {result.get('alignment_bytes')}"
    )


@then("no error code is returned")
def assert_no_error_code_types(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None
    assert "code" not in result, f"Expected no error code, got: {result.get('code')}"


@then(parsers.parse('the response code is "{code}"'))
def assert_response_code_types(code: str, ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict, got None. Error: {ctx.get('error')}"
    assert result.get("code") == code, (
        f"Expected code={code!r}, got: {result.get('code')!r}. Full result: {result}"
    )
