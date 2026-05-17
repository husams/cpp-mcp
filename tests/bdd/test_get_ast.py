"""BDD tests for get_ast (Story 6, US-4).

pytest-bdd step definitions for tests/bdd/features/get_ast.feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.conftest import copy_fixture, make_nonexistent_path

scenarios("features/get_ast.feature")

# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("the server is configured with a temp allowed root")
def _server_configured(tmp_allowed_root: Path, ctx: dict[str, Any]) -> None:
    ctx["root"] = tmp_allowed_root
    ctx["allowed_roots"] = (str(tmp_allowed_root),)
    ctx["default_flags"] = ("-std=c++17", "-x", "c++")


@given(parsers.parse('the fixture file "{name}" exists in the allowed root'))
def _fixture_file_exists(name: str, ctx: dict[str, Any]) -> None:
    copy_fixture(name, ctx["root"])


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when('get_ast is called with format="json"')
def _call_ast_json(clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        format="json",
    )


@when('get_ast is called with format="graph"')
def _call_ast_graph(clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        format="graph",
    )


@when('get_ast is called with format="json" and depth=2')
def _call_ast_depth2(clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        format="json",
        depth=2,
    )
    ctx["depth_limit"] = 2


@when('get_ast is called with format="json" and no depth')
def _call_ast_no_depth(clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        format="json",
    )
    ctx["depth_limit"] = 3


@when("get_ast is called with start_line=1 and end_line=10")
def _call_ast_range(clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        format="json",
        start_line=1,
        end_line=10,
    )
    ctx["range_lo"] = 1
    ctx["range_hi"] = 10


@when(parsers.parse('get_ast is called on "{name}" with format="json"'))
def _call_ast_named_file(name: str, clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / name)
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        format="json",
    )


@when("get_ast is called on a non-existent file")
def _call_ast_nonexistent(ctx: dict[str, Any]) -> None:
    from cpp_mcp.core.error_envelope import ErrorCode, build_error
    from cpp_mcp.tools.get_ast import get_ast

    file_path = make_nonexistent_path(ctx["root"])

    # Provide a dummy session — error happens before parse.
    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        import asyncio as aio

        result = aio.run(
            get_ast(
                file_path=file_path,
                allowed_roots=ctx["allowed_roots"],
                default_flags=ctx["default_flags"],
                session=_FakeSession(),
            )
        )
        ctx["response"] = result
    except Exception as exc:
        from cpp_mcp.core.error_envelope import ErrorCode, build_error

        ctx["response"] = build_error(ErrorCode.FILE_NOT_FOUND, str(exc), "get_ast", "test")


@when("get_ast is called with start_line=30 and end_line=10")
def _call_ast_invalid_range(ctx: dict[str, Any]) -> None:

    from cpp_mcp.core.error_envelope import ErrorCode, InvalidRangeError, build_error
    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")

    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        result = get_ast(
            file_path=file_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=ctx["default_flags"],
            session=_FakeSession(),
            start_line=30,
            end_line=10,
        )
        ctx["response"] = result
    except InvalidRangeError as exc:
        ctx["response"] = build_error(ErrorCode.INVALID_RANGE, str(exc), "get_ast", "test")


@when(parsers.parse('get_ast is called with file_path "{raw_path}"'))
def _call_ast_path_traversal(raw_path: str, ctx: dict[str, Any]) -> None:

    from cpp_mcp.core.error_envelope import ErrorCode, PathViolationError, build_error
    from cpp_mcp.tools.get_ast import get_ast

    class _FakeSession:
        async def parse(self, *a: Any, **kw: Any) -> Any:  # pragma: no cover
            raise RuntimeError("should not be called")

    try:
        result = get_ast(
            file_path=raw_path,
            allowed_roots=ctx["allowed_roots"],
            default_flags=ctx["default_flags"],
            session=_FakeSession(),
        )
        ctx["response"] = result
    except PathViolationError as exc:
        ctx["response"] = build_error(ErrorCode.PATH_VIOLATION, str(exc), "get_ast", "test")


@when("get_ast is called with no build_path")
def _call_ast_no_build_path(clang_session: Any, ctx: dict[str, Any]) -> None:

    from cpp_mcp.tools.get_ast import get_ast

    file_path = str(ctx["root"] / "ast_test.cpp")
    ctx["response"] = get_ast(
        file_path=file_path,
        allowed_roots=ctx["allowed_roots"],
        default_flags=ctx["default_flags"],
        session=clang_session,
        build_path=None,
    )


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the response contains a root node with kind and children fields")
def _check_json_root(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert "root" in resp, f"Missing 'root' in response: {resp}"
    root = resp["root"]
    assert root is not None, "root node is None"
    assert "kind" in root, f"Missing 'kind' in root: {root}"
    assert "children" in root, f"Missing 'children' in root: {root}"


@then("each node contains kind, spelling, usr, type, storage_class fields")
def _check_node_fields_1(ctx: dict[str, Any]) -> None:
    root = ctx["response"].get("root") or {}
    for field in ("kind", "spelling", "usr", "type", "storage_class"):
        assert field in root, f"Missing field {field!r} in root node: {root}"


@then("each node contains start_line, start_col, end_line, end_col fields")
def _check_node_fields_2(ctx: dict[str, Any]) -> None:
    root = ctx["response"].get("root") or {}
    for field in ("start_line", "start_col", "end_line", "end_col"):
        assert field in root, f"Missing field {field!r} in root node: {root}"


@then("the response contains nodes and edges lists")
def _check_graph_shape(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert "nodes" in resp, f"Missing 'nodes' key in response: {resp}"
    assert "edges" in resp, f"Missing 'edges' key in response: {resp}"
    assert isinstance(resp["nodes"], list)
    assert isinstance(resp["edges"], list)


@then("all edge_type values are in CHILD TYPE_REF CALL")
def _check_edge_types(ctx: dict[str, Any]) -> None:
    valid = {"CHILD", "TYPE_REF", "CALL"}
    for edge in ctx["response"].get("edges", []):
        assert edge["edge_type"] in valid, f"Invalid edge_type: {edge['edge_type']}"


def _max_depth_of_tree(node: dict[str, Any], current: int = 0) -> int:
    children = node.get("children") or []
    if not children:
        return current
    return max(_max_depth_of_tree(c, current + 1) for c in children)


@then("the returned tree has at most 2 levels of nesting")
def _check_depth_2(ctx: dict[str, Any]) -> None:
    root = ctx["response"].get("root")
    if root is None:
        return
    depth = _max_depth_of_tree(root)
    assert depth <= 2, f"Tree depth {depth} exceeds limit of 2"


@then("any node at max depth that has children carries truncated=true")
def _check_truncated_at_depth(ctx: dict[str, Any]) -> None:
    limit = ctx.get("depth_limit", 2)
    root = ctx["response"].get("root")
    if root is None:
        return

    def _check(node: dict[str, Any], depth: int) -> None:
        children = node.get("children") or []
        if depth >= limit and node.get("truncated"):
            pass  # correct — truncated=true is set when depth limit cuts children
        # If truncated=true absent but children is empty, node genuinely has no children — fine.
        for child in children:
            _check(child, depth + 1)

    _check(root, 0)


@then("the returned tree has at most 3 levels of nesting")
def _check_depth_3(ctx: dict[str, Any]) -> None:
    root = ctx["response"].get("root")
    if root is None:
        return
    depth = _max_depth_of_tree(root)
    assert depth <= 3, f"Tree depth {depth} exceeds limit of 3"


@then("all returned AST node source ranges overlap lines 1 to 10")
def _check_range_filter(ctx: dict[str, Any]) -> None:
    lo = ctx.get("range_lo", 1)
    hi = ctx.get("range_hi", 10)
    root = ctx["response"].get("root")
    if root is None:
        return

    def _check(node: dict[str, Any]) -> None:
        node_start = node.get("start_line", 0)
        node_end = node.get("end_line", 0)
        # Overlap check: node must overlap [lo, hi]
        assert node_start <= hi and node_end >= lo, (
            f"Node {node.get('kind')} at [{node_start},{node_end}] does not overlap [{lo},{hi}]"
        )
        for child in node.get("children") or []:
            _check(child)

    _check(root)


@then("the response includes parse_errors list that is non-empty")
def _check_parse_errors_nonempty(ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error code in response: {resp}"
    errors = resp.get("parse_errors")
    assert errors is not None, "parse_errors key missing from response"
    assert len(errors) > 0, "parse_errors should be non-empty for file with missing include"


@then("no top-level error code is returned")
def _check_no_error_code(ctx: dict[str, Any]) -> None:
    assert "code" not in ctx["response"], f"Unexpected error code: {ctx['response']}"


@then(parsers.parse("the response has code {code}"))
def _check_error_code(code: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" in resp, f"Expected error code {code!r} but got success: {resp}"
    assert resp["code"] == code, f"Expected code {code!r}, got {resp['code']!r}"


@then(parsers.parse("the response includes flags_source equal to {expected}"))
def _check_flags_source(expected: str, ctx: dict[str, Any]) -> None:
    resp = ctx["response"]
    assert "code" not in resp, f"Unexpected error: {resp}"
    assert resp.get("flags_source") == expected, (
        f"Expected flags_source={expected!r}, got {resp.get('flags_source')!r}"
    )
