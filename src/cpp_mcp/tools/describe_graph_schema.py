"""describe_graph_schema MCP tool implementation.

Discovers node/edge types, counts, and property keys live from the graph
database (ADR-24 — no caching; every call is fresh).

Validation order (mirrors ingest_code / query_graphdb):
  1. INVALID_ARGUMENT  — empty/missing db_uri.
  2. INVALID_ARGUMENT  — unknown URI scheme (select_introspector).
  3. DEPENDENCY_MISSING — backend package not importable (introspector.connect).
  4. DB_UNREACHABLE    — backend unreachable (introspector.connect).
  5. QUERY_TIMEOUT     — introspector.describe exceeds resolved timeout.
  6. Success           — return schema dict.

AC-Q2-6: the result dict MUST NOT contain the db_uri string.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import logging
import uuid
from typing import Annotated, Any

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    InvalidArgumentError,
    QueryTimeoutError,
    wrap_tool,
)
from cpp_mcp.graphdb.schema_introspector import select_introspector

logger = logging.getLogger(__name__)

_TOOL_NAME = "describe_graph_schema"
_SAMPLE_MIN = 10
_SAMPLE_MAX = 1000
_SAMPLE_DEFAULT = 100


def _resolve_timeout_s() -> int:
    """Resolve the query timeout from the environment (mirrors query_config logic)."""
    import os

    raw = os.environ.get("CPP_MCP_QUERY_TIMEOUT_SECONDS", "30")
    try:
        v = int(raw)
    except ValueError:
        v = 30
    return max(1, min(120, v))


def describe_graph_schema(
    *,
    db_uri: str,
    sample_size: int = _SAMPLE_DEFAULT,
    request_id: str,
) -> dict[str, Any]:
    """Core describe logic — callable directly in unit tests.

    Args:
        db_uri: Backend URI (``bolt://...`` or ``indradb://...``).
        sample_size: Per-type vertex sample for property-key inference;
            clamped to ``[10, 1000]``.
        request_id: UUID4 hex string for log correlation.

    Returns:
        Success payload: ``{schema_version, backend, node_types, edge_types,
        totals, notes, request_id}``.

    Raises:
        :exc:`InvalidArgumentError`: empty ``db_uri`` or unknown scheme.
        :exc:`DependencyMissingError`: backend package missing.
        :exc:`DBUnreachableError`: backend unreachable.
        :exc:`QueryTimeoutError`: introspection exceeds timeout.
    """
    # 1. Validate db_uri.
    if not db_uri:
        raise InvalidArgumentError("db_uri is required and must be a non-empty string.")

    # 2. scheme dispatch (raises InvalidArgumentError on unknown scheme).
    introspector = select_introspector(db_uri)

    # Clamp sample_size.
    clamped_sample = max(_SAMPLE_MIN, min(_SAMPLE_MAX, sample_size))

    # 3+4. Connect (raises DependencyMissingError / DBUnreachableError).
    try:
        introspector.connect(db_uri)
    except (DependencyMissingError, DBUnreachableError):
        raise
    except Exception as exc:
        raise DBUnreachableError(
            f"Cannot reach graph database at {db_uri!r}: {exc}"
        ) from exc

    timeout_s = _resolve_timeout_s()

    # 5. Run describe with timeout.
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(introspector.describe, clamped_sample)
            try:
                result = future.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError as exc:
                raise QueryTimeoutError(
                    f"describe_graph_schema timed out after {timeout_s}s"
                ) from exc
    finally:
        with contextlib.suppress(Exception):
            introspector.close()

    # AC-Q2-6: never echo db_uri in result.
    result["request_id"] = request_id
    return result


def _register(mcp: Any) -> None:
    """Register describe_graph_schema against *mcp*. Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name=_TOOL_NAME,
        description=(
            "Discover node/edge types, counts, and property keys live from the graph database. "
            "Returns schema_version, backend, node_types (sorted by count desc), "
            "edge_types, totals, and notes (including schema-version skew warnings). "
            "No caching — every call is fresh. "
            "Requires an IndraDB or Neo4j URI populated by ingest_code."
        ),
    )
    @wrap_tool(_TOOL_NAME)
    def describe_graph_schema_tool(
        db_uri: Annotated[
            str,
            "Backend URI (e.g. 'indradb://localhost:27615' or 'bolt://localhost:7687').",
        ],
        sample_size: Annotated[
            int,
            "Per-type vertex sample for property key inference; clamped to [10, 1000].",
        ] = _SAMPLE_DEFAULT,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        return describe_graph_schema(
            db_uri=db_uri,
            sample_size=sample_size,
            request_id=request_id,
        )
