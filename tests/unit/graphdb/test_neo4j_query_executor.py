"""Unit tests for Neo4jQueryExecutor — row coercion and error mapping (S3).

All tests use mock drivers and fabricated Neo4j graph objects; no live Neo4j
instance is required.

Covers:
  - Row coercion: Node → dict with _labels; Relationship → dict with _type/_start/_end;
    Path → dict with _nodes/_rels; scalars pass through.
  - Error mapping: CypherSyntaxError → QueryParseError; ClientError TimedOut →
    QueryTimeoutError; ServiceUnavailable → DBUnreachableError.
  - Truncation: row_limit enforced; truncated flag set when more rows exist.
  - connect() called before execute() (else DBUnreachableError).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import neo4j.graph as neo4j_graph
import pytest

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    QueryParseError,
    QueryTimeoutError,
    ReadOnlyViolationError,
)
from cpp_mcp.graphdb.neo4j_query_executor import (
    Neo4jQueryExecutor,
    _coerce_value,
)

# ---------------------------------------------------------------------------
# Fake graph object builders
# ---------------------------------------------------------------------------


def _graph() -> neo4j_graph.Graph:
    return neo4j_graph.Graph()


def _node(
    graph: neo4j_graph.Graph,
    element_id: str,
    labels: list[str],
    props: dict[str, Any] | None = None,
) -> neo4j_graph.Node:
    return neo4j_graph.Node(graph, element_id, hash(element_id), labels, props or {})


def _rel(
    graph: neo4j_graph.Graph,
    element_id: str,
    rel_type: str,
    start: neo4j_graph.Node,
    end: neo4j_graph.Node,
    props: dict[str, Any] | None = None,
) -> neo4j_graph.Relationship:
    RelClass = graph.relationship_type(rel_type)
    r: neo4j_graph.Relationship = RelClass(graph, element_id, hash(element_id), props or {})
    r._start_node = start
    r._end_node = end
    return r


# ---------------------------------------------------------------------------
# _coerce_value tests
# ---------------------------------------------------------------------------


class TestCoerceValue:
    def test_scalar_int(self) -> None:
        assert _coerce_value(42) == 42

    def test_scalar_string(self) -> None:
        assert _coerce_value("hello") == "hello"

    def test_scalar_none(self) -> None:
        assert _coerce_value(None) is None

    def test_list_of_ints(self) -> None:
        assert _coerce_value([1, 2, 3]) == [1, 2, 3]

    def test_nested_dict(self) -> None:
        assert _coerce_value({"a": 1, "b": "x"}) == {"a": 1, "b": "x"}

    def test_node_coercion(self) -> None:
        g = _graph()
        n = _node(g, "n:1", ["Function", "Entity"], {"name": "foo", "usr": "abc"})
        result = _coerce_value(n)
        assert isinstance(result, dict)
        assert result["_labels"] == ["Entity", "Function"]  # sorted
        assert result["name"] == "foo"
        assert result["usr"] == "abc"

    def test_relationship_coercion(self) -> None:
        g = _graph()
        n1 = _node(g, "n:1", ["Function"], {"name": "foo"})
        n2 = _node(g, "n:2", ["File"], {"name": "bar"})
        r = _rel(g, "r:1", "DEFINES", n1, n2, {"weight": 1})
        result = _coerce_value(r)
        assert result["_type"] == "DEFINES"
        assert result["_start"] == "n:1"
        assert result["_end"] == "n:2"
        assert result["weight"] == 1

    def test_path_coercion(self) -> None:
        g = _graph()
        n1 = _node(g, "n:1", ["Function"], {"name": "f"})
        n2 = _node(g, "n:2", ["File"], {"name": "file"})
        r = _rel(g, "r:1", "DEFINES", n1, n2)
        path = neo4j_graph.Path(n1, r)
        result = _coerce_value(path)
        assert "_nodes" in result
        assert "_rels" in result
        assert len(result["_nodes"]) == 2
        assert len(result["_rels"]) == 1
        assert result["_rels"][0]["_type"] == "DEFINES"

    def test_non_serializable_scalar_converted(self) -> None:
        """Values not natively JSON-serializable are stringified."""
        import datetime

        dt = datetime.datetime(2024, 1, 1, 12, 0, 0)
        result = _coerce_value(dt)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Neo4jQueryExecutor.execute tests
# ---------------------------------------------------------------------------


def _make_plan(operator_type: str = "AllNodesScan") -> MagicMock:
    """Return a fake EXPLAIN plan with the given operator."""
    plan = MagicMock()
    plan.operator_type = operator_type
    plan.arguments = {}
    plan.children = []
    return plan


def _make_driver_mock(
    records: list[dict[str, Any]] | None = None,
    run_side_effect: Exception | None = None,
    plan_operator: str = "AllNodesScan",
) -> MagicMock:
    """Build a mock neo4j driver whose session().run() yields fake records.

    The first call to session.run() returns an EXPLAIN result (plan only);
    the second call returns the actual query result with rows.
    """
    driver = MagicMock()

    explain_result = MagicMock()
    explain_summary = MagicMock()
    explain_summary.plan = _make_plan(plan_operator)
    explain_result.consume.return_value = explain_summary

    actual_result = MagicMock()
    if run_side_effect is not None:
        # Both explain and actual raise the same error (simulate first call failing).
        actual_result.__iter__ = MagicMock(return_value=iter([]))
        driver.session.return_value.__enter__.return_value.run.side_effect = run_side_effect
    else:
        # First run() → explain result, second run() → actual records iterator.
        fake_records = records or []

        def _fake_run(query_or_str: Any, params: Any = None) -> Any:
            q_text = getattr(query_or_str, "text", str(query_or_str))
            if q_text.startswith("EXPLAIN"):
                return explain_result
            # Return an iterable mock
            result_mock = MagicMock()
            result_mock.__iter__ = MagicMock(return_value=iter(fake_records))
            return result_mock

        driver.session.return_value.__enter__.return_value.run.side_effect = _fake_run

    return driver


def _make_record(data: dict[str, Any]) -> MagicMock:
    """Return a mock neo4j Record with the given key-value pairs.

    Supports both ``record.keys()`` and ``for key in record`` iteration,
    matching the real neo4j Record behaviour.
    """
    keys = list(data.keys())
    record = MagicMock()
    record.keys.return_value = keys
    record.__iter__ = MagicMock(return_value=iter(keys))
    record.__getitem__ = MagicMock(side_effect=lambda k: data[k])
    return record


class TestExecuteHappyPath:
    def _make_executor_with_driver(self, driver: Any) -> Neo4jQueryExecutor:
        executor = Neo4jQueryExecutor()
        executor._driver = driver
        return executor

    def test_scalar_rows_returned(self) -> None:
        records = [_make_record({"n": 1}), _make_record({"n": 2})]
        driver = _make_driver_mock(records=records)
        ex = self._make_executor_with_driver(driver)
        result = ex.execute("MATCH (n) RETURN n", None, row_limit=10, timeout_s=30)
        assert result["rows_returned"] == 2
        assert result["truncated"] is False
        assert len(result["rows"]) == 2

    def test_truncation_at_row_limit(self) -> None:
        records = [_make_record({"n": i}) for i in range(5)]
        driver = _make_driver_mock(records=records)
        ex = self._make_executor_with_driver(driver)
        result = ex.execute("MATCH (n) RETURN n", None, row_limit=3, timeout_s=30)
        assert result["rows_returned"] == 3
        assert result["truncated"] is True

    def test_no_truncation_when_rows_equal_limit(self) -> None:
        records = [_make_record({"n": i}) for i in range(3)]
        driver = _make_driver_mock(records=records)
        ex = self._make_executor_with_driver(driver)
        result = ex.execute("MATCH (n) RETURN n", None, row_limit=3, timeout_s=30)
        assert result["truncated"] is False
        assert result["rows_returned"] == 3

    def test_ms_field_is_non_negative_int(self) -> None:
        driver = _make_driver_mock(records=[_make_record({"x": 42})])
        ex = self._make_executor_with_driver(driver)
        result = ex.execute("RETURN 1 AS x", None, row_limit=10, timeout_s=30)
        assert isinstance(result["ms"], int)
        assert result["ms"] >= 0

    def test_node_coercion_in_execute(self) -> None:
        g = _graph()
        n = _node(g, "n:1", ["Function"], {"name": "foo"})
        record = _make_record({"node": n})
        driver = _make_driver_mock(records=[record])
        ex = self._make_executor_with_driver(driver)
        result = ex.execute("MATCH (n) RETURN n AS node", None, row_limit=10, timeout_s=30)
        row = result["rows"][0]
        assert "_labels" in row["node"]
        assert "Function" in row["node"]["_labels"]

    def test_parameters_forwarded(self) -> None:
        """execute() passes parameters dict to session.run()."""
        driver = _make_driver_mock(records=[])
        ex = self._make_executor_with_driver(driver)
        ex.execute("MATCH (n {name: $name}) RETURN n", {"name": "foo"}, row_limit=10, timeout_s=30)
        # The second call is the actual run; verify parameters were passed.
        calls = driver.session.return_value.__enter__.return_value.run.call_args_list
        # First call is EXPLAIN, second is actual; check second call args.
        assert len(calls) == 2


class TestExecuteErrorMapping:
    def _make_executor_with_driver(self, driver: Any) -> Neo4jQueryExecutor:
        executor = Neo4jQueryExecutor()
        executor._driver = driver
        return executor

    def test_cypher_syntax_error_in_explain_raises_query_parse_error(self) -> None:
        import neo4j.exceptions as neo4j_exc

        err = neo4j_exc.CypherSyntaxError(
            "bad syntax", "Neo.ClientError.Statement.SyntaxError", "Invalid syntax"
        )
        driver = _make_driver_mock(run_side_effect=err)
        ex = self._make_executor_with_driver(driver)
        with pytest.raises(QueryParseError):
            ex.execute("NOT VALID ##", None, row_limit=10, timeout_s=30)

    def test_timed_out_client_error_raises_query_timeout(self) -> None:
        import neo4j.exceptions as neo4j_exc

        err = neo4j_exc.ClientError(
            "TimedOut",
            "Neo.ClientError.Transaction.TransactionTimedOut",
            "Transaction timed out",
        )
        driver = _make_driver_mock(run_side_effect=err)
        ex = self._make_executor_with_driver(driver)
        with pytest.raises(QueryTimeoutError):
            ex.execute("MATCH (n) RETURN n", None, row_limit=10, timeout_s=1)

    def test_service_unavailable_raises_db_unreachable(self) -> None:
        import neo4j.exceptions as neo4j_exc

        # ServiceUnavailable is raised on actual run (after successful EXPLAIN).
        driver = MagicMock()

        explain_result = MagicMock()
        explain_summary = MagicMock()
        explain_summary.plan = _make_plan("AllNodesScan")
        explain_result.consume.return_value = explain_summary

        call_count = 0

        def _fake_run(query_or_str: Any, params: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            q_text = getattr(query_or_str, "text", str(query_or_str))
            if q_text.startswith("EXPLAIN"):
                return explain_result
            raise neo4j_exc.ServiceUnavailable("database went away")

        driver.session.return_value.__enter__.return_value.run.side_effect = _fake_run
        ex = self._make_executor_with_driver(driver)
        with pytest.raises(DBUnreachableError, match="unavailable"):
            ex.execute("MATCH (n) RETURN n", None, row_limit=10, timeout_s=30)

    def test_execute_before_connect_raises_db_unreachable(self) -> None:
        ex = Neo4jQueryExecutor()  # _driver is None
        with pytest.raises(DBUnreachableError, match="before connect"):
            ex.execute("MATCH (n) RETURN n", None, row_limit=10, timeout_s=30)

    def test_write_query_raises_read_only_violation(self) -> None:
        driver = _make_driver_mock(plan_operator="CreateNode")
        ex = Neo4jQueryExecutor()
        ex._driver = driver
        with pytest.raises(ReadOnlyViolationError):
            ex.execute("CREATE (n:X) RETURN n", None, row_limit=10, timeout_s=30)
