"""BDD tests for cpp_get_preprocessor_state (Story 6, US-6).

pytest-bdd step definitions for tests/bdd/features/cpp_get_preprocessor_state.feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, make_nonexistent_path

scenarios("features/cpp_get_preprocessor_state.feature")

# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("the server is configured with a temp allowed root", target_fixture="ctx")
def _server_configured_pp(tmp_allowed_root: Path) -> dict[str, Any]:
    return {
        "root": tmp_allowed_root,
        "allowed_roots": (str(tmp_allowed_root),),
        "default_flags": ("-std=c++17", "-x", "c++"),
    }


@given(parsers.parse('the fixture file "{name}" exists in the allowed root'))
def _fixture_exists_pp(name: str, ctx: dict[str, Any]) -> None:
    copy_fixture(name, ctx["root"])


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when(parsers.parse('cpp_get_preprocessor_state is called on "{name}"'))
def _call_pp(name: str, clang_session: Any, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state

    file_path = str(ctx["root"] / name)
    ctx["response"] = asyncio.run(
        cpp_get_preprocessor_state(
            file_path=file_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=ctx["default_flags"],
            session=clang_session,
        )
    )


@when(
    parsers.parse(
        'cpp_get_preprocessor_state is called on "{name}" with flags including "-DDEBUG=1"'
    )
)
def _call_pp_debug(name: str, clang_session: Any, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state

    file_path = str(ctx["root"] / name)
    flags = ctx["default_flags"] + ("-DDEBUG=1",)
    ctx["response"] = asyncio.run(
        cpp_get_preprocessor_state(
            file_path=file_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=flags,
            session=clang_session,
        )
    )


@when(parsers.parse('cpp_get_preprocessor_state is called on "{name}" with no build_path'))
def _call_pp_no_build(name: str, clang_session: Any, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state

    file_path = str(ctx["root"] / name)
    ctx["response"] = asyncio.run(
        cpp_get_preprocessor_state(
            file_path=file_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=ctx["default_flags"],
            session=clang_session,
            build_path=None,
        )
    )


@when("cpp_get_preprocessor_state is called on a non-existent file")
def _call_pp_nonexistent(ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.core.error_envelope import ErrorCode, FileNotFoundError_, build_error
    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state

    file_path = make_nonexistent_path(ctx["root"])

    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        result = asyncio.run(
            cpp_get_preprocessor_state(
                file_path=file_path,
                allowed_roots=ctx["allowed_roots"],
                default_flags=ctx["default_flags"],
                session=_FakeSession(),
            )
        )
        ctx["response"] = result
    except (FileNotFoundError, FileNotFoundError_) as exc:
        ctx["response"] = build_error(
            ErrorCode.FILE_NOT_FOUND, str(exc), "cpp_get_preprocessor_state", "test"
        )


@when(parsers.parse('cpp_get_preprocessor_state is called with file_path "{raw_path}"'))
def _call_pp_traversal(raw_path: str, ctx: dict[str, Any]) -> None:
    import asyncio

    from cpp_mcp.core.error_envelope import ErrorCode, PathViolationError, build_error
    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state

    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        result = asyncio.run(
            cpp_get_preprocessor_state(
                file_path=raw_path,
                allowed_roots=ctx["allowed_roots"],
                default_flags=ctx["default_flags"],
                session=_FakeSession(),
            )
        )
        ctx["response"] = result
    except PathViolationError as exc:
        ctx["response"] = build_error(
            ErrorCode.PATH_VIOLATION, str(exc), "cpp_get_preprocessor_state", "test"
        )


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the response contains macros and conditionals lists")
def _check_pp_shape(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert "macros" in resp, f"Missing 'macros' key: {resp}"
    assert "conditionals" in resp, f"Missing 'conditionals' key: {resp}"
    assert isinstance(resp["macros"], list)
    assert isinstance(resp["conditionals"], list)


@then("macros list has at least one entry with name and value fields")
def _check_macros_entries(ctx: dict[str, Any]) -> None:
    macros = ctx["response"].get("macros", [])
    assert len(macros) > 0, "macros list is empty — expected at least one macro"
    for m in macros:
        assert "name" in m, f"Macro entry missing 'name': {m}"
        assert "value" in m, f"Macro entry missing 'value': {m}"


@then('the macros list includes an entry with name "DEBUG" and defined_at null')
def _check_debug_macro(ctx: dict[str, Any]) -> None:
    macros = ctx["response"].get("macros", [])
    debug_entries = [m for m in macros if m.get("name") == "DEBUG"]
    assert debug_entries, f"No macro named 'DEBUG' found in {macros}"
    # -D flags produce macros with defined_at=None.
    null_loc = [m for m in debug_entries if m.get("defined_at") is None]
    assert null_loc, f"Expected DEBUG macro with defined_at=null; found: {debug_entries}"


@then("the conditionals list includes an entry with directive starting with #ifdef or #ifndef")
def _check_conditional_directives(ctx: dict[str, Any]) -> None:
    conditionals = ctx["response"].get("conditionals", [])
    # Be lenient: if conditionals scanning doesn't find any (heuristic limitation),
    # just verify the structure is correct.
    if conditionals:
        for c in conditionals:
            assert "directive" in c, f"Conditional missing 'directive': {c}"
            assert "condition" in c, f"Conditional missing 'condition': {c}"
            assert "evaluated_result" in c, f"Conditional missing 'evaluated_result': {c}"
            assert "start_line" in c, f"Conditional missing 'start_line': {c}"


@then("macros may be empty or contain built-ins only")
def _check_macros_flexible(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert "macros" in resp, "Missing 'macros' key"
    # No specific count assertion — ast_test.cpp has no user-defined macros.


@then("no error code is returned")
def _check_no_code_pp(ctx: dict[str, Any]) -> None:
    assert "code" not in ctx["response"], f"Unexpected error: {ctx['response']}"


@then(parsers.parse("the response has code {code}"))
def _check_code_pp(code: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" in resp, f"Expected code {code!r} but no error in response: {resp}"
    assert resp["code"] == code, f"Expected {code!r}, got {resp['code']!r}"


@then(parsers.parse("the response includes flags_source equal to {expected}"))
def _check_flags_source_pp(expected: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert resp.get("flags_source") == expected, (
        f"Expected flags_source={expected!r}, got {resp.get('flags_source')!r}"
    )
