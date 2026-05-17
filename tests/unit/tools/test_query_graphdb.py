"""Unit tests for the query_graphdb tool entry point (design §5, §7).

Tests:
  - Error envelope mapping for every error code.
  - row_limit default 200, clamp to [1, 500].
  - Truncation flag surfaced in stats.
  - request_id is a 32-char hex string.
  - backend field correct per URI scheme.
  - Timeout: concurrent.futures.TimeoutError → QUERY_TIMEOUT envelope.
"""

from __future__ import annotations

import concurrent.futures
import sys
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fake_session() -> MagicMock:
    """Return a mock ClangSession with a real ThreadPoolExecutor."""
    session = MagicMock()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    session.executor = pool
    return session


def _call_tool(
    db_uri: str = "indradb://localhost:27615",
    query: str = '{"query":"all_vertices","args":{}}',
    parameters: dict[str, Any] | None = None,
    row_limit: int = 200,
    session: Any = None,
) -> dict[str, Any]:
    """Invoke query_graphdb_tool directly (bypassing FastMCP wiring)."""
    from cpp_mcp.tools.query_graphdb import _register

    if session is None:
        session = _fake_session()

    # Build a minimal mcp stub that captures the decorated function.
    captured: dict[str, Any] = {}

    class _FakeMcp:
        def tool(self, **kwargs: Any) -> Any:
            def decorator(fn: Any) -> Any:
                captured["fn"] = fn
                return fn

            return decorator

    _register(_FakeMcp())
    fn = captured["fn"]
    return fn(  # type: ignore[no-any-return]
        db_uri=db_uri,
        query=query,
        parameters=parameters,
        row_limit=row_limit,
        session=session,
    )


# ---------------------------------------------------------------------------
# Monkeypatch helper: install fake_indradb and a mock executor
# ---------------------------------------------------------------------------


def _install_fake_indradb(monkeypatch: pytest.MonkeyPatch) -> Any:
    import tests.fixtures.fake_indradb as fake_indradb

    monkeypatch.setitem(sys.modules, "indradb", fake_indradb)  # type: ignore[arg-type]
    return fake_indradb


def _mock_select_executor(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any] | None = None,
    raise_exc: Exception | None = None,
    connect_exc: Exception | None = None,
) -> MagicMock:
    """Monkeypatch select_executor with a mock that returns a fake executor."""
    fake_executor = MagicMock()
    fake_executor.backend = "indradb"

    if connect_exc is not None:
        fake_executor.connect.side_effect = connect_exc
    if raise_exc is not None:
        fake_executor.execute.side_effect = raise_exc
    elif result is not None:
        fake_executor.execute.return_value = result

    monkeypatch.setattr(
        "cpp_mcp.tools.query_graphdb.select_executor",
        MagicMock(return_value=fake_executor),
    )
    return fake_executor


def _default_result() -> dict[str, Any]:
    return {
        "rows": [{"id": "abc", "t": "Function", "properties": {}}],
        "rows_returned": 1,
        "truncated": False,
        "ms": 5,
    }


# ---------------------------------------------------------------------------
# INVALID_ARGUMENT tests
# ---------------------------------------------------------------------------


