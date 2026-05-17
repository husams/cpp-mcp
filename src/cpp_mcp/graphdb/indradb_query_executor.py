"""IndraDB read-only query executor implementing the ADR-23 JSON query subset.

``indradb`` is an optional dependency (``pip install cpp-mcp[graphdb-indradb]``).
This module imports it lazily inside :meth:`IndraDbQueryExecutor.connect` so that
the rest of the server starts without it installed.

Read-only purity guarantee (AC-Q1-4):
  This module imports ONLY ``Client.get``, ``get_properties``, and the seven
  ``*Query`` constructors listed in ADR-23.  No ``set_*`` or ``delete_*`` symbols
  are imported or re-exported.  This is verified by ``test_query_executor_purity.py``.

Assumed ``get_properties`` shape (to be confirmed against live daemon in S5):
  Returns batches of property objects with ``.name`` and ``.value`` attributes,
  identical to the streaming shape returned by ``get()``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
import uuid
from typing import Any

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    QueryParseError,
    QueryUnsupportedError,
)
from cpp_mcp.graphdb.query_executor import QueryResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADR-23 verb allowlist
# ---------------------------------------------------------------------------

_ALLOWED_VERBS: frozenset[str] = frozenset(
    {
        "all_vertices",
        "all_edges",
        "vertex_with_type",
        "edge_with_type",
        "vertex_with_property_equal",
        "edge_with_property_equal",
        "pipe",
    }
)

# Type identifier pattern (mirrors IndraDB upstream rule).
_TYPE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# JSON scalar types per ADR-23 §validation rule 6.
_JSON_SCALAR = (str, int, float, bool, type(None))


def _validate_t(t: Any) -> str:
    """Validate a type identifier string per ADR-23 §rule 4.

    Raises:
        :exc:`QueryParseError`: if *t* is not a string matching ``^[A-Za-z_][A-Za-z0-9_]*$``.
    """
    if not isinstance(t, str) or not _TYPE_IDENT_RE.match(t):
        raise QueryParseError(f"Invalid type identifier {t!r}; must match ^[A-Za-z_][A-Za-z0-9_]*$")
    return t


def _validate_uuid(vertex_id: Any) -> uuid.UUID:
    """Validate *vertex_id* as a UUID string per ADR-23 §rule 5.

    Raises:
        :exc:`QueryParseError`: if *vertex_id* is not a valid UUID string.
    """
    if not isinstance(vertex_id, str):
        raise QueryParseError(f"vertex_id must be a string UUID, got {type(vertex_id).__name__}")
    try:
        return uuid.UUID(vertex_id)
    except ValueError as exc:
        raise QueryParseError(f"vertex_id {vertex_id!r} is not a valid UUID: {exc}") from exc


def _validate_scalar(value: Any) -> Any:
    """Validate *value* is a JSON scalar per ADR-23 §rule 6.

    Raises:
        :exc:`QueryParseError`: if *value* is not a JSON scalar.
    """
    if not isinstance(value, _JSON_SCALAR):
        raise QueryParseError(
            f"value must be a JSON scalar (str/int/float/bool/null), got {type(value).__name__}"
        )
    return value


def _require_args(
    args: dict[str, Any], required: set[str], optional: set[str] | None = None
) -> None:
    """Check that *args* contains exactly *required* keys (plus optional *optional* keys).

    Raises:
        :exc:`QueryParseError`: on missing or extra keys.
    """
    allowed = required | (optional or set())
    missing = required - set(args)
    extra = set(args) - allowed
    if missing:
        raise QueryParseError(f"Missing required args: {sorted(missing)}")
    if extra:
        raise QueryParseError(f"Unexpected args: {sorted(extra)}")


# ---------------------------------------------------------------------------
# Result coercion helpers (design §6.1)
# ---------------------------------------------------------------------------


def _coerce_vertex(vertex: Any, props: dict[str, Any]) -> dict[str, Any]:
    """Coerce an IndraDB Vertex to the wire row shape."""
    return {"id": str(vertex.id), "t": str(vertex.t), "properties": props}


def _coerce_edge(edge: Any, props: dict[str, Any]) -> dict[str, Any]:
    """Coerce an IndraDB Edge to the wire row shape."""
    return {
        "outbound_id": str(edge.outbound_id),
        "inbound_id": str(edge.inbound_id),
        "t": str(edge.t),
        "properties": props,
    }


def _fetch_vertex_props(client: Any, query: Any, items: list[Any]) -> list[dict[str, Any]]:
    """Fetch properties for *items* in one batched ``client.get(query.properties())`` call.

    Returns a list of property dicts, one per item in *items*.  Uses a single
    ``client.get(query.properties())`` call to avoid N+1 round-trips (design §6.1).

    S5 confirmed: ``client.get(query.properties())`` yields batches of
    ``VertexProperties`` objects, each with:
      - ``.vertex``: the ``Vertex`` object (has ``.id``)
      - ``.props``: list of ``NamedProperty`` (each has ``.name`` / ``.value``)
    """
    by_id: dict[str, dict[str, Any]] = {}
    for batch in client.get(query.properties()):
        for vp in batch:  # vp: VertexProperties
            vid = str(vp.vertex.id)
            for np in vp.props:  # np: NamedProperty
                by_id.setdefault(vid, {})[np.name] = np.value
    return [by_id.get(str(item.id), {}) for item in items]


def _fetch_edge_props(client: Any, query: Any, items: list[Any]) -> list[dict[str, Any]]:
    """Fetch properties for edge *items* in one batched ``client.get(query.properties())`` call.

    S5 confirmed: ``client.get(query.properties())`` yields batches of
    ``EdgeProperties`` objects, each with:
      - ``.edge``: the ``Edge`` object (has ``.outbound_id``, ``.inbound_id``, ``.t``)
      - ``.props``: list of ``NamedProperty`` (each has ``.name`` / ``.value``)
    """
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for batch in client.get(query.properties()):
        for ep in batch:  # ep: EdgeProperties
            edge = ep.edge
            oid = str(getattr(edge, "outbound_id", ""))
            iid = str(getattr(edge, "inbound_id", ""))
            t = str(getattr(edge, "t", ""))
            if oid and iid and t:
                for np in ep.props:  # np: NamedProperty
                    by_key.setdefault((oid, t, iid), {})[np.name] = np.value
    return [by_key.get((str(e.outbound_id), str(e.t), str(e.inbound_id)), {}) for e in items]


def _flatten_results(batches: Any) -> list[Any]:
    """Flatten a batch-streaming result from ``client.get()`` to a flat list."""
    return [item for batch in batches for item in batch]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class IndraDbQueryExecutor:
    """IndraDB read-only query executor implementing the ADR-23 JSON subset.

    Satisfies the :class:`~cpp_mcp.graphdb.query_executor.QueryExecutor` Protocol.
    """

    backend: str = "indradb"

    def __init__(self) -> None:
        self._client: Any = None
        self._closed: bool = False

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open an IndraDB gRPC connection to *uri*.

        Lazily imports ``indradb`` so the rest of the server starts without it
        installed.

        Args:
            uri: IndraDB URI, e.g. ``"indradb://localhost:27615"``.
            **kwargs: Forwarded to ``indradb.Client``.

        Raises:
            :exc:`DependencyMissingError`: when ``indradb`` is not installed.
            :exc:`DBUnreachableError`: when the backend cannot be reached.
        """
        try:
            import indradb  # type: ignore[import-untyped]  # lazy — optional dep; no stubs
        except ImportError as exc:
            raise DependencyMissingError(
                "indradb Python driver is not installed. "
                "Install with: uv sync --extra graphdb-indradb  "
                'or: pip install "cpp-mcp[graphdb-indradb]"'
            ) from exc

        from urllib.parse import urlparse

        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 27615
        host_port = f"{host}:{port}"

        try:
            self._client = indradb.Client(host=host_port, **kwargs)
            self._client.ping()
            logger.debug("IndraDB (query) connected: %s", uri)
        except Exception as exc:
            raise DBUnreachableError(f"Cannot reach IndraDB at {uri!r}: {exc}") from exc

    def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None,
        row_limit: int,
        timeout_s: int,
    ) -> QueryResult:
        """Execute an ADR-23 JSON query and return at most *row_limit* rows.

        Args:
            query: IndraDB JSON query shape (``{"query": "<verb>", "args": {...}}``).
                If *query* is not valid JSON, raises :exc:`QueryParseError`.
                If *query* is valid JSON but the verb is not in the allowlist,
                raises :exc:`QueryUnsupportedError`.
            parameters: Ignored for IndraDB (Cypher-only concept).
            row_limit: Maximum rows to return (already clamped by caller).
            timeout_s: Unused here — the caller (tool entry) wraps the submit
                with ``concurrent.futures`` timeout; kept for Protocol conformance.

        Returns:
            :class:`~cpp_mcp.graphdb.query_executor.QueryResult` with rows,
            counts, and timing (ms).

        Raises:
            :exc:`QueryParseError`: on JSON parse failure or invalid args.
            :exc:`QueryUnsupportedError`: on unknown verb.
        """
        start = time.monotonic()
        rows = self._dispatch_query(query, row_limit)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        truncated = len(rows) < self._last_total
        return QueryResult(
            rows=rows,
            rows_returned=len(rows),
            truncated=truncated,
            ms=elapsed_ms,
        )

    # We track the pre-truncation total to fill the ``truncated`` flag.
    _last_total: int = 0

    def _dispatch_query(self, query_str: str, row_limit: int) -> list[dict[str, Any]]:
        """Parse the JSON query shape and dispatch to the appropriate IndraDB query."""
        # ADR-23 rule 1: must parse as JSON object.
        try:
            payload = json.loads(query_str)
        except (json.JSONDecodeError, ValueError) as exc:
            raise QueryParseError(
                f"query must be a valid JSON object (IndraDB endpoint); parse error: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise QueryParseError(
                "query must be a JSON object with 'query' and 'args' keys, "
                f"got {type(payload).__name__}"
            )

        verb = payload.get("query")
        args = payload.get("args", {})

        if not isinstance(args, dict):
            raise QueryParseError(f"'args' must be a JSON object, got {type(args).__name__}")

        # ADR-23 rule 2: verb must be in allowlist.
        if verb not in _ALLOWED_VERBS:
            raise QueryUnsupportedError(
                f"Unsupported query verb {verb!r}; allowed: {sorted(_ALLOWED_VERBS)}"
            )

        assert isinstance(verb, str)

        # Dispatch to per-verb builder.
        import indradb  # safe: already in sys.modules after connect()

        client = self._client

        if verb == "all_vertices":
            _require_args(args, set())
            raw = _flatten_results(client.get(indradb.AllVertexQuery()))
            self._last_total = len(raw)
            items = raw[:row_limit]
            props_list = _fetch_vertex_props(client, indradb.AllVertexQuery(), items)
            return [_coerce_vertex(v, p) for v, p in zip(items, props_list, strict=True)]

        if verb == "all_edges":
            _require_args(args, set())
            raw = _flatten_results(client.get(indradb.AllEdgeQuery()))
            self._last_total = len(raw)
            items = raw[:row_limit]
            props_list = _fetch_edge_props(client, indradb.AllEdgeQuery(), items)
            return [_coerce_edge(e, p) for e, p in zip(items, props_list, strict=True)]

        if verb == "vertex_with_type":
            # indradb client has no VertexWithTypeQuery; filter client-side (S5).
            _require_args(args, {"t"})
            t = _validate_t(args["t"])
            all_raw = _flatten_results(client.get(indradb.AllVertexQuery()))
            raw = [v for v in all_raw if str(v.t) == t]
            self._last_total = len(raw)
            items = raw[:row_limit]
            if not items:
                return []
            sq = indradb.SpecificVertexQuery(*[v.id for v in items])
            props_list = _fetch_vertex_props(client, sq, items)
            return [_coerce_vertex(v, p) for v, p in zip(items, props_list, strict=True)]

        if verb == "edge_with_type":
            # indradb client has no EdgeWithTypeQuery; filter client-side (S5).
            _require_args(args, {"t"})
            t = _validate_t(args["t"])
            all_raw = _flatten_results(client.get(indradb.AllEdgeQuery()))
            raw = [e for e in all_raw if str(e.t) == t]
            self._last_total = len(raw)
            items = raw[:row_limit]
            if not items:
                return []
            sq = indradb.SpecificEdgeQuery(*items)
            props_list = _fetch_edge_props(client, sq, items)
            return [_coerce_edge(e, p) for e, p in zip(items, props_list, strict=True)]

        if verb == "vertex_with_property_equal":
            # indradb.VertexWithPropertyValueQuery has a library bug: __init__ uses
            # parameter names '_name'/'_value' but the body assigns 'name'/'value'
            # (without underscore), causing NameError on every call.  Work around by
            # fetching all vertices + their properties and filtering client-side,
            # identical to the vertex_with_type approach (S5).
            _require_args(args, {"name", "value"})
            if not isinstance(args["name"], str):
                raise QueryParseError(f"'name' must be a string, got {type(args['name']).__name__}")
            _validate_scalar(args["value"])
            prop_name: str = args["name"]
            prop_value: Any = args["value"]
            all_raw_v = _flatten_results(client.get(indradb.AllVertexQuery()))
            # Fetch properties for all vertices to filter by name+value.
            all_props: dict[str, dict[str, Any]] = {}
            for batch in client.get(indradb.AllVertexQuery().properties()):
                for vp in batch:
                    vid_str = str(vp.vertex.id)
                    for np in vp.props:
                        all_props.setdefault(vid_str, {})[np.name] = np.value
            raw = [
                v for v in all_raw_v if all_props.get(str(v.id), {}).get(prop_name) == prop_value
            ]
            self._last_total = len(raw)
            items = raw[:row_limit]
            # Build per-item props from the already-fetched map.
            props_list = [all_props.get(str(v.id), {}) for v in items]
            return [_coerce_vertex(v, p) for v, p in zip(items, props_list, strict=True)]

        if verb == "edge_with_property_equal":
            # indradb.EdgeWithPropertyValueQuery.to_message() passes json.dumps(value)
            # as a plain str to proto.EdgeWithPropertyValueQuery(value=...) which
            # expects a proto.Json message, causing MergeFrom TypeError.  Work around
            # by fetching all edges + their properties and filtering client-side.
            _require_args(args, {"name", "value"})
            if not isinstance(args["name"], str):
                raise QueryParseError(f"'name' must be a string, got {type(args['name']).__name__}")
            _validate_scalar(args["value"])
            edge_prop_name: str = args["name"]
            edge_prop_value: Any = args["value"]
            all_raw_e = _flatten_results(client.get(indradb.AllEdgeQuery()))
            # Fetch properties for all edges to filter by name+value.
            all_edge_props: dict[tuple[str, str, str], dict[str, Any]] = {}
            for batch in client.get(indradb.AllEdgeQuery().properties()):
                for ep in batch:
                    edge = ep.edge
                    oid = str(getattr(edge, "outbound_id", ""))
                    iid = str(getattr(edge, "inbound_id", ""))
                    t_str = str(getattr(edge, "t", ""))
                    if oid and iid and t_str:
                        for np in ep.props:
                            all_edge_props.setdefault((oid, t_str, iid), {})[np.name] = np.value
            raw_e = [
                e
                for e in all_raw_e
                if all_edge_props.get((str(e.outbound_id), str(e.t), str(e.inbound_id)), {}).get(
                    edge_prop_name
                )
                == edge_prop_value
            ]
            self._last_total = len(raw_e)
            items_e = raw_e[:row_limit]
            props_list_e = [
                all_edge_props.get((str(e.outbound_id), str(e.t), str(e.inbound_id)), {})
                for e in items_e
            ]
            return [_coerce_edge(e, p) for e, p in zip(items_e, props_list_e, strict=True)]

        if verb == "pipe":
            # indradb.PipeQuery(direction) is wrong: the real API requires
            # PipeQuery(inner, direction) where inner is a query object and direction
            # is an EdgeDirection enum value.  Use the .outbound()/.inbound() helper
            # methods on SpecificVertexQuery instead — they construct PipeQuery correctly.
            _require_args(args, {"vertex_id", "direction"}, optional={"t"})
            vid = _validate_uuid(args["vertex_id"])
            direction = args["direction"]
            if direction not in {"outbound", "inbound"}:
                raise QueryParseError(
                    f"'direction' must be 'outbound' or 'inbound', got {direction!r}"
                )
            t_opt: str | None = None
            if "t" in args and args["t"] is not None:
                t_opt = _validate_t(args["t"])

            svq = indradb.SpecificVertexQuery(vid)
            # Use .outbound()/.inbound() if available (real indradb API ≥3.x).
            # The real client returns Edge objects from a PipeQuery; we then resolve
            # those edges to the neighbour Vertex objects.
            # The fake indradb client (tests/fixtures/fake_indradb.py) does not
            # implement .outbound()/.inbound() — fall back to the >> operator with
            # PipeQuery, which the fake resolves directly to Vertex objects.
            _use_rshift_fallback = not callable(getattr(svq, "outbound", None))
            if _use_rshift_fallback:
                # Fake-client path: PipeQuery(direction[, t]) via >> operator.
                pipe_fake: Any = indradb.PipeQuery(direction, t_opt)
                composed: Any = svq >> pipe_fake
                items = _flatten_results(client.get(composed))
                self._last_total = len(items)
                items = items[:row_limit]
                if not items:
                    return []
                sq_fake = indradb.SpecificVertexQuery(*[item.id for item in items])
                props_list_fake = _fetch_vertex_props(client, sq_fake, items)
                return [
                    _coerce_vertex(item, p) for item, p in zip(items, props_list_fake, strict=True)
                ]

            # Real-client path: use .outbound() / .inbound() which return PipeQuery
            # wrapping the inner query with the correct EdgeDirection enum.
            pipe_q = svq.outbound() if direction == "outbound" else svq.inbound()
            if t_opt is not None:
                pipe_q = pipe_q.t(t_opt)
            raw_edges = _flatten_results(client.get(pipe_q))
            self._last_total = len(raw_edges)
            edges = raw_edges[:row_limit]
            if not edges:
                return []
            # Resolve edges to neighbour Vertex objects.
            neighbor_ids = [
                e.inbound_id if direction == "outbound" else e.outbound_id for e in edges
            ]
            sq = indradb.SpecificVertexQuery(*neighbor_ids)
            neighbor_vertices = _flatten_results(client.get(sq))
            vid_to_vertex: dict[str, Any] = {str(v.id): v for v in neighbor_vertices}
            items = [vid_to_vertex[str(nid)] for nid in neighbor_ids if str(nid) in vid_to_vertex]
            if not items:
                return []
            sq2 = indradb.SpecificVertexQuery(*[v.id for v in items])
            props_list = _fetch_vertex_props(client, sq2, items)
            return [_coerce_vertex(item, p) for item, p in zip(items, props_list, strict=True)]

        # Unreachable — verb already validated above.
        raise QueryUnsupportedError(f"Unsupported verb {verb!r}")  # pragma: no cover

    def close(self) -> None:
        """Release resources.  Idempotent."""
        if self._closed:
            return
        try:
            if self._client is not None:
                with contextlib.suppress(Exception):
                    close_fn = getattr(self._client, "close", None)
                    if callable(close_fn):
                        close_fn()
        finally:
            self._client = None
            self._closed = True
