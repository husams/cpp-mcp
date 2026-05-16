"""BDD tests for cpp_get_header_info (Story 6, US-5).

pytest-bdd step definitions for tests/bdd/features/cpp_get_header_info.feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, make_nonexistent_path

scenarios("features/cpp_get_header_info.feature")

# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("the server is configured with a temp allowed root", target_fixture="ctx")
def _server_configured_hi(tmp_allowed_root: Path) -> dict[str, Any]:
    return {
        "root": tmp_allowed_root,
        "allowed_roots": (str(tmp_allowed_root),),
        "default_flags": ("-std=c++17", "-x", "c++"),
    }


@given(parsers.parse('the fixture file "{name}" exists in the allowed root'))
def _fixture_exists_hi(name: str, ctx: dict[str, Any]) -> None:
    copy_fixture(name, ctx["root"])


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when(parsers.parse('cpp_get_header_info is called on "{name}"'))
def _call_hi(name: str, clang_session: Any, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.tools.get_header_info import cpp_get_header_info

    file_path = str(ctx["root"] / name)
    ctx["response"] = asyncio.run(
        cpp_get_header_info(
            file_path=file_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=ctx["default_flags"],
            session=clang_session,
        )
    )


@when(parsers.parse('cpp_get_header_info is called on "{name}" with no build_path'))
def _call_hi_no_build(name: str, clang_session: Any, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.tools.get_header_info import cpp_get_header_info

    file_path = str(ctx["root"] / name)
    ctx["response"] = asyncio.run(
        cpp_get_header_info(
            file_path=file_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=ctx["default_flags"],
            session=clang_session,
            build_path=None,
        )
    )


@when("cpp_get_header_info is called on a non-existent file")
def _call_hi_nonexistent(ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.core.error_envelope import ErrorCode, FileNotFoundError_, build_error
    from cpp_mcp.tools.get_header_info import cpp_get_header_info

    file_path = make_nonexistent_path(ctx["root"])

    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        result = asyncio.run(
            cpp_get_header_info(
                file_path=file_path,
                allowed_roots=ctx["allowed_roots"],
                default_flags=ctx["default_flags"],
                session=_FakeSession(),
            )
        )
        ctx["response"] = result
    except (FileNotFoundError, FileNotFoundError_) as exc:
        ctx["response"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "cpp_get_header_info", "test"
        )


@when(parsers.parse('cpp_get_header_info is called with file_path "{raw_path}"'))
def _call_hi_path_traversal(raw_path: str, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.core.error_envelope import ErrorCode, PathViolationError, build_error
    from cpp_mcp.tools.get_header_info import cpp_get_header_info

    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        result = asyncio.run(
            cpp_get_header_info(
                file_path=raw_path,
                allowed_roots=ctx["allowed_roots"],
                default_flags=ctx["default_flags"],
                session=_FakeSession(),
            )
        )
        ctx["response"] = result
    except PathViolationError as exc:
        ctx["response"] = build_error(
            ErrorCode.PATH_VIOLATION, str(exc), "cpp_get_header_info", "test"
        )


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the response contains all header info fields")
def _check_hi_full_shape(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    for key in (
        "direct_includes",
        "transitive_includes",
        "exported_symbols",
        "missing_includes",
        "orphaned_includes",
    ):
        assert key in resp, f"Missing key {key!r} in response: {resp}"


@then("direct_includes is empty and transitive_includes is empty")
def _check_empty_includes(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert resp["direct_includes"] == [], f"direct_includes not empty: {resp}"
    assert resp["transitive_includes"] == [], f"transitive_includes not empty: {resp}"


@then("no error code is returned")
def _check_no_code_hi(ctx: dict[str, Any]) -> None:
    assert "code" not in ctx["response"], f"Unexpected error: {ctx['response']}"


@then("missing_includes contains the unresolvable header name")
def _check_missing_includes(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    missing = resp.get("missing_includes", [])
    assert len(missing) > 0, f"Expected non-empty missing_includes, got: {missing}"
    # The fixture includes "nonexistent_lib_12345.h"
    found = any("nonexistent" in m for m in missing)
    assert found, f"Expected to find 'nonexistent' in missing_includes: {missing}"


@then(parsers.parse("the response has code {code}"))
def _check_code_hi(code: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" in resp, f"Expected code {code!r} but no error in response: {resp}"
    assert resp["code"] == code, f"Expected {code!r}, got {resp['code']!r}"


@then(parsers.parse('orphaned_includes contains "{name}"'))
def _check_orphaned_includes(name: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    orphaned = resp.get("orphaned_includes", [])
    assert len(orphaned) > 0, f"Expected non-empty orphaned_includes, got: {orphaned}"
    found = any(name in o for o in orphaned)
    assert found, f"Expected to find {name!r} in orphaned_includes: {orphaned}"


@then(parsers.parse("the response includes flags_source equal to {expected}"))
def _check_flags_source_hi(expected: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert resp.get("flags_source") == expected, (
        f"Expected flags_source={expected!r}, got {resp.get('flags_source')!r}"
    )
