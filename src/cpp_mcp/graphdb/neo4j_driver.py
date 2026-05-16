"""Neo4j Bolt driver implementation (ADR-7 MVP backend).

``neo4j`` is an optional dependency (``pip install cpp-mcp[graphdb]``).
This module imports it lazily inside :meth:`Neo4jDriver.connect` so that the
rest of the server starts without it installed.

Idempotency strategy (ADR-7):
  - Nodes: ``MERGE (n:Label {usr: $usr}) SET n += $props``
  - Edges: ``MERGE (a {usr: $src})-[r:TYPE]->(b {usr: $tgt})``

Each file's nodes + edges are written in a single ``execute_write`` transaction,
satisfying the per-file atomicity requirement (ADR-7 / US-7/AC-5).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from cpp_mcp.core.error_envelope import DBUnreachableError, DependencyMissingError
from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord

logger = logging.getLogger(__name__)


class Neo4jDriver:
    """Bolt-backed graph driver; satisfies the ``GraphDriver`` Protocol."""

    def __init__(self) -> None:
        self._driver: Any = None  # neo4j.GraphDatabase.driver instance

    # ------------------------------------------------------------------
    # connect
    # ------------------------------------------------------------------

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open a Bolt connection to *uri*.

        Args:
            uri: Bolt URI, e.g. ``"bolt://localhost:7687"``.
            **kwargs: Additional keyword args forwarded to the neo4j driver
                constructor (e.g. ``auth=("neo4j", "password")``).

        Raises:
            :exc:`DependencyMissingError`: when the ``neo4j`` package is not installed.
            :exc:`DBUnreachableError`: wraps any neo4j connectivity exception.
        """
        try:
            # Lazy import — only required when graphdb extra is installed.
            import neo4j  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DependencyMissingError(
                "neo4j Python driver is not installed. "
                'Install with: pip install "cpp-mcp[graphdb-neo4j]"'
            ) from exc

        try:
            driver = neo4j.GraphDatabase.driver(uri, **kwargs)
            # Verify connectivity eagerly so that DB_UNREACHABLE fires before
            # any file is parsed (ADR-7 / SC-US-7-2).
            driver.verify_connectivity()
            self._driver = driver
            logger.debug("Neo4j connected: %s", uri)
        except Exception as exc:
            raise DBUnreachableError(f"Cannot reach graph database at {uri!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # upsert_nodes
    # ------------------------------------------------------------------

    def upsert_nodes(self, batch: list[NodeRecord]) -> int:
        """Upsert *batch* nodes in a single transaction.

        Uses ``MERGE (n:Label {usr: $usr}) SET n += $props`` per node.
        """
        if not batch or self._driver is None:
            return 0

        def _tx(tx: Any, records: list[NodeRecord]) -> int:
            written = 0
            for rec in records:
                label = rec["label"]
                usr = rec["usr"]
                props = dict(rec["props"])
                props["usr"] = usr  # ensure USR is in props for retrieval
                query = f"MERGE (n:`{label}` {{usr: $usr}}) SET n += $props RETURN n"
                result = tx.run(query, usr=usr, props=props)
                if result.single() is not None:
                    written += 1
            return written

        with self._driver.session() as sess:
            return int(sess.execute_write(_tx, batch))

    # ------------------------------------------------------------------
    # upsert_edges
    # ------------------------------------------------------------------

    def upsert_edges(self, batch: list[EdgeRecord]) -> int:
        """Upsert *batch* edges in a single transaction.

        Uses MERGE on (source_usr, target_usr, edge_type) as the natural key.
        """
        if not batch or self._driver is None:
            return 0

        def _tx(tx: Any, records: list[EdgeRecord]) -> int:
            written = 0
            for rec in records:
                src = rec["source_usr"]
                tgt = rec["target_usr"]
                etype = rec["edge_type"]
                props = rec["props"]
                query = (
                    "MATCH (a {usr: $src}), (b {usr: $tgt}) "
                    f"MERGE (a)-[r:`{etype}`]->(b) "
                    "SET r += $props "
                    "RETURN r"
                )
                result = tx.run(query, src=src, tgt=tgt, props=props)
                if result.single() is not None:
                    written += 1
            return written

        with self._driver.session() as sess:
            return int(sess.execute_write(_tx, batch))

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the Bolt driver and release resources."""
        if self._driver is not None:
            with contextlib.suppress(Exception):
                self._driver.close()
            self._driver = None
