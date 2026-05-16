"""BDD tests for cpp_export_to_graphdb (Story 8 / US-7).

Uses the FakeGraphDriver — no live Neo4j required.
Live Neo4j scenarios are tagged @neo4j and auto-skipped when NEO4J_TEST_URI
is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest_bdd import given, scenarios, then, when

from cpp_mcp.core.error_envelope import DBUnreachableError
from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord
from cpp_mcp.graphdb.schema import NODE_FILE

scenarios("features/export_to_graphdb.feature")


# ---------------------------------------------------------------------------
# In-memory fake driver (same as unit tests — duplicated for BDD isolation)
# ---------------------------------------------------------------------------


class FakeGraphDriver:
    """In-memory driver for BDD tests."""

    def __init__(self, *, fail_on_connect: bool = False) -> None:
        self.connected_uri: str | None = None
        self.nodes: list[NodeRecord] = []
        self.edges: list[EdgeRecord] = []
        self.closed = False
        self._fail_on_connect = fail_on_connect
        self._connect_called = False

    def connect(self, uri: str, **kwargs: Any) -> None:
        self._connect_called = True
        if self._fail_on_connect:
            raise DBUnreachableError(f"Simulated unreachable: {uri}")
        self.connected_uri = uri

    def upsert_nodes(self, batch: list[NodeRecord]) -> int:
        self.nodes.extend(batch)
        return len(batch)

    def upsert_edges(self, batch: list[EdgeRecord]) -> int:
        self.edges.extend(batch)
        return len(batch)

    def close(self) -> None:
        self.closed = True


_: GraphDriver = FakeGraphDriver()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_exc(exc: Exception, request_id: str = "bdd-test") -> dict[str, Any]:
    """Convert a raised exception to an error-envelope dict (mirrors wrap_tool logic)."""
    from cpp_mcp.core.error_envelope import (
        DBUnreachableError,
        DependencyMissingError,
        ErrorCode,
        FileNotFoundError_,
        InvalidArgumentError,
        PathViolationError,
        build_error,
    )

    code_map = [
        (PathViolationError, ErrorCode.PATH_VIOLATION),
        (InvalidArgumentError, ErrorCode.INVALID_ARGUMENT),
        (DependencyMissingError, ErrorCode.DEPENDENCY_MISSING),
        (DBUnreachableError, ErrorCode.DB_UNREACHABLE),
        (FileNotFoundError, ErrorCode.FILE_NOT_FOUND),
        (FileNotFoundError_, ErrorCode.FILE_NOT_FOUND),
    ]
    for exc_type, code in code_map:
        if isinstance(exc, exc_type):
            return build_error(code, str(exc), "cpp_export_to_graphdb", request_id)
    return build_error(
        ErrorCode.INTERNAL_ERROR,
        "An internal error occurred.",
        "cpp_export_to_graphdb",
        request_id,
    )


def _invoke(ctx: dict[str, Any]) -> dict[str, Any]:
    """Call the cpp_export_to_graphdb handler with select_driver patched to a fake."""
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.export_to_graphdb import cpp_export_to_graphdb

    session = ClangSession(capacity=4)

    kwargs: dict[str, Any] = {
        "file_path_or_dir": ctx.get("file_path_or_dir", ""),
        "build_path": ctx.get("build_path"),
        "db_uri": ctx.get("db_uri", "bolt://localhost:7687"),
        "allowed_roots": ctx["allowed_roots"],
        "default_flags": ("-std=c++17", "-I.", "-x", "c++"),
        "session": session,
        "request_id": "bdd-test",
    }

    fake_driver = ctx.get("fake_driver", FakeGraphDriver())
    ctx["fake_driver_instance"] = fake_driver

    # Patch select_driver (the new dispatch point) to return the fake driver.
    # This also prevents Neo4jDriver from being imported when neo4j is absent.
    with patch("cpp_mcp.tools.export_to_graphdb.select_driver", return_value=fake_driver):
        try:
            result = cpp_export_to_graphdb(**kwargs)
        except Exception as exc:
            result = _wrap_exc(exc)

    ctx["result"] = result
    session.executor.shutdown(wait=False)
    return result


def _invoke_no_patch(ctx: dict[str, Any]) -> dict[str, Any]:
    """Call the cpp_export_to_graphdb handler WITHOUT patching select_driver.

    Used for unknown-scheme validation-order tests where the real dispatch
    logic must run.
    """
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.export_to_graphdb import cpp_export_to_graphdb

    session = ClangSession(capacity=4)

    kwargs: dict[str, Any] = {
        "file_path_or_dir": ctx.get("file_path_or_dir", ""),
        "build_path": ctx.get("build_path"),
        "db_uri": ctx.get("db_uri", "bolt://localhost:7687"),
        "allowed_roots": ctx["allowed_roots"],
        "default_flags": ("-std=c++17", "-I.", "-x", "c++"),
        "session": session,
        "request_id": "bdd-test",
    }

    try:
        result = cpp_export_to_graphdb(**kwargs)
    except Exception as exc:
        result = _wrap_exc(exc)

    ctx["result"] = result
    session.executor.shutdown(wait=False)
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "projects"
    root.mkdir()
    build = root / "build"
    build.mkdir()
    return {
        "root": root,
        "build": build,
        "allowed_roots": (str(root),),
        "build_path": str(build),
        "db_uri": "bolt://localhost:7687",
        "fake_driver": FakeGraphDriver(),
    }


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("the MCP server is running with allowed root for graphdb export")
def given_server_running(ctx: dict[str, Any]) -> None:
    pass  # root is created in fixture


@given("a fake graph database driver is installed")
def given_fake_driver(ctx: dict[str, Any]) -> None:
    pass  # fake driver is already in ctx fixture


@given('a valid C++ source file "main.cpp" exists in the allowed root')
def given_main_cpp(ctx: dict[str, Any]) -> None:
    cpp = ctx["root"] / "main.cpp"
    cpp.write_text("// minimal C++ file\nint main() { return 0; }\n")
    ctx["file_path_or_dir"] = str(cpp)
    ctx["main_cpp_mtime"] = cpp.stat().st_mtime_ns
    ctx["initial_files"] = set(ctx["root"].iterdir())


@given("the graph database driver will fail to connect")
def given_driver_fails(ctx: dict[str, Any]) -> None:
    ctx["fake_driver"] = FakeGraphDriver(fail_on_connect=True)


@given("the allowed root directory contains C++ files and non-C++ files")
def given_mixed_dir(ctx: dict[str, Any]) -> None:
    root = ctx["root"]
    (root / "main.cpp").write_text("")
    (root / "util.h").write_text("")
    (root / "algo.hpp").write_text("")
    (root / "impl.cc").write_text("")
    (root / "module.cxx").write_text("")
    (root / "README.md").write_text("")
    (root / "build.py").write_text("")
    ctx["file_path_or_dir"] = str(root)


@given('the allowed root contains "good.cpp" and "broken.cpp" where broken will fail')
def given_partial_failure_files(ctx: dict[str, Any]) -> None:
    root = ctx["root"]
    (root / "good.cpp").write_text("int x = 1;\n")
    (root / "broken.cpp").write_text("// will fail\n")
    ctx["file_path_or_dir"] = str(root)

    # Wrap the fake driver to raise on bad.cpp's upsert.
    class PartialFakeDriver(FakeGraphDriver):
        _current_file: str = ""

        def upsert_nodes(self, batch: list[NodeRecord]) -> int:
            for n in batch:
                if "broken.cpp" in n["props"].get("path", ""):
                    raise RuntimeError("Simulated extraction failure for broken.cpp")
            return super().upsert_nodes(batch)

    ctx["fake_driver"] = PartialFakeDriver()


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when("cpp_export_to_graphdb is called with that file and a build path")
def when_export_single_file(ctx: dict[str, Any]) -> None:
    _invoke(ctx)


@when('cpp_export_to_graphdb is called with file "main.cpp" and unreachable db_uri')
def when_export_unreachable(ctx: dict[str, Any]) -> None:
    ctx["db_uri"] = "bolt://unreachable-host:7687"
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with the directory as input")
def when_export_directory(ctx: dict[str, Any]) -> None:
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with the directory")
def when_export_directory_partial(ctx: dict[str, Any]) -> None:
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with a non-existent file path")
def when_export_nonexistent(ctx: dict[str, Any]) -> None:
    ctx["file_path_or_dir"] = str(ctx["root"] / "nonexistent_file_xyz.cpp")
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with file_path_or_dir containing path traversal")
def when_export_path_traversal_input(ctx: dict[str, Any]) -> None:
    ctx["file_path_or_dir"] = "../../etc/passwd"
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with build_path containing path traversal")
def when_export_path_traversal_build(ctx: dict[str, Any]) -> None:
    ctx["build_path"] = "../../etc"
    _invoke(ctx)


@when("cpp_export_to_graphdb is called without a db_uri")
def when_export_no_db_uri(ctx: dict[str, Any]) -> None:
    ctx["db_uri"] = None
    _invoke(ctx)


@when("cpp_export_to_graphdb is called without a build_path")
def when_export_no_build_path(ctx: dict[str, Any]) -> None:
    ctx["build_path"] = None
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with an empty db_uri")
def when_export_empty_db_uri(ctx: dict[str, Any]) -> None:
    ctx["db_uri"] = ""
    _invoke(ctx)


@when("cpp_export_to_graphdb is called with traversal path and unknown scheme db_uri")
def when_export_traversal_unknown_scheme(ctx: dict[str, Any]) -> None:
    ctx["file_path_or_dir"] = "../../etc/passwd"
    ctx["db_uri"] = "mysql://localhost:3306"
    _invoke_no_patch(ctx)


@when("cpp_export_to_graphdb is called with non-existent path and unknown scheme db_uri")
def when_export_nonexistent_unknown_scheme(ctx: dict[str, Any]) -> None:
    ctx["file_path_or_dir"] = str(ctx["root"] / "nonexistent_xyz.cpp")
    ctx["db_uri"] = "surrealdb://localhost:8000"
    _invoke_no_patch(ctx)


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the response contains files_processed equal to 1")
def then_files_processed_1(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("files_processed") == 1, ctx["result"]


@then("the response contains no errors")
def then_no_errors(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("errors") == [], ctx["result"]


@then("graph node types include File")
def then_file_node_type(ctx: dict[str, Any]) -> None:
    fake = ctx.get("fake_driver_instance")
    if fake and isinstance(fake, FakeGraphDriver):
        labels = {n["label"] for n in fake.nodes}
        assert NODE_FILE in labels, f"Expected File node; got labels: {labels}"


@then('the response code is "DB_UNREACHABLE"')
def then_db_unreachable(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "DB_UNREACHABLE", ctx["result"]


@then("no source files are modified")
def then_no_source_modified(ctx: dict[str, Any]) -> None:
    # Verify main.cpp mtime unchanged if it was set.
    if "main_cpp_mtime" in ctx:
        cpp = ctx["root"] / "main.cpp"
        assert cpp.stat().st_mtime_ns == ctx["main_cpp_mtime"]


@then("only C++ files are processed")
def then_only_cpp_processed(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    # 5 C++ files: main.cpp, util.h, algo.hpp, impl.cc, module.cxx
    assert result.get("files_processed") == 5, result


@then("README.md and build.py are not processed")
def then_non_cpp_excluded(ctx: dict[str, Any]) -> None:
    fake = ctx.get("fake_driver_instance")
    if fake and isinstance(fake, FakeGraphDriver):
        paths = [n["props"].get("path", "") for n in fake.nodes if n["label"] == NODE_FILE]
        for p in paths:
            assert "README.md" not in p
            assert "build.py" not in p


@then("files_processed is at least 1")
def then_files_processed_at_least_1(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("files_processed", 0) >= 1, ctx["result"]


@then("the errors list contains an entry for broken.cpp")
def then_errors_contain_broken(ctx: dict[str, Any]) -> None:
    errors = ctx["result"].get("errors", [])
    assert any("broken.cpp" in e.get("file", "") for e in errors), errors


@then("no all-or-nothing rollback occurs")
def then_no_rollback(ctx: dict[str, Any]) -> None:
    # Successful file was still committed (files_processed >= 1 checked above).
    pass


@then('the response code is "FILE_NOT_FOUND"')
def then_file_not_found(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "FILE_NOT_FOUND", ctx["result"]


@then('the response code is "PATH_VIOLATION"')
def then_path_violation(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "PATH_VIOLATION", ctx["result"]


@then("no database write occurs")
def then_no_db_write(ctx: dict[str, Any]) -> None:
    fake = ctx.get("fake_driver_instance")
    if fake and isinstance(fake, FakeGraphDriver) and fake._connect_called:
        # Either never connected, or no nodes/edges written.
        assert len(fake.nodes) == 0 and len(fake.edges) == 0


@then('the mtime of "main.cpp" is unchanged after the call')
def then_mtime_unchanged(ctx: dict[str, Any]) -> None:
    cpp = ctx["root"] / "main.cpp"
    assert cpp.stat().st_mtime_ns == ctx["main_cpp_mtime"]


@then("no new files exist in the allowed root after the call")
def then_no_new_files(ctx: dict[str, Any]) -> None:
    current = set(ctx["root"].iterdir())
    initial = ctx.get("initial_files", current)
    new_files = current - initial
    assert not new_files, f"Unexpected new files: {new_files}"


@then('the response code is "INVALID_ARGUMENT"')
def then_invalid_argument(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "INVALID_ARGUMENT", ctx["result"]


@then('the message identifies "db_uri"')
def then_message_identifies_db_uri(ctx: dict[str, Any]) -> None:
    assert "db_uri" in ctx["result"].get("message", ""), ctx["result"]


@then('the message identifies "build_path"')
def then_message_identifies_build_path(ctx: dict[str, Any]) -> None:
    assert "build_path" in ctx["result"].get("message", ""), ctx["result"]


@then('the response code is not "PATH_VIOLATION"')
def then_not_path_violation(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") != "PATH_VIOLATION", ctx["result"]
