"""QueryExecutor Protocol and scheme dispatch for read-only graph queries.

Mirrors the ``select_driver`` dispatch in ``graphdb/__init__.py`` but for the
read-only query surface (design §3.1).  No I/O or lazy imports occur at module
load time; backend modules are imported inside each executor's ``connect()``.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict
from urllib.parse import urlparse

from cpp_mcp.core.error_envelope import InvalidArgumentError

# Reuse the same scheme frozensets as the write-path drivers (graphdb/__init__.py).
_NEO4J_SCHEMES: frozenset[str] = frozenset(
    {"bolt", "bolt+s", "bolt+ssc", "neo4j", "neo4j+s", "neo4j+ssc"}
)
_INDRADB_SCHEMES: frozenset[str] = frozenset({"indradb", "grpc", "indradb+grpc"})


class QueryResult(TypedDict):
    """Result returned by :meth:`QueryExecutor.execute`."""

    rows: list[dict[str, Any]]
    rows_returned: int
    truncated: bool
    ms: int


class QueryExecutor(Protocol):
    """Structural Protocol for read-only graph query backends (design §3.1)."""

    backend: str  # "neo4j" | "indradb"

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open a connection to *uri*.

        Raises:
            :exc:`~cpp_mcp.core.error_envelope.DependencyMissingError`: if the
                backend driver package is not installed.
            :exc:`~cpp_mcp.core.error_envelope.DBUnreachableError`: if the
                backend cannot be reached.
        """
        ...

    def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None,
        row_limit: int,
        timeout_s: int,
    ) -> QueryResult:
        """Execute *query* and return at most *row_limit* rows.

        Args:
            query: Cypher string (Neo4j) or IndraDB JSON shape (IndraDB).
            parameters: Bound parameters (Cypher only; ignored by IndraDB executor).
            row_limit: Maximum rows to return (already clamped to [1, 500] by caller).
            timeout_s: Execution timeout in seconds.

        Returns:
            :class:`QueryResult` with rows, counts, and timing.

        Raises:
            :exc:`~cpp_mcp.core.error_envelope.ReadOnlyViolationError`: on write
                operation detected (Neo4j path).
            :exc:`~cpp_mcp.core.error_envelope.QueryParseError`: on invalid
                JSON/Cypher syntax.
            :exc:`~cpp_mcp.core.error_envelope.QueryUnsupportedError`: on unknown
                verb (IndraDB) or disallowed operator (Neo4j).
            :exc:`~cpp_mcp.core.error_envelope.QueryTimeoutError`: on timeout.
        """
        ...

    def close(self) -> None:
        """Release resources.  Idempotent."""
        ...


def select_executor(db_uri: str) -> QueryExecutor:
    """Return an *unconnected* :class:`QueryExecutor` instance for *db_uri*'s scheme.

    Pure scheme dispatch — no I/O, no lazy imports at call time.  Lazy imports
    happen inside each executor's ``connect()`` method.

    Args:
        db_uri: Backend URI including scheme, e.g. ``"bolt://localhost:7687"``
            or ``"indradb://localhost:27615"``.

    Returns:
        An unconnected :class:`QueryExecutor` appropriate for the URI scheme.

    Raises:
        :exc:`~cpp_mcp.core.error_envelope.InvalidArgumentError`: if *db_uri*
            is empty, missing ``://``, or has an unrecognised scheme.
    """
    if not db_uri or "://" not in db_uri:
        raise InvalidArgumentError(
            f"db_uri must include a scheme (got {db_uri!r}); "
            f"supported: {sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
        )
    scheme = urlparse(db_uri).scheme
    if scheme in _NEO4J_SCHEMES:
        from cpp_mcp.graphdb.neo4j_query_executor import Neo4jQueryExecutor

        return Neo4jQueryExecutor()
    if scheme in _INDRADB_SCHEMES:
        from cpp_mcp.graphdb.indradb_query_executor import IndraDbQueryExecutor

        return IndraDbQueryExecutor()
    raise InvalidArgumentError(
        f"Unsupported db_uri scheme {scheme!r}; "
        f"supported: {sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
    )
