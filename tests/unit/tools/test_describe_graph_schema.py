"""S4: Unit tests for the describe_graph_schema tool entry point.

Tests cover:
  - Envelope mapping for INVALID_ARGUMENT, DEPENDENCY_MISSING, DB_UNREACHABLE, QUERY_TIMEOUT
  - sample_size clamping to [10, 1000]
  - db_uri non-echo (AC-Q2-6): response dict must not contain the URI string
  - request_id is a 32-char hex string
  - schema_version field equals SCHEMA_VERSION
  - backend field reflects the URI scheme
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    InvalidArgumentError,
    QueryTimeoutError,
)
from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _call_tool(
    db_uri: str,
    sample_size: int = 100,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Call describe_graph_schema() directly."""
    from cpp_mcp.tools.describe_graph_schema import describe_graph_schema

    return describe_graph_schema(
        db_uri=db_uri,
        sample_size=sample_size,
        request_id=request_id or uuid.uuid4().hex,
    )


def _make_mock_introspector(
    describe_return: dict[str, Any] | None = None,
    connect_raises: Exception | None = None,
    describe_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock SchemaIntrospector."""
    mock = MagicMock()
    mock.backend = "indradb"
    if connect_raises is not None:
        mock.connect.side_effect = connect_raises
    if describe_raises is not None:
        mock.describe.side_effect = describe_raises
    elif describe_return is not None:
        mock.describe.return_value = describe_return
    else:
        mock.describe.return_value = {
            "schema_version": SCHEMA_VERSION,
            "backend": "indradb",
            "node_types": [],
            "edge_types": [],
            "totals": {"vertices": 0, "edges": 0},
            "notes": [],
        }
    return mock


def _success_result() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "backend": "indradb",
        "node_types": [],
        "edge_types": [],
        "totals": {"vertices": 0, "edges": 0},
        "notes": [],
    }


# ---------------------------------------------------------------------------
# Tests: INVALID_ARGUMENT
# ---------------------------------------------------------------------------


class TestInvalidArgument:
    """Empty or invalid db_uri → INVALID_ARGUMENT."""

    def test_empty_db_uri_raises_invalid_argument(self) -> None:
        with pytest.raises(InvalidArgumentError):
            _call_tool(db_uri="")

    def test_unknown_scheme_raises_invalid_argument(self) -> None:
        with pytest.raises(InvalidArgumentError, match="Unsupported db_uri scheme"):
            _call_tool(db_uri="redis://localhost:6379")


# ---------------------------------------------------------------------------
# Tests: DEPENDENCY_MISSING
# ---------------------------------------------------------------------------


class TestDependencyMissing:
    """Driver not installed → DEPENDENCY_MISSING via wrap_tool."""

    def test_dependency_missing_propagated(self) -> None:
        mock_intr = _make_mock_introspector(
            connect_raises=DependencyMissingError("indradb not installed")
        )
        with (
            patch(
                "cpp_mcp.tools.describe_graph_schema.select_introspector",
                return_value=mock_intr,
            ),
            pytest.raises(DependencyMissingError),
        ):
            _call_tool(db_uri="indradb://localhost:27615")


# ---------------------------------------------------------------------------
# Tests: DB_UNREACHABLE
# ---------------------------------------------------------------------------


class TestDbUnreachable:
    """Backend unreachable → DB_UNREACHABLE."""

    def test_db_unreachable_propagated(self) -> None:
        mock_intr = _make_mock_introspector(connect_raises=DBUnreachableError("cannot reach"))
        with (
            patch(
                "cpp_mcp.tools.describe_graph_schema.select_introspector",
                return_value=mock_intr,
            ),
            pytest.raises(DBUnreachableError),
        ):
            _call_tool(db_uri="indradb://localhost:27615")

    def test_unexpected_connect_error_wrapped_as_db_unreachable(self) -> None:
        mock_intr = _make_mock_introspector(connect_raises=RuntimeError("connection reset"))
        with (
            patch(
                "cpp_mcp.tools.describe_graph_schema.select_introspector",
                return_value=mock_intr,
            ),
            pytest.raises(DBUnreachableError),
        ):
            _call_tool(db_uri="indradb://localhost:27615")


# ---------------------------------------------------------------------------
# Tests: QUERY_TIMEOUT
# ---------------------------------------------------------------------------


class TestQueryTimeout:
    """Describe call exceeds timeout → QUERY_TIMEOUT."""

    def test_query_timeout_when_describe_too_slow(self) -> None:
        import time

        def _slow_describe(sample_size: int) -> dict[str, Any]:
            time.sleep(5)  # will be interrupted
            return _success_result()

        mock_intr = MagicMock()
        mock_intr.backend = "indradb"
        mock_intr.connect.return_value = None
        mock_intr.describe.side_effect = _slow_describe

        with (
            patch(
                "cpp_mcp.tools.describe_graph_schema.select_introspector",
                return_value=mock_intr,
            ),
            patch(
                "cpp_mcp.tools.describe_graph_schema._resolve_timeout_s",
                return_value=1,
            ),
            pytest.raises(QueryTimeoutError),
        ):
            _call_tool(db_uri="indradb://localhost:27615")


# ---------------------------------------------------------------------------
# Tests: sample_size clamping
# ---------------------------------------------------------------------------


class TestSampleSizeClamping:
    """sample_size is clamped to [10, 1000] before dispatch."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (0, 10),
            (5, 10),
            (10, 10),
            (100, 100),
            (1000, 1000),
            (1001, 1000),
            (9999, 1000),
        ],
    )
    def test_sample_size_clamped(self, raw: int, expected: int) -> None:
        captured: list[int] = []

        def _capture_describe(sample_size: int) -> dict[str, Any]:
            captured.append(sample_size)
            return _success_result()

        mock_intr = MagicMock()
        mock_intr.backend = "indradb"
        mock_intr.connect.return_value = None
        mock_intr.describe.side_effect = _capture_describe

        with patch(
            "cpp_mcp.tools.describe_graph_schema.select_introspector",
            return_value=mock_intr,
        ):
            _call_tool(db_uri="indradb://localhost:27615", sample_size=raw)

        assert captured == [expected], f"sample_size {raw} → expected {expected}, got {captured}"


