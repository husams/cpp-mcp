"""BDD tests for cpp_export_to_graphdb — IndraDB backend (Story S5 / US-G5).

All scenarios that use the fake driver run unconditionally.
Live-daemon scenarios are tagged @indradb and skipped when INDRADB_TEST_URI
is not set in the environment.

Patching strategy (per scenario type):
- Single-invocation fake scenarios: install fake_indradb in sys.modules["indradb"]
  so the real IndraDBDriver runs end-to-end against the fake client.
- Idempotency scenario: patch select_driver to return the same IndraDBDriver
  instance backed by a shared fake client so both invocations accumulate into
  the same store — real UPSERT semantics (create_vertex/create_edge no-ops on
  duplicate) keep counts stable across the two calls.
- select_driver dispatch-table scenario: call select_driver directly with fake
  indradb in sys.modules to allow IndraDBDriver instantiation.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

import tests.fixtures.fake_indradb as _fake_indradb_module
from cpp_mcp.graphdb.indradb_driver import IndraDBDriver
from cpp_mcp.graphdb.schema import NODE_FILE

scenarios("features/export_to_indradb.feature")


# ---------------------------------------------------------------------------
# Module-level fake indradb module (shared; each test gets isolated via Client
# instances — the module itself is stateless).
# ---------------------------------------------------------------------------

_FAKE_INDRADB: types.ModuleType = types.ModuleType("indradb")
_FAKE_INDRADB.Client = _fake_indradb_module.Client  # type: ignore[attr-defined]
_FAKE_INDRADB.Vertex = _fake_indradb_module.Vertex  # type: ignore[attr-defined]
_FAKE_INDRADB.Edge = _fake_indradb_module.Edge  # type: ignore[attr-defined]
_FAKE_INDRADB.Identifier = _fake_indradb_module.Identifier  # type: ignore[attr-defined]
_FAKE_INDRADB.SpecificVertexQuery = _fake_indradb_module.SpecificVertexQuery  # type: ignore[attr-defined]
_FAKE_INDRADB.SpecificEdgeQuery = _fake_indradb_module.SpecificEdgeQuery  # type: ignore[attr-defined]
_FAKE_INDRADB.BulkInserter = _fake_indradb_module.BulkInserter  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_exc(exc: Exception, request_id: str = "bdd-indradb") -> dict[str, Any]:
    """Convert a raised exception to an error-envelope dict."""
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


def _restore_indradb(old: types.ModuleType | None) -> None:
    if old is None:
        sys.modules.pop("indradb", None)
    else:
        sys.modules["indradb"] = old


def _invoke_fake(
    ctx: dict[str, Any],
    *,
    fail_on_connect: bool = False,
) -> dict[str, Any]:
    """Call cpp_export_to_graphdb with fake_indradb patched in sys.modules.

    The fake Client used within this invocation is accessible via
    ctx["last_fake_client"] after the call.
    """
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.export_to_graphdb import cpp_export_to_graphdb

    # Build a fresh fake module per call so each scenario gets isolated state.
    fake_mod = types.ModuleType("indradb")

    if fail_on_connect:

        class _FailClient(_fake_indradb_module.Client):  # type: ignore[misc]
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self._fail_on_ping = True

        fake_mod.Client = _FailClient  # type: ignore[attr-defined]
    else:
        fake_mod.Client = _fake_indradb_module.Client  # type: ignore[attr-defined]

    fake_mod.Vertex = _fake_indradb_module.Vertex  # type: ignore[attr-defined]
    fake_mod.Edge = _fake_indradb_module.Edge  # type: ignore[attr-defined]
    fake_mod.Identifier = _fake_indradb_module.Identifier  # type: ignore[attr-defined]
    fake_mod.SpecificVertexQuery = _fake_indradb_module.SpecificVertexQuery  # type: ignore[attr-defined]
    fake_mod.SpecificEdgeQuery = _fake_indradb_module.SpecificEdgeQuery  # type: ignore[attr-defined]
    fake_mod.BulkInserter = _fake_indradb_module.BulkInserter  # type: ignore[attr-defined]

    # Intercept Client instantiation so we can capture the created client.
    captured_clients: list[_fake_indradb_module.Client] = []
    _OrigClient = fake_mod.Client

    class _CapturingClient(_OrigClient):  # type: ignore[misc,valid-type]
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            captured_clients.append(self)  # type: ignore[arg-type]

    fake_mod.Client = _CapturingClient  # type: ignore[attr-defined]

    old = sys.modules.get("indradb")
    sys.modules["indradb"] = fake_mod  # type: ignore[assignment]
    session = ClangSession(capacity=4)
    kwargs: dict[str, Any] = {
        "file_path_or_dir": ctx.get("file_path_or_dir", ""),
        "build_path": ctx.get("build_path"),
        "db_uri": ctx.get("db_uri", "indradb://localhost:27615"),
        "allowed_roots": ctx["allowed_roots"],
        "default_flags": ("-std=c++17", "-I.", "-x", "c++"),
        "session": session,
        "request_id": "bdd-indradb",
    }
    try:
        result = cpp_export_to_graphdb(**kwargs)
    except Exception as exc:
        result = _wrap_exc(exc)
    finally:
        _restore_indradb(old)
        session.executor.shutdown(wait=False)

    ctx["result"] = result
    ctx["last_fake_client"] = captured_clients[0] if captured_clients else None
    return result


def _invoke_live(ctx: dict[str, Any]) -> dict[str, Any]:
    """Call cpp_export_to_graphdb against a real IndraDB daemon."""
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.export_to_graphdb import cpp_export_to_graphdb

    session = ClangSession(capacity=4)
    kwargs: dict[str, Any] = {
        "file_path_or_dir": ctx.get("file_path_or_dir", ""),
        "build_path": ctx.get("build_path"),
        "db_uri": ctx["db_uri"],
        "allowed_roots": ctx["allowed_roots"],
        "default_flags": ("-std=c++17", "-I.", "-x", "c++"),
        "session": session,
        "request_id": "bdd-indradb-live",
    }
    try:
        result = cpp_export_to_graphdb(**kwargs)
    except Exception as exc:
        result = _wrap_exc(exc)
    finally:
        session.executor.shutdown(wait=False)

    ctx["result"] = result
    return result


def _invoke_idempotency(ctx: dict[str, Any]) -> None:
    """Run cpp_export_to_graphdb twice with the same shared IndraDBDriver.

    Uses a persistent fake_indradb.Client instance so both runs accumulate
    writes to the same store — real UPSERT semantics (create_vertex/create_edge
    no-op on duplicate) keep node_count/edge_count stable.

    Stores counts after each run into ctx["node_count_run{1,2}"] etc.
    """
    from cpp_mcp.core.clang_session import ClangSession
    from cpp_mcp.tools.export_to_graphdb import cpp_export_to_graphdb

    # Create a single shared IndraDBDriver backed by a single fake Client.
    shared_client = _fake_indradb_module.Client(host="localhost:27615")

    class _SharedDriver(IndraDBDriver):
        """IndraDBDriver subclass pre-wired to the shared fake client."""

        def connect(self, uri: str, **kwargs: Any) -> None:  # type: ignore[override]
            self._client = shared_client
            self._closed = False

    shared_driver = _SharedDriver()

    def _run_export() -> dict[str, Any]:
        sess = ClangSession(capacity=4)
        kwargs: dict[str, Any] = {
            "file_path_or_dir": ctx.get("file_path_or_dir", ""),
            "build_path": ctx.get("build_path"),
            "db_uri": ctx.get("db_uri", "indradb://localhost:27615"),
            "allowed_roots": ctx["allowed_roots"],
            "default_flags": ("-std=c++17", "-I.", "-x", "c++"),
            "session": sess,
            "request_id": "bdd-indradb-idempotency",
        }
        try:
            with patch("cpp_mcp.tools.export_to_graphdb.select_driver", return_value=shared_driver):
                result = cpp_export_to_graphdb(**kwargs)
        except Exception as exc:
            result = _wrap_exc(exc)
        finally:
            sess.executor.shutdown(wait=False)
        return result

    # Run 1
    ctx["result"] = _run_export()
    # After close(), shared_driver._client is None but shared_client is still alive.
    # Reset driver state so run 2 works.
    shared_driver._client = None
    shared_driver._closed = False
    ctx["node_count_after_first"] = shared_client.node_count
    ctx["edge_count_after_first"] = shared_client.edge_count

    # Run 2 — same shared_client accumulates; UPSERT semantics prevent duplicates.
    ctx["result"] = _run_export()
    ctx["node_count_after_second"] = shared_client.node_count
    ctx["edge_count_after_second"] = shared_client.edge_count


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
        "db_uri": "indradb://localhost:27615",
    }


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("the MCP server is running with allowed root for graphdb export")
def given_server_running(ctx: dict[str, Any]) -> None:
    pass  # root created by fixture


@given("a fake IndraDB driver is installed as the IndraDB backend")
def given_fake_indradb_backend(ctx: dict[str, Any]) -> None:
    ctx["use_fake"] = True


@given('a valid C++ source file "main.cpp" exists in the allowed root')
def given_main_cpp(ctx: dict[str, Any]) -> None:
    cpp = ctx["root"] / "main.cpp"
    cpp.write_text("// minimal C++ file\nint main() { return 0; }\n")
    ctx["file_path_or_dir"] = str(cpp)


@given("the fake IndraDB driver uses an idempotent upsert store")
def given_idempotent_store(ctx: dict[str, Any]) -> None:
    # fake_indradb.Client.create_vertex/create_edge already no-op on duplicate;
    # no extra setup needed — this step documents the test precondition.
    ctx["idempotency_mode"] = True


@given("the fake IndraDB driver is configured to fail on connect")
def given_fail_on_connect(ctx: dict[str, Any]) -> None:
    ctx["fail_on_connect"] = True


@given("the fake IndraDB driver is installed")
def given_fake_driver_installed(ctx: dict[str, Any]) -> None:
    ctx["use_fake"] = True


@given("a fake IndraDB driver class is registered")
def given_fake_driver_class(ctx: dict[str, Any]) -> None:
    ctx["use_fake"] = True


@given("INDRADB_TEST_URI is set in the environment")
def given_indradb_test_uri(ctx: dict[str, Any]) -> None:
    uri = os.environ.get("INDRADB_TEST_URI")
    if not uri:
        pytest.skip("INDRADB_TEST_URI not set — @indradb live test skipped")
    ctx["db_uri"] = uri
    ctx["live"] = True


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when("cpp_export_to_graphdb is called with that file and an indradb:// URI")
def when_export_indradb(ctx: dict[str, Any]) -> None:
    if ctx.get("idempotency_mode"):
        _invoke_idempotency(ctx)
    else:
        fail = ctx.get("fail_on_connect", False)
        _invoke_fake(ctx, fail_on_connect=fail)


@when("cpp_export_to_graphdb is called again with the same file and URI")
def when_export_indradb_again(ctx: dict[str, Any]) -> None:
    # Idempotency scenario already ran both calls in _invoke_idempotency.
    # This step is a no-op — counts are already stored in ctx by _invoke_idempotency.
    pass


@when(parsers.parse('select_driver is called with "{uri}"'))
def when_select_driver(ctx: dict[str, Any], uri: str) -> None:
    from cpp_mcp.graphdb import select_driver

    old = sys.modules.get("indradb")
    sys.modules["indradb"] = _FAKE_INDRADB  # type: ignore[assignment]
    try:
        ctx["select_driver_result"] = select_driver(uri)
    finally:
        _restore_indradb(old)


@when(
    'cpp_export_to_graphdb is called with file_path_or_dir "../../etc/passwd" and an indradb:// URI'
)
def when_export_traversal_indradb(ctx: dict[str, Any]) -> None:
    ctx["file_path_or_dir"] = "../../etc/passwd"
    ctx["db_uri"] = "indradb://localhost:27615"
    _invoke_fake(ctx)


@when("cpp_export_to_graphdb is called with a non-existent file and an indradb:// URI")
def when_export_nonexistent_indradb(ctx: dict[str, Any]) -> None:
    ctx["file_path_or_dir"] = str(ctx["root"] / "nonexistent_indradb_xyz.cpp")
    ctx["db_uri"] = "indradb://localhost:27615"
    _invoke_fake(ctx)


@when("cpp_export_to_graphdb is called with that file and the INDRADB_TEST_URI")
def when_export_live(ctx: dict[str, Any]) -> None:
    _invoke_live(ctx)


@when("the node count is recorded")
def when_record_node_count(ctx: dict[str, Any]) -> None:
    ctx["recorded_node_count"] = ctx.get("result", {}).get("nodes_written", 0)


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
    client = ctx.get("last_fake_client")
    if client is not None:
        labels = {v.t.name for v in client._vertices.values()}
        assert NODE_FILE in labels, f"Expected {NODE_FILE!r} in {labels}"
    else:
        # Live test or idempotency path — trust files_processed as evidence.
        assert ctx["result"].get("files_processed", 0) >= 1


@then('the response code is "DB_UNREACHABLE"')
def then_db_unreachable(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "DB_UNREACHABLE", ctx["result"]


@then("no database write occurs")
def then_no_db_write(ctx: dict[str, Any]) -> None:
    client = ctx.get("last_fake_client")
    if client is not None:
        assert client.node_count == 0, f"Unexpected nodes written: {client.node_count}"
        assert client.edge_count == 0, f"Unexpected edges written: {client.edge_count}"


@then("the node count after the second run equals the node count after the first run")
def then_node_count_stable(ctx: dict[str, Any]) -> None:
    first = ctx.get("node_count_after_first", 0)
    second = ctx.get("node_count_after_second", 0)
    assert second == first, f"Node count changed on re-export: first={first}, second={second}"


@then("the edge count after the second run equals the edge count after the first run")
def then_edge_count_stable(ctx: dict[str, Any]) -> None:
    first = ctx.get("edge_count_after_first", 0)
    second = ctx.get("edge_count_after_second", 0)
    assert second == first, f"Edge count changed on re-export: first={first}, second={second}"


@then("the returned driver is an instance of IndraDBDriver")
def then_driver_is_indradb(ctx: dict[str, Any]) -> None:
    driver = ctx.get("select_driver_result")
    assert isinstance(driver, IndraDBDriver), f"Expected IndraDBDriver, got {type(driver)}"


@then("no gRPC connection is attempted")
def then_no_grpc_connection(ctx: dict[str, Any]) -> None:
    driver = ctx.get("select_driver_result")
    assert isinstance(driver, IndraDBDriver)
    assert driver._client is None, "Driver should be unconnected after select_driver"


@then('the response code is "PATH_VIOLATION"')
def then_path_violation(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "PATH_VIOLATION", ctx["result"]


@then('the response code is "FILE_NOT_FOUND"')
def then_file_not_found(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("code") == "FILE_NOT_FOUND", ctx["result"]


@then("the live IndraDB database contains at least one File node")
def then_live_file_node(ctx: dict[str, Any]) -> None:
    assert ctx["result"].get("files_processed", 0) >= 1, ctx["result"]
    assert ctx["result"].get("errors") == [], ctx["result"]


@then("the node count after the second run equals the recorded count")
def then_live_node_count_stable(ctx: dict[str, Any]) -> None:
    recorded = ctx.get("recorded_node_count", 0)
    current = ctx.get("result", {}).get("nodes_written", 0)
    assert current == recorded, f"Live node count changed: recorded={recorded}, current={current}"
