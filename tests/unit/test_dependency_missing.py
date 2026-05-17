"""Unit tests for the DEPENDENCY_MISSING error code (S1 / US-G1).

Covers:
- US-G1/AC-1: DependencyMissingError class exists and is a domain exception.
- US-G1/AC-2: envelope shape {code, message, tool, request_id} for DependencyMissingError.
- US-G1/AC-3: Neo4jDriver.connect raises DependencyMissingError (not DBUnreachableError)
              when the neo4j package is absent.
- US-G1/AC-4: install-command fragment present in the exception message.

ADR-13: DependencyMissingError must appear in _EXC_TO_CODE BEFORE DBUnreachableError.
"""

from __future__ import annotations

import sys

import pytest

from cpp_mcp.core.error_envelope import (
    _EXC_TO_CODE,
    DBUnreachableError,
    DependencyMissingError,
    ErrorCode,
    wrap_tool,
)

# ---------------------------------------------------------------------------
# AC-1: class exists and is an Exception subclass
# ---------------------------------------------------------------------------


class TestDependencyMissingErrorClass:
    def test_is_exception_subclass(self) -> None:
        """DependencyMissingError must inherit from Exception."""
        assert issubclass(DependencyMissingError, Exception)

    def test_instantiation(self) -> None:
        err = DependencyMissingError("some package is missing")
        assert str(err) == "some package is missing"

    def test_raise_and_catch(self) -> None:
        with pytest.raises(DependencyMissingError, match="some package"):
            raise DependencyMissingError("some package is not installed")


# ---------------------------------------------------------------------------
# AC-2: envelope shape for DependencyMissingError via wrap_tool
# ---------------------------------------------------------------------------


class TestDependencyMissingEnvelopeShape:
    _ENVELOPE_KEYS: frozenset[str] = frozenset({"code", "message", "tool", "request_id"})
    _TOOL_NAME = "ingest_code"

    def _make_result(self, msg: str) -> dict[str, str]:
        @wrap_tool(self._TOOL_NAME)
        def failing_tool() -> None:  # type: ignore[return]
            raise DependencyMissingError(msg)

        result = failing_tool()
        assert isinstance(result, dict)
        return result  # type: ignore[return-value]

    def test_envelope_keys(self) -> None:
        result = self._make_result("neo4j not installed")
        assert set(result.keys()) == self._ENVELOPE_KEYS

    def test_envelope_code_is_dependency_missing(self) -> None:
        result = self._make_result("neo4j not installed")
        assert result["code"] == ErrorCode.DEPENDENCY_MISSING

    def test_envelope_tool_name(self) -> None:
        result = self._make_result("neo4j not installed")
        assert result["tool"] == self._TOOL_NAME

    def test_envelope_request_id_is_nonempty_string(self) -> None:
        result = self._make_result("neo4j not installed")
        assert isinstance(result["request_id"], str) and result["request_id"]

    def test_envelope_message_is_nonempty_string(self) -> None:
        result = self._make_result("neo4j not installed")
        assert isinstance(result["message"], str) and result["message"]


# ---------------------------------------------------------------------------
# ADR-13: ordering in _EXC_TO_CODE
# ---------------------------------------------------------------------------


class TestExcToCodeOrdering:
    def test_dependency_missing_before_db_unreachable(self) -> None:
        """ADR-13: DependencyMissingError entry must precede DBUnreachableError entry."""
        types_in_order = [exc_type for exc_type, _ in _EXC_TO_CODE]
        dep_idx = types_in_order.index(DependencyMissingError)
        db_idx = types_in_order.index(DBUnreachableError)
        assert dep_idx < db_idx, (
            f"DependencyMissingError at position {dep_idx} must come before "
            f"DBUnreachableError at position {db_idx} in _EXC_TO_CODE"
        )

    def test_dependency_missing_maps_to_correct_code(self) -> None:
        code_map = dict(_EXC_TO_CODE)
        assert code_map[DependencyMissingError] == ErrorCode.DEPENDENCY_MISSING


# ---------------------------------------------------------------------------
# AC-3: Neo4jDriver.connect raises DependencyMissingError when neo4j absent
# ---------------------------------------------------------------------------


class TestNeo4jDriverDependencyMissing:
    def test_raises_dependency_missing_not_db_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When neo4j is absent, connect must raise DependencyMissingError."""
        monkeypatch.setitem(sys.modules, "neo4j", None)  # type: ignore[arg-type]

        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        driver = Neo4jDriver()
        with pytest.raises(DependencyMissingError):
            driver.connect("bolt://localhost:7687")

    def test_does_not_raise_db_unreachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DBUnreachableError must NOT be raised when neo4j is not installed."""
        monkeypatch.setitem(sys.modules, "neo4j", None)  # type: ignore[arg-type]

        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        driver = Neo4jDriver()
        with pytest.raises(Exception) as exc_info:
            driver.connect("bolt://localhost:7687")
        assert not isinstance(exc_info.value, DBUnreachableError), (
            "connect() must raise DependencyMissingError, not DBUnreachableError, "
            "when the neo4j package is absent"
        )


# ---------------------------------------------------------------------------
# AC-4: install-command fragment in exception message
# ---------------------------------------------------------------------------


class TestInstallCommandInMessage:
    def test_neo4j_driver_message_contains_install_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Message must include the pip install command fragment."""
        monkeypatch.setitem(sys.modules, "neo4j", None)  # type: ignore[arg-type]

        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        driver = Neo4jDriver()
        with pytest.raises(DependencyMissingError, match="pip install"):
            driver.connect("bolt://localhost:7687")

    def test_neo4j_driver_message_contains_graphdb_neo4j_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Message must reference the graphdb-neo4j extra."""
        monkeypatch.setitem(sys.modules, "neo4j", None)  # type: ignore[arg-type]

        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        driver = Neo4jDriver()
        with pytest.raises(DependencyMissingError, match="graphdb-neo4j"):
            driver.connect("bolt://localhost:7687")
