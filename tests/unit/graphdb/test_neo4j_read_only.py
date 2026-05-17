"""Unit tests for ADR-22 EXPLAIN-plan read-only enforcement.

Tests fabricated ``ResultSummary.plan`` trees to verify the allow/reject
matrix without a live Neo4j instance.  The ``_walk_plan`` and
``_enforce_read_only`` internals are tested directly; ``execute`` is tested
end-to-end in ``test_neo4j_query_executor.py``.

Allow-set (AC-Q1-3):
  MATCH, OPTIONAL MATCH, WITH, RETURN, WHERE, UNWIND, ORDER BY, SKIP, LIMIT,
  read-only CALL { MATCH ... } subqueries, db.labels / db.relationshipTypes procs.

Reject-set (AC-Q1-3):
  CREATE, MERGE, DELETE, DetachDelete, SET, REMOVE, DROP, LOAD CSV,
  any CALL <proc> outside the read-only allowlist (e.g. apoc.create.node),
  CALL { CREATE ... } nested write, unknown write-prefix operator.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.core.error_envelope import (
    QueryParseError,
    QueryTimeoutError,
    ReadOnlyViolationError,
)
from cpp_mcp.graphdb.neo4j_query_executor import _enforce_read_only, _walk_plan

# ---------------------------------------------------------------------------
# Plan-tree fabrication helpers
# ---------------------------------------------------------------------------


def _plan(
    operator_type: str,
    arguments: dict[str, Any] | None = None,
    children: list[Any] | None = None,
) -> MagicMock:
    """Return a fake Plan node matching the neo4j Plan duck type."""
    p = MagicMock()
    p.operator_type = operator_type
    p.arguments = arguments or {}
    p.children = children or []
    return p


# ---------------------------------------------------------------------------
# _walk_plan allow-set tests
# ---------------------------------------------------------------------------


class TestWalkPlanAllowed:
    """Operators that must NOT raise ReadOnlyViolationError."""

    @pytest.mark.parametrize(
        "operator_type",
        [
            "AllNodesScan",
            "NodeByLabelScan",
            "IndexSeek",
            "Expand",
            "Filter",
            "Projection",
            "Argument",
            "Apply",
            "Optional",
            "Distinct",
            "Sort",
            "Skip",
            "Limit",
            "Unwind",
            "EagerAggregation",
            "ProduceResults",
            "CartesianProduct",
        ],
    )
    def test_read_only_operators_pass(self, operator_type: str) -> None:
        _walk_plan(_plan(operator_type))  # must not raise

    def test_nested_call_subquery_all_read(self) -> None:
        """CALL { MATCH (n) RETURN n } — inner body compiles to read operators."""
        inner = _plan("AllNodesScan")
        outer = _plan("Apply", children=[inner])
        _walk_plan(outer)  # must not raise

    def test_procedure_call_db_labels(self) -> None:
        """CALL db.labels() — in allowlist."""
        p = _plan("ProcedureCall", arguments={"Details": "db.labels() :: (label :: STRING)"})
        _walk_plan(p)  # must not raise

    def test_procedure_call_db_relationship_types(self) -> None:
        details = "db.relationshipTypes() :: (relationshipType :: STRING)"
        p = _plan("ProcedureCall", arguments={"Details": details})
        _walk_plan(p)

    def test_procedure_call_db_property_keys(self) -> None:
        details = "db.propertyKeys() :: (propertyKey :: STRING)"
        p = _plan("ProcedureCall", arguments={"Details": details})
        _walk_plan(p)

    def test_procedure_call_db_schema_visualization(self) -> None:
        details = "db.schema.visualization() :: (nodes :: LIST, relationships :: LIST)"
        p = _plan("ProcedureCall", arguments={"Details": details})
        _walk_plan(p)

    def test_procedure_call_name_key_fallback(self) -> None:
        """Some driver versions use 'name' instead of 'Details'."""
        p = _plan("ProcedureCall", arguments={"name": "db.labels"})
        _walk_plan(p)

    def test_unknown_operator_not_in_write_prefix_passes(self) -> None:
        """An operator not matching any write prefix should pass (fail-closed only for writes)."""
        p = _plan("FuturePlannerOperatorXYZ")
        _walk_plan(p)  # must not raise

    def test_deeply_nested_all_read(self) -> None:
        """Multiple levels of nesting — all read-only operators."""
        plan = _plan(
            "ProduceResults",
            children=[
                _plan(
                    "Sort",
                    children=[
                        _plan(
                            "Apply",
                            children=[
                                _plan("NodeByLabelScan"),
                                _plan("Filter"),
                            ],
                        )
                    ],
                )
            ],
        )
        _walk_plan(plan)  # must not raise


# ---------------------------------------------------------------------------
# _walk_plan reject-set tests
# ---------------------------------------------------------------------------


class TestWalkPlanRejected:
    """Operators that MUST raise ReadOnlyViolationError."""

    @pytest.mark.parametrize(
        "operator_type",
        [
            "CreateNode",
            "CreateRelationship",
            "MergeCreateNode",
            "MergeCreateRelationship",
            "DeleteNode",
            "DeleteRelationship",
            "DetachDeleteNode",
            "SetProperty",
            "SetLabels",
            "SetNodeProperty",
            "SetRelationshipProperty",
            "RemoveLabels",
            "RemoveProperty",
            "LoadCsv",
            "Foreach",
            "EmptyResult",
        ],
    )
    def test_write_operator_raises(self, operator_type: str) -> None:
        with pytest.raises(ReadOnlyViolationError, match="not permitted"):
            _walk_plan(_plan(operator_type))

    def test_nested_call_create_rejected(self) -> None:
        """CALL { CREATE (n:X) RETURN n } — inner write is still rejected."""
        inner = _plan("CreateNode")
        outer = _plan("Apply", children=[inner])
        with pytest.raises(ReadOnlyViolationError):
            _walk_plan(outer)

    def test_procedure_call_apoc_create_node_rejected(self) -> None:
        details = "apoc.create.node(labels :: LIST, props :: MAP) :: NODE"
        p = _plan("ProcedureCall", arguments={"Details": details})
        with pytest.raises(ReadOnlyViolationError, match="not in the read-only allowlist"):
            _walk_plan(p)

    def test_procedure_call_unknown_proc_rejected(self) -> None:
        p = _plan("ProcedureCall", arguments={"Details": "custom.proc() :: (x :: STRING)"})
        with pytest.raises(ReadOnlyViolationError):
            _walk_plan(p)

    def test_procedure_call_empty_name_rejected(self) -> None:
        """A ProcedureCall with no name / empty Details is also rejected (fail-closed)."""
        p = _plan("ProcedureCall", arguments={})
        with pytest.raises(ReadOnlyViolationError):
            _walk_plan(p)

    def test_write_operator_buried_in_read_tree(self) -> None:
        """A single write operator deep in the tree should be caught."""
        plan = _plan(
            "ProduceResults",
            children=[
                _plan(
                    "Sort",
                    children=[
                        _plan(
                            "Apply",
                            children=[
                                _plan("NodeByLabelScan"),
                                _plan("CreateNode"),  # buried write
                            ],
                        )
                    ],
                )
            ],
        )
        with pytest.raises(ReadOnlyViolationError):
            _walk_plan(plan)


# ---------------------------------------------------------------------------
# _enforce_read_only integration tests (mocked session)
# ---------------------------------------------------------------------------


def _make_session(
    plan: Any = None,
    syntax_error: Exception | None = None,
    client_error: Exception | None = None,
) -> MagicMock:
    """Build a mock neo4j session whose .run() returns a fabricated summary."""
    session = MagicMock()
    result_mock = MagicMock()

    if syntax_error is not None:
        session.run.side_effect = syntax_error
    elif client_error is not None:
        session.run.side_effect = client_error
    else:
        summary_mock = MagicMock()
        summary_mock.plan = plan
        result_mock.consume.return_value = summary_mock
        session.run.return_value = result_mock

    return session


class TestEnforceReadOnly:
    """_enforce_read_only with mocked session."""

    def test_all_nodes_scan_passes(self) -> None:
        session = _make_session(plan=_plan("AllNodesScan"))
        _enforce_read_only(session, "MATCH (n) RETURN n", {}, 30)  # no raise

    def test_create_node_raises_read_only_violation(self) -> None:
        session = _make_session(plan=_plan("CreateNode"))
        with pytest.raises(ReadOnlyViolationError):
            _enforce_read_only(session, "CREATE (n:X) RETURN n", {}, 30)

    def test_cypher_syntax_error_raises_query_parse_error(self) -> None:
        import neo4j.exceptions as neo4j_exc

        err = neo4j_exc.CypherSyntaxError(
            "bad syntax", "Neo.ClientError.Statement.SyntaxError", "msg"
        )
        session = _make_session(syntax_error=err)
        with pytest.raises(QueryParseError, match="syntax"):
            _enforce_read_only(session, "NOT VALID CYPHER ##", {}, 30)

    def test_timed_out_client_error_raises_query_timeout(self) -> None:
        import neo4j.exceptions as neo4j_exc

        err = neo4j_exc.ClientError(
            "TimedOut error",
            "Neo.ClientError.Transaction.TransactionTimedOut",
            "Transaction timed out",
        )
        session = _make_session(client_error=err)
        with pytest.raises(QueryTimeoutError, match="timed out"):
            _enforce_read_only(session, "MATCH (n) RETURN n", {}, 1)

    def test_none_plan_raises_query_parse_error(self) -> None:
        session = _make_session(plan=None)
        with pytest.raises(QueryParseError, match="no plan"):
            _enforce_read_only(session, "MATCH (n) RETURN n", {}, 30)
