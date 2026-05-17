"""BDD step implementations for get_definition feature (Story 5 / US-1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, make_nonexistent_path, requires_libclang

# Register all scenarios from the feature file.
scenarios("features/get_definition.feature")


# ---------------------------------------------------------------------------
# Background step
# ---------------------------------------------------------------------------


@given("the MCP server is configured with a temp allowed root")
def mcp_configured(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given('the file "definition_test.cpp" is copied to the allowed root')
def copy_definition_test(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["current_file"] = str(copy_fixture("definition_test.cpp", tmp_allowed_root))


@given('the file "forward_decl.cpp" is copied to the allowed root')
def copy_forward_decl(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["current_file"] = str(copy_fixture("forward_decl.cpp", tmp_allowed_root))


@given('the file "macro_test.cpp" is copied to the allowed root')
def copy_macro_test(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["current_file"] = str(copy_fixture("macro_test.cpp", tmp_allowed_root))


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@requires_libclang
@when(parsers.parse("get_definition is called with that file at line {line:d} col {col:d}"))
def call_get_definition(
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
    from cpp_mcp.tools.get_definition import get_definition

    request_id = uuid.uuid4().hex
    try:
        result = get_definition(
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
            ErrorCode.INVALID_POSITION, str(exc), "get_definition", request_id
        )
        ctx["error"] = None
    except (FileNotFoundError, FileNotFoundError_) as exc:
        ctx["result"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "get_definition", request_id
        )
        ctx["error"] = None
    except PathViolationError as exc:
        ctx["result"] = build_error(
            ErrorCode.PATH_VIOLATION, str(exc), "get_definition", request_id
        )
        ctx["error"] = None
    except Exception as exc:
        ctx["result"] = None
        ctx["error"] = exc


@when(
    parsers.parse("get_definition is called with a non-existent file at line {line:d} col {col:d}")
)
def call_get_definition_nonexistent(
    line: int,
    col: int,
    ctx: dict[str, Any],
    tmp_allowed_root: Path,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import ErrorCode, FileNotFoundError_, build_error
    from cpp_mcp.core.path_guard import validate_path

    nonexistent = make_nonexistent_path(tmp_allowed_root)
    request_id = uuid.uuid4().hex
    try:
        validate_path(nonexistent, allowed_roots, kind="file")
        ctx["result"] = None
        ctx["error"] = None
    except FileNotFoundError as exc:
        ctx["result"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "get_definition", request_id
        )
        ctx["error"] = None
    except FileNotFoundError_ as exc:
        ctx["result"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "get_definition", request_id
        )
        ctx["error"] = None


@when(
    parsers.parse('get_definition is called with file_path "{path}" at line {line:d} col {col:d}')
)
def call_get_definition_raw_path(
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
        ctx["result"] = build_error(
            ErrorCode.PATH_VIOLATION, str(exc), "get_definition", request_id
        )
        ctx["error"] = None


@when(
    parsers.parse(
        "get_definition is called with that file and bad build_path"
        ' "{build_path}" line {line:d} col {col:d}'
    )
)
def call_get_definition_bad_build_path(
    build_path: str,
    line: int,
    col: int,
    ctx: dict[str, Any],
    allowed_roots: tuple[str, ...],
) -> None:
    from cpp_mcp.core.error_envelope import ErrorCode, PathViolationError, build_error
    from cpp_mcp.core.path_guard import validate_path

    request_id = uuid.uuid4().hex
    try:
        validate_path(build_path, allowed_roots, kind="dir")
        ctx["result"] = None
        ctx["error"] = None
    except PathViolationError as exc:
        ctx["result"] = build_error(
            ErrorCode.PATH_VIOLATION, str(exc), "get_definition", request_id
        )
        ctx["error"] = None


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the response contains definition_found true")
def assert_definition_found_true(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict, got None. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success, got error: {result}"
    assert result.get("definition_found") is True, f"Expected definition_found=True, got: {result}"


@then("the response contains a non-empty usr")
def assert_non_empty_usr(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert result.get("usr"), f"Expected non-empty usr, got: {result}"


@then("the file field is an absolute path")
def assert_file_is_absolute(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    file_val = result.get("file")
    assert file_val is not None, "Expected file field to be set"
    assert Path(file_val).is_absolute(), f"Expected absolute path, got: {file_val!r}"


@then(parsers.parse('the response code is "{code}"'))
def assert_response_code(code: str, ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict, got None. Error: {ctx.get('error')}"
    assert result.get("code") == code, (
        f"Expected code={code!r}, got: {result.get('code')!r}. Full result: {result}"
    )


@then("no stack trace is exposed")
def assert_no_stack_trace(ctx: dict[str, Any]) -> None:
    result = ctx.get("result", {}) or {}
    message = result.get("message", "")
    assert "Traceback" not in message, f"Stack trace found in message: {message!r}"


@then("the response contains definition_found false")
def assert_definition_found_false(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict, got None. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success result, got error: {result}"
    assert result.get("definition_found") is False, (
        f"Expected definition_found=False, got: {result}"
    )


@then("no error code is returned")
def assert_no_error_code(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None
    assert "code" not in result, f"Expected no error code, got: {result.get('code')}"


@then("the response either has definition_found true or definition_found false")
def assert_definition_found_boolean(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict, got None. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success result, got error: {result}"
    assert isinstance(result.get("definition_found"), bool), (
        f"Expected boolean definition_found, got: {result}"
    )
