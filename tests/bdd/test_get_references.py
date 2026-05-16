"""BDD step implementations for cpp_get_references feature (Story 5 / US-2)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, make_nonexistent_path, requires_libclang

scenarios("features/cpp_get_references.feature")


# ---------------------------------------------------------------------------
# Background step
# ---------------------------------------------------------------------------


@given("the MCP server is configured with a temp allowed root")
def mcp_configured_refs(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given('the file "references_test.cpp" is copied to the allowed root')
def copy_references_test(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["current_file"] = str(copy_fixture("references_test.cpp", tmp_allowed_root))


@given('the file "definition_test.cpp" is copied to the allowed root')
def copy_definition_test_refs(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["current_file"] = str(copy_fixture("definition_test.cpp", tmp_allowed_root))


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@requires_libclang
@when(parsers.parse("cpp_get_references is called with that file at line {line:d} col {col:d}"))
def call_get_references(
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
    from cpp_mcp.tools.get_references import get_references

    request_id = uuid.uuid4().hex
    try:
        result = get_references(
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
            ErrorCode.INVALID_POSITION, str(exc), "cpp_get_references", request_id
        )
        ctx["error"] = None
    except (FileNotFoundError, FileNotFoundError_) as exc:
        ctx["result"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "cpp_get_references", request_id
        )
        ctx["error"] = None
    except PathViolationError as exc:
        ctx["result"] = build_error(
            ErrorCode.PATH_VIOLATION, str(exc), "cpp_get_references", request_id
        )
        ctx["error"] = None
    except Exception as exc:
        ctx["result"] = None
        ctx["error"] = exc


@when(
    parsers.parse(
        "cpp_get_references is called with a non-existent file at line {line:d} col {col:d}"
    )
)
def call_get_references_nonexistent(
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
        ctx["result"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "cpp_get_references", request_id
        )
        ctx["error"] = None


@when(
    parsers.parse(
        'cpp_get_references is called with file_path "{path}" at line {line:d} col {col:d}'
    )
)
def call_get_references_raw_path(
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
            ErrorCode.PATH_VIOLATION, str(exc), "cpp_get_references", request_id
        )
        ctx["error"] = None


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the response contains a references list")
def assert_references_list(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict. Error: {ctx.get('error')}"
    assert "code" not in result, f"Expected success, got error: {result}"
    assert "references" in result, f"Expected 'references' field in result: {result}"
    assert isinstance(result["references"], list)


@then("each reference has file line col and context_snippet fields")
def assert_reference_fields(ctx: dict[str, Any]) -> None:
    references = ctx["result"]["references"]
    for ref in references:
        assert "file" in ref, f"Missing 'file' in reference: {ref}"
        assert "line" in ref, f"Missing 'line' in reference: {ref}"
        assert "col" in ref, f"Missing 'col' in reference: {ref}"
        assert "context_snippet" in ref, f"Missing 'context_snippet' in reference: {ref}"


@then("the references list is empty")
def assert_references_empty(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None
    assert "code" not in result, f"Expected success result, got: {result}"
    assert result["references"] == [], f"Expected empty references, got: {result['references']}"


@then(parsers.parse('the response code is "{code}"'))
def assert_response_code_refs(code: str, ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None, f"Expected a result dict, got None. Error: {ctx.get('error')}"
    assert result.get("code") == code, (
        f"Expected code={code!r}, got: {result.get('code')!r}. Full result: {result}"
    )


@then("no error code is returned")
def assert_no_error_code_refs(ctx: dict[str, Any]) -> None:
    result = ctx.get("result")
    assert result is not None
    assert "code" not in result, f"Expected no error code, got: {result.get('code')}"