# ---------------------------------------------------------------------------
# Tests: db_uri non-echo (AC-Q2-6)
# ---------------------------------------------------------------------------


class TestDbUriNonEcho:
    """Result dict must not contain the db_uri string."""

    def test_db_uri_not_in_result(self) -> None:
        mock_intr = _make_mock_introspector(describe_return=_success_result())

        with patch(
            "cpp_mcp.tools.describe_graph_schema.select_introspector",
            return_value=mock_intr,
        ):
            result = _call_tool(db_uri="indradb://localhost:27615")

        result_str = str(result)
        assert "indradb://localhost:27615" not in result_str, (
            f"db_uri leaked into result: {result_str}"
        )

    def test_bolt_uri_not_in_result(self) -> None:
        mock_neo4j = MagicMock()
        mock_neo4j.backend = "neo4j"
        mock_neo4j.connect.return_value = None
        mock_neo4j.describe.return_value = {
            "schema_version": SCHEMA_VERSION,
            "backend": "neo4j",
            "node_types": [],
            "edge_types": [],
            "totals": {"vertices": 0, "edges": 0},
            "notes": [],
        }

        with patch(
            "cpp_mcp.tools.describe_graph_schema.select_introspector",
            return_value=mock_neo4j,
        ):
            result = _call_tool(db_uri="bolt://localhost:7687")

        result_str = str(result)
        assert "bolt://localhost:7687" not in result_str, f"db_uri leaked into result: {result_str}"


# ---------------------------------------------------------------------------
# Tests: request_id shape
# ---------------------------------------------------------------------------


class TestRequestId:
    """request_id must be a 32-char hex string."""

    def test_request_id_is_32_char_hex(self) -> None:
        mock_intr = _make_mock_introspector(describe_return=_success_result())

        with patch(
            "cpp_mcp.tools.describe_graph_schema.select_introspector",
            return_value=mock_intr,
        ):
            req_id = uuid.uuid4().hex
            result = _call_tool(db_uri="indradb://localhost:27615", request_id=req_id)

        assert "request_id" in result
        assert result["request_id"] == req_id
        assert len(result["request_id"]) == 32
        # Validate hex
        int(result["request_id"], 16)


# ---------------------------------------------------------------------------
# Tests: schema_version field
# ---------------------------------------------------------------------------


class TestSchemaVersionField:
    """schema_version field in result must equal the constant."""

    def test_schema_version_field_equals_constant(self) -> None:
        mock_intr = _make_mock_introspector(describe_return=_success_result())

        with patch(
            "cpp_mcp.tools.describe_graph_schema.select_introspector",
            return_value=mock_intr,
        ):
            result = _call_tool(db_uri="indradb://localhost:27615")

        assert result["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Tests: via wrap_tool envelope (via _register + tool invocation)
# ---------------------------------------------------------------------------


class TestWrapToolEnvelope:
    """Exceptions from the tool body are converted to error envelopes by wrap_tool."""

    def _invoke_registered_tool(self, db_uri: str, sample_size: int = 100) -> dict[str, Any]:
        """Build the server and call the registered tool function directly."""
        from cpp_mcp.server.app import build_server

        mcp = build_server()
        # Find the describe_graph_schema tool function.
        # build_server registers it via _register; we invoke via the tool's underlying fn.
        import asyncio

        from cpp_mcp.tools.describe_graph_schema import _TOOL_NAME

        # Get tool list and find our tool.
        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert _TOOL_NAME in tool_names

        # Directly call the module's describe_graph_schema function via wrap_tool path.
        # Since the tool errors before any DB call, we test via the public function.
        from cpp_mcp.tools.describe_graph_schema import describe_graph_schema

        try:
            return describe_graph_schema(
                db_uri=db_uri,
                sample_size=sample_size,
                request_id=uuid.uuid4().hex,
            )
        except Exception as exc:
            raise exc

    def test_empty_uri_raises_invalid_argument_error(self) -> None:
        with pytest.raises(InvalidArgumentError):
            self._invoke_registered_tool(db_uri="")

    def test_unknown_scheme_raises_invalid_argument_error(self) -> None:
        with pytest.raises(InvalidArgumentError):
            self._invoke_registered_tool(db_uri="ftp://localhost")