class TestInvalidArgument:
    def test_empty_db_uri_returns_invalid_argument(self) -> None:
        result = _call_tool(db_uri="")
        assert result["code"] == "INVALID_ARGUMENT"

    def test_empty_query_returns_invalid_argument(self) -> None:
        result = _call_tool(query="")
        assert result["code"] == "INVALID_ARGUMENT"

    def test_unknown_scheme_returns_invalid_argument(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _call_tool(db_uri="redis://localhost:6379")
        assert result["code"] == "INVALID_ARGUMENT"


# ---------------------------------------------------------------------------
# DEPENDENCY_MISSING tests
# ---------------------------------------------------------------------------


class TestDependencyMissing:
    def test_missing_driver_returns_dependency_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cpp_mcp.core.error_envelope import DependencyMissingError

        _mock_select_executor(
            monkeypatch,
            connect_exc=DependencyMissingError("indradb not installed"),
        )
        result = _call_tool()
        assert result["code"] == "DEPENDENCY_MISSING"


# ---------------------------------------------------------------------------
# DB_UNREACHABLE tests
# ---------------------------------------------------------------------------


class TestDbUnreachable:
    def test_unreachable_backend_returns_db_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cpp_mcp.core.error_envelope import DBUnreachableError

        _mock_select_executor(
            monkeypatch,
            connect_exc=DBUnreachableError("host unreachable"),
        )
        result = _call_tool()
        assert result["code"] == "DB_UNREACHABLE"


# ---------------------------------------------------------------------------
# QUERY_PARSE_ERROR tests
# ---------------------------------------------------------------------------


class TestQueryParseError:
    def test_parse_error_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        _mock_select_executor(monkeypatch, raise_exc=QueryParseError("bad json"))
        result = _call_tool()
        assert result["code"] == "QUERY_PARSE_ERROR"


# ---------------------------------------------------------------------------
# QUERY_UNSUPPORTED tests
# ---------------------------------------------------------------------------


class TestQueryUnsupported:
    def test_unsupported_verb_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cpp_mcp.core.error_envelope import QueryUnsupportedError

        _mock_select_executor(monkeypatch, raise_exc=QueryUnsupportedError("unknown verb"))
        result = _call_tool()
        assert result["code"] == "QUERY_UNSUPPORTED"


# ---------------------------------------------------------------------------
# QUERY_TIMEOUT tests
# ---------------------------------------------------------------------------


class TestQueryTimeout:
    def test_futures_timeout_maps_to_query_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """concurrent.futures.TimeoutError from .result() → QUERY_TIMEOUT."""
        session = MagicMock()
        fut = MagicMock()
        fut.result.side_effect = concurrent.futures.TimeoutError()
        session.executor.submit.return_value = fut
        result = _call_tool(session=session)
        assert result["code"] == "QUERY_TIMEOUT"


# ---------------------------------------------------------------------------
# row_limit clamp tests
# ---------------------------------------------------------------------------


class TestRowLimitClamp:
    def _get_submitted_row_limit(self, monkeypatch: pytest.MonkeyPatch, row_limit: int) -> int:
        """Capture the row_limit passed through to _do_query_graphdb."""
        captured: dict[str, Any] = {}

        def fake_do(**kwargs: Any) -> dict[str, Any]:
            captured["row_limit"] = kwargs.get("row_limit")
            return {
                "rows": [],
                "stats": {"backend": "indradb", "ms": 1, "rows_returned": 0, "truncated": False},
                "request_id": uuid.uuid4().hex,
            }

        monkeypatch.setattr("cpp_mcp.tools.query_graphdb._do_query_graphdb", fake_do)
        _call_tool(row_limit=row_limit)
        return captured.get("row_limit", -1)

    def test_default_row_limit_is_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rl = self._get_submitted_row_limit(monkeypatch, 200)
        assert rl == 200

    def test_row_limit_clamped_to_min_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rl = self._get_submitted_row_limit(monkeypatch, 0)
        assert rl == 1

    def test_row_limit_clamped_to_max_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rl = self._get_submitted_row_limit(monkeypatch, 999)
        assert rl == 500

    def test_row_limit_negative_clamped_to_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rl = self._get_submitted_row_limit(monkeypatch, -10)
        assert rl == 1

    def test_row_limit_500_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rl = self._get_submitted_row_limit(monkeypatch, 500)
        assert rl == 500


# ---------------------------------------------------------------------------
# Success-path tests
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_request_id_is_32_char_hex(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_select_executor(monkeypatch, result=_default_result())
        result = _call_tool()
        assert "request_id" in result
        rid = result["request_id"]
        assert isinstance(rid, str)
        assert len(rid) == 32
        assert all(c in "0123456789abcdef" for c in rid)

    def test_backend_field_correct_for_indradb(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_select_executor(monkeypatch, result=_default_result())
        result = _call_tool(db_uri="indradb://localhost:27615")
        assert result["stats"]["backend"] == "indradb"

    def test_truncation_flag_surfaced_in_stats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        truncated_result = {**_default_result(), "truncated": True, "rows_returned": 1}
        _mock_select_executor(monkeypatch, result=truncated_result)
        result = _call_tool()
        assert result["stats"]["truncated"] is True

    def test_rows_present_in_success_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_select_executor(monkeypatch, result=_default_result())
        result = _call_tool()
        assert "rows" in result
        assert isinstance(result["rows"], list)
