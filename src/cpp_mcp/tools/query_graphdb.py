"""query_graphdb MCP tool implementation (v6 / ADR-23).

Validation order (design §5):
  1. INVALID_ARGUMENT  — empty/missing db_uri or query.
  2. INVALID_ARGUMENT  — unknown URI scheme (via select_executor).
  3. DEPENDENCY_MISSING — backend driver not importable (from connect()).
  4. DB_UNREACHABLE     — backend reachable check fails (from connect()).
  5. QUERY_PARSE_ERROR  — JSON parse failure (IndraDB) / Cypher syntax error (Neo4j).
  6. QUERY_UNSUPPORTED  — unknown verb (IndraDB) / disallowed operator (Neo4j).
  7. QUERY_TIMEOUT      — execution exceeds resolved timeout.
  8. Success → coerce rows → enforce row_limit → return.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import logging
import uuid
from typing import Annotated, Any

from fastmcp.dependencies import Depends

from cpp_mcp.core.deps import get_session
from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    InvalidArgumentError,
    QueryTimeoutError,
    wrap_tool,
)
from cpp_mcp.core.query_config import resolve_query_timeout_s
from cpp_mcp.graphdb.query_executor import select_executor

logger = logging.getLogger(__name__)

_TOOL_NAME = "query_graphdb"
_ROW_LIMIT_DEFAULT = 200
_ROW_LIMIT_MAX = 500
_ROW_LIMIT_MIN = 1


def _do_query_graphdb(
    *,
    db_uri: str,
    query: str,
    parameters: dict[str, Any] | None,
    row_limit: int,
    request_id: str,
) -> dict[str, Any]:
    """Blocking query execution — runs on the shared worker thread.

    Args:
        db_uri: Backend URI (bolt:// or indradb://).
        query: Cypher string (Neo4j) or IndraDB JSON shape (IndraDB).
        parameters: Bound parameters (Cypher only; ignored for IndraDB).
        row_limit: Maximum rows (already clamped to [1, 500]).
        request_id: UUID hex for log correlation.

    Returns:
        Success payload: ``{rows, stats, request_id}``.

    Raises:
        :exc:`InvalidArgumentError`: on empty inputs or unknown URI scheme.
        :exc:`DependencyMissingError`: if the backend driver is not installed.
        :exc:`DBUnreachableError`: if the backend is unreachable.
        :exc:`QueryParseError`: on invalid query syntax.
        :exc:`QueryUnsupportedError`: on disallowed query verb/operator.
        :exc:`QueryTimeoutError`: on execution timeout.
    """
    # Step 1 — empty db_uri / query already validated by caller.
    # Step 2 — unknown scheme: select_executor raises InvalidArgumentError.
    executor = select_executor(db_uri)

    timeout_s = resolve_query_timeout_s()

    # Step 3/4 — DEPENDENCY_MISSING / DB_UNREACHABLE.
    try:
        executor.connect(db_uri)
    except (DependencyMissingError, DBUnreachableError):
        raise
    except Exception as exc:
        raise DBUnreachableError(
            f"Cannot reach graph database at {db_uri!r}: {exc}"
        ) from exc

    try:
        result = executor.execute(
            query=query,
            parameters=parameters,
            row_limit=row_limit,
            timeout_s=timeout_s,
        )
    finally:
        with contextlib.suppress(Exception):
            executor.close()

    return {
        "rows": result["rows"],
        "stats": {
            "backend": executor.backend,
            "ms": result["ms"],
            "rows_returned": result["rows_returned"],
            "truncated": result["truncated"],
        },
        "request_id": request_id,
    }


def _register(mcp: Any) -> None:
    """Register query_graphdb against *mcp*.  Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="query_graphdb",
        description=(
            "Execute a read-only graph query against a Neo4j or IndraDB backend. "
            "Neo4j: supply a Cypher SELECT query. "
            "IndraDB: supply a JSON object per the ADR-23 query schema "
            '(e.g. {"query":"all_vertices","args":{}}).'
        ),
    )
    @wrap_tool(_TOOL_NAME)
    def query_graphdb_tool(
        db_uri: Annotated[
            str,
            "Backend URI: bolt://... (Neo4j) or indradb://... (IndraDB).",
        ],
        query: Annotated[
            str,
            "Cypher string (Neo4j) or IndraDB JSON query shape (IndraDB).",
        ],
        parameters: Annotated[
            dict[str, Any] | None,
            "Bound parameters for Cypher queries (Neo4j only). Ignored for IndraDB.",
        ] = None,
        row_limit: Annotated[
            int,
            "Maximum rows returned. Clamped to [1, 500]; default 200.",
        ] = _ROW_LIMIT_DEFAULT,
        *,
        session: Any = Depends(get_session),
    ) -> dict[str, Any]:
        # Step 1 — validate empty inputs before dispatch.
        if not db_uri:
            raise InvalidArgumentError(
                "db_uri is required and must be a non-empty string for query_graphdb."
            )
        if not query:
            raise InvalidArgumentError(
                "query is required and must be a non-empty string for query_graphdb."
            )

        # Clamp row_limit.
        clamped = max(_ROW_LIMIT_MIN, min(_ROW_LIMIT_MAX, row_limit))

        request_id = uuid.uuid4().hex
        timeout_s = resolve_query_timeout_s()

        try:
            return session.executor.submit(  # type: ignore[no-any-return]
                _do_query_graphdb,
                db_uri=db_uri,
                query=query,
                parameters=parameters,
                row_limit=clamped,
                request_id=request_id,
            ).result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise QueryTimeoutError(
                f"query_graphdb timed out after {timeout_s}s"
            ) from exc
