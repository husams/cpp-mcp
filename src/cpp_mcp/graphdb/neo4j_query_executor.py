"""Neo4j read-only query executor implementing the ADR-22 EXPLAIN-plan algorithm.

``neo4j`` is an optional dependency (``pip install cpp-mcp[graphdb-neo4j]``).
This module imports it lazily inside :meth:`Neo4jQueryExecutor.connect` so that
the rest of the server starts without it installed.

Read-only enforcement (ADR-22):
  1. ``EXPLAIN <query>`` is run first; ``ResultSummary.plan`` is walked recursively.
  2. Any operator whose name matches a write-side prefix raises
     :exc:`~cpp_mcp.core.error_envelope.ReadOnlyViolationError`.
  3. Any ``ProcedureCall`` whose procedure name (from ``arguments["Details"]`` or
     ``arguments["name"]``) is not in :data:`READ_ONLY_PROCEDURES` is rejected.
  4. On allowlist pass, the actual query runs with the same timeout.

Timing: ``QueryResult.ms`` reflects query-only duration (excludes EXPLAIN overhead).
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    QueryParseError,
    QueryTimeoutError,
    ReadOnlyViolationError,
)
from cpp_mcp.graphdb.query_executor import QueryResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Read-only enforcement constants (ADR-22)
# ---------------------------------------------------------------------------

WRITE_OPERATOR_PREFIXES: tuple[str, ...] = (
    "Create",
    "Merge",
    "Delete",
    "DetachDelete",
    "SetProperty",
    "SetLabels",
    "SetNodeProperty",
    "SetRelationshipProperty",
    "RemoveLabels",
    "RemoveProperty",
    "LoadCsv",
    "Foreach",
    "EmptyResult",
)

READ_ONLY_PROCEDURES: frozenset[str] = frozenset(
    {
        "db.labels",
        "db.relationshipTypes",
        "db.propertyKeys",
        "db.schema.visualization",
        "db.schema.nodeTypeProperties",
        "db.schema.relTypeProperties",
    }
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _walk_plan(plan: Any) -> None:
    """Recursively walk a Neo4j ``Plan`` tree; raise on write operators.

    Args:
        plan: A ``neo4j.Plan`` (or compatible mock) with ``operator_type``,
            ``arguments``, and ``children`` attributes.

    Raises:
        :exc:`~cpp_mcp.core.error_envelope.ReadOnlyViolationError`: when a
            write-side operator or a non-allowlisted procedure call is found.
    """
    op: str = plan.operator_type
    if any(op.startswith(p) for p in WRITE_OPERATOR_PREFIXES):
        raise ReadOnlyViolationError(
            f"Cypher operator {op!r} is not permitted in read-only queries (ADR-22)"
        )
    if op == "ProcedureCall":
        # Neo4j 5.x puts the procedure signature in "Details"; earlier builds
        # may use "name".  We parse the name from before the first "(" if
        # "Details" is present; fall back to "name" as a plain string.
        raw: str = plan.arguments.get("Details") or plan.arguments.get("name", "")
        # Strip args: "db.labels() :: (label :: STRING)" → "db.labels"
        proc_name = raw.split("(")[0].strip()
        if proc_name not in READ_ONLY_PROCEDURES:
            raise ReadOnlyViolationError(
                f"Procedure {proc_name!r} is not in the read-only allowlist (ADR-22)"
            )
    for child in plan.children:
        _walk_plan(child)


def _enforce_read_only(
    session: Any, query: str, parameters: dict[str, Any], timeout_s: int
) -> None:
    """Run ``EXPLAIN <query>`` and walk the returned plan; raise on writes.

    Args:
        session: An open Neo4j session.
        query: The Cypher query string to inspect.
        parameters: Bound parameters (forwarded to EXPLAIN so the planner sees them).
        timeout_s: Server-side timeout for the EXPLAIN call (seconds).

    Raises:
        :exc:`~cpp_mcp.core.error_envelope.QueryParseError`: on Cypher syntax errors.
        :exc:`~cpp_mcp.core.error_envelope.ReadOnlyViolationError`: on write operators.
        :exc:`~cpp_mcp.core.error_envelope.QueryTimeoutError`: if EXPLAIN times out.
    """
    import neo4j  # lazy — already imported in connect(); re-import is free (cached)
    import neo4j.exceptions as neo4j_exc

    explain_text: str = f"EXPLAIN {query}"
    explain_query = neo4j.Query(explain_text, timeout=float(timeout_s))
    try:
        result = session.run(explain_query, parameters or {})
        summary = result.consume()
    except neo4j_exc.CypherSyntaxError as exc:
        raise QueryParseError(f"Cypher syntax error: {exc}") from exc
    except neo4j_exc.ClientError as exc:
        # Neo.ClientError.Transaction.TransactionTimedOut
        if "TimedOut" in str(exc):
            raise QueryTimeoutError(f"EXPLAIN timed out after {timeout_s}s: {exc}") from exc
        raise QueryParseError(f"Cypher error during EXPLAIN: {exc}") from exc

    if summary.plan is None:
        # EXPLAIN always returns a plan; None means the driver could not produce
        # one — treat as a parse error (fail-closed).
        raise QueryParseError("EXPLAIN returned no plan (unexpected; query may be unparseable)")

    _walk_plan(summary.plan)


def _coerce_value(value: Any) -> Any:
    """Recursively coerce a Neo4j result value to a JSON-safe Python object.

    - :class:`neo4j.graph.Node` → ``{"_labels": [...], **props}``
    - :class:`neo4j.graph.Relationship` → ``{"_type": str, "_start": str, "_end": str, **props}``
    - :class:`neo4j.graph.Path` → ``{"_nodes": [...], "_rels": [...]}``
    - Scalars / lists / mappings → serialized via ``json.loads(json.dumps(v, default=str))``.
    """
    import neo4j.graph as neo4j_graph

    if isinstance(value, neo4j_graph.Node):
        coerced: dict[str, Any] = {"_labels": sorted(value.labels)}
        coerced.update({k: _coerce_value(v) for k, v in value.items()})
        return coerced
    if isinstance(value, neo4j_graph.Relationship):
        start_node = value.start_node
        end_node = value.end_node
        coerced = {
            "_type": value.type,
            "_start": start_node.element_id if start_node is not None else None,
            "_end": end_node.element_id if end_node is not None else None,
        }
        coerced.update({k: _coerce_value(v) for k, v in value.items()})
        return coerced
    if isinstance(value, neo4j_graph.Path):
        return {
            "_nodes": [_coerce_value(n) for n in value.nodes],
            "_rels": [_coerce_value(r) for r in value.relationships],
        }
    # Scalars, lists, and mappings — round-trip through JSON to enforce serializability.
    return json.loads(json.dumps(value, default=str))


def _coerce_record(record: Any) -> dict[str, Any]:
    """Convert a Neo4j ``Record`` to a plain ``dict`` with coerced values."""
    return {key: _coerce_value(record[key]) for key in record}


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class Neo4jQueryExecutor:
    """Neo4j read-only query executor (ADR-22).

    Enforces read-only access by running ``EXPLAIN <query>`` before the actual
    query and walking the returned plan tree.  Write-side operators raise
    :exc:`~cpp_mcp.core.error_envelope.ReadOnlyViolationError`.
    """

    backend: str = "neo4j"

    def __init__(self) -> None:
        self._driver: Any = None
        self._closed: bool = False

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open a Neo4j driver connection to *uri*.

        Args:
            uri: Bolt/Neo4j URI, e.g. ``"bolt://localhost:7687"``.
            **kwargs: Forwarded to ``neo4j.GraphDatabase.driver``.

        Raises:
            :exc:`DependencyMissingError`: when the ``neo4j`` package is not installed.
            :exc:`DBUnreachableError`: when the backend cannot be reached.
        """
        try:
            import neo4j  # lazy — optional dep
        except ImportError as exc:
            raise DependencyMissingError(
                "neo4j Python driver is not installed. "
                "Install with: uv sync --extra graphdb-neo4j  "
                'or: pip install "cpp-mcp[graphdb-neo4j]"'
            ) from exc

        try:
            self._driver = neo4j.GraphDatabase.driver(uri, **kwargs)
            self._driver.verify_connectivity()
            logger.debug("Neo4j (query) connected: %s", uri)
        except Exception as exc:
            raise DBUnreachableError(
                f"Cannot reach Neo4j at {uri!r}: {exc}"
            ) from exc

    def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None,
        row_limit: int,
        timeout_s: int,
    ) -> QueryResult:
        """Execute *query* read-only against Neo4j.

        Enforcement sequence (ADR-22):
        1. ``EXPLAIN <query>`` — parse check + plan walk.
        2. If plan passes, run the actual query with the same timeout.
        3. Consume at most ``row_limit`` rows; set ``truncated`` if more exist.

        Args:
            query: Cypher query string.
            parameters: Bound parameters forwarded to both EXPLAIN and actual run.
            row_limit: Maximum rows to return (already clamped to [1, 500] by caller).
            timeout_s: Server-side timeout in seconds applied to both EXPLAIN and query.

        Returns:
            :class:`~cpp_mcp.graphdb.query_executor.QueryResult`.

        Raises:
            :exc:`~cpp_mcp.core.error_envelope.ReadOnlyViolationError`: write operator detected.
            :exc:`~cpp_mcp.core.error_envelope.QueryParseError`: Cypher syntax error.
            :exc:`~cpp_mcp.core.error_envelope.QueryTimeoutError`: execution timed out.
            :exc:`~cpp_mcp.core.error_envelope.DBUnreachableError`: backend unreachable.
        """
        import neo4j  # already cached — free re-import
        import neo4j.exceptions as neo4j_exc

        if self._driver is None:
            raise DBUnreachableError("execute() called before connect()")

        params: dict[str, Any] = parameters or {}
        actual_query = neo4j.Query(query, timeout=float(timeout_s))

        with self._driver.session() as session:
            # Phase 1: EXPLAIN — read-only enforcement (ADR-22).
            _enforce_read_only(session, query, params, timeout_s)

            # Phase 2: Run the actual query and collect rows.
            t0 = time.monotonic()
            try:
                result = session.run(actual_query, params)
            except neo4j_exc.CypherSyntaxError as exc:
                raise QueryParseError(f"Cypher syntax error: {exc}") from exc
            except neo4j_exc.ClientError as exc:
                if "TimedOut" in str(exc):
                    raise QueryTimeoutError(
                        f"Query timed out after {timeout_s}s: {exc}"
                    ) from exc
                raise DBUnreachableError(f"Neo4j client error: {exc}") from exc
            except neo4j_exc.ServiceUnavailable as exc:
                raise DBUnreachableError(f"Neo4j service unavailable: {exc}") from exc

            rows: list[dict[str, Any]] = []
            truncated = False
            for i, record in enumerate(result):
                if i < row_limit:
                    rows.append(_coerce_record(record))
                else:
                    # There is at least one record beyond row_limit.
                    truncated = True
                    break

            elapsed_ms = int((time.monotonic() - t0) * 1000)

        return QueryResult(
            rows=rows,
            rows_returned=len(rows),
            truncated=truncated,
            ms=elapsed_ms,
        )

    def close(self) -> None:
        """Release driver resources.  Idempotent."""
        if self._closed:
            return
        try:
            if self._driver is not None:
                with contextlib.suppress(Exception):
                    self._driver.close()
        finally:
            self._driver = None
            self._closed = True
