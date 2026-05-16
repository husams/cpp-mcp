"""IndraDB gRPC driver implementation (ADR-7 backend, v3 graphdb-multi).

``indradb`` is an optional dependency (``pip install cpp-mcp[graphdb-indradb]``).
This module imports it lazily inside :meth:`IndraDBDriver.connect` so that the
rest of the server starts without it installed (C-G5).

Idempotency strategy (ADR-14, ADR-7):
  - Nodes: ``create_vertex(Vertex(uuid5(NS_CPPMCP_USR, usr), Identifier(label)))``
    — IndraDB's create_vertex is a no-op on existing identical record.
  - Edges: ``create_edge(Edge(src_uuid, Identifier(edge_type), tgt_uuid))``
    — keyed by (outbound, type, inbound); repeated call is a no-op.

Property serialisation follows ADR-15: JSON scalars pass through; non-scalars
are JSON-encoded; unencodable objects fall back to repr() with a debug log.

URI schemes accepted: ``indradb://``, ``grpc://``, ``indradb+grpc://``.
Default port: 27615 (IndraDB upstream default).
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from typing import Any
from urllib.parse import urlparse

from cpp_mcp.core.error_envelope import DBUnreachableError, DependencyMissingError
from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# USR → vertex UUID namespace (ADR-14)
# Generated once; pinned here as a wire-format constant.  DO NOT CHANGE.
# ---------------------------------------------------------------------------
NS_CPPMCP_USR = uuid.UUID("8f6e2c1b-7d3a-4f59-9a4b-1c0d2e5f8a91")

# ---------------------------------------------------------------------------
# Property serialisation helpers (ADR-15)
# ---------------------------------------------------------------------------

_SCALAR = (str, int, float, bool, type(None))

_DEFAULT_PORT = 27615


def _normalise_prop(key: str, value: Any) -> Any:
    """Normalise a property value for IndraDB storage (ADR-15).

    JSON scalars pass through unchanged.  Other types are JSON-encoded for
    deterministic idempotency (sort_keys=True).  Unencodable objects fall back
    to repr() with a debug log.
    """
    if isinstance(value, _SCALAR):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        logger.debug(
            "indradb prop %r is not JSON-serialisable; storing repr()",
            key,
        )
        return repr(value)


def _strip_scheme(uri: str) -> str:
    """Return 'host:port' from an IndraDB URI, applying default port if absent."""
    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or _DEFAULT_PORT
    return f"{host}:{port}"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


class IndraDBDriver:
    """IndraDB gRPC-backed graph driver; satisfies the ``GraphDriver`` Protocol."""

    def __init__(self) -> None:
        self._client: Any = None  # indradb.Client instance
        self._closed: bool = False

    # ------------------------------------------------------------------
    # connect
    # ------------------------------------------------------------------

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open an IndraDB gRPC connection to *uri*.

        Args:
            uri: IndraDB URI, e.g. ``"indradb://localhost:27615"``.
                Accepted schemes: ``indradb``, ``grpc``, ``indradb+grpc``.
            **kwargs: Additional keyword args forwarded to ``indradb.Client``.

        Raises:
            :exc:`DependencyMissingError`: when the ``indradb`` package is not installed.
            :exc:`DBUnreachableError`: wraps any IndraDB connectivity exception.
        """
        try:
            import indradb  # type: ignore[import-not-found]  # lazy — optional dep
        except ImportError as exc:
            raise DependencyMissingError(
                "indradb Python driver is not installed. "
                'Install with: pip install "cpp-mcp[graphdb-indradb]"'
            ) from exc

        host = _strip_scheme(uri)
        try:
            self._client = indradb.Client(host=host, **kwargs)
            self._client.ping()
            logger.debug("IndraDB connected: %s", uri)
        except Exception as exc:
            raise DBUnreachableError(f"Cannot reach graph database at {uri!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # upsert_nodes
    # ------------------------------------------------------------------

    def upsert_nodes(self, batch: list[NodeRecord]) -> int:
        """Upsert *batch* nodes using uuid5(NS_CPPMCP_USR, usr) as vertex id.

        Idempotency: same USR → same UUID → IndraDB create_vertex is a no-op on
        repeat.  Property writes use overwrite semantics, so a re-export yields
        identical values (ADR-14, ADR-15).

        Returns:
            Number of records processed.
        """
        if not batch or self._client is None:
            return 0

        import indradb  # re-import is safe; module already in sys.modules after connect()

        for rec in batch:
            usr = rec["usr"]
            label = rec["label"]
            vid = uuid.uuid5(NS_CPPMCP_USR, usr)
            vtype = indradb.Identifier(label)
            self._client.create_vertex(indradb.Vertex(vid, vtype))
            props: dict[str, Any] = dict(rec["props"])
            props["usr"] = usr
            for key, value in props.items():
                norm = _normalise_prop(key, value)
                self._client.set_properties(
                    indradb.SpecificVertexQuery(vid),
                    name=key,
                    value=norm,
                )

        return len(batch)

    # ------------------------------------------------------------------
    # upsert_edges
    # ------------------------------------------------------------------

    def upsert_edges(self, batch: list[EdgeRecord]) -> int:
        """Upsert *batch* edges.

        Idempotency: IndraDB edges are keyed by (outbound_id, type, inbound_id);
        calling create_edge twice with the same triple is a no-op (ADR-14).

        Returns:
            Number of records processed.
        """
        if not batch or self._client is None:
            return 0

        import indradb  # re-import is safe; module already in sys.modules after connect()

        for rec in batch:
            src_vid = uuid.uuid5(NS_CPPMCP_USR, rec["source_usr"])
            tgt_vid = uuid.uuid5(NS_CPPMCP_USR, rec["target_usr"])
            etype = indradb.Identifier(rec["edge_type"])
            edge = indradb.Edge(outbound_id=src_vid, t=etype, inbound_id=tgt_vid)
            self._client.create_edge(edge)
            for key, value in rec["props"].items():
                norm = _normalise_prop(key, value)
                self._client.set_properties(
                    indradb.SpecificEdgeQuery(edge),
                    name=key,
                    value=norm,
                )

        return len(batch)

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release resources held by this driver.  Idempotent — safe to call twice."""
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
