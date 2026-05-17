"""GraphDriver Protocol and data model types (ADR-7).

Defines the structural Protocol that all graph database backends must satisfy.
The MVP implementation is ``neo4j_driver.Neo4jDriver``.  A Cognee driver can
be added later by implementing the same Protocol — no tool or exporter changes
are needed.

Node / Edge representations use TypedDicts so that mypy can check the caller
side without requiring a concrete class.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class NodeRecord(TypedDict):
    """Flat representation of one graph node to be upserted.

    Fields
    ------
    label:
        Schema node type label (e.g. ``"Function"``, ``"Class"``).
    usr:
        libclang Unified Symbol Resolution string — used as the primary key
        for idempotent MERGE operations.
    props:
        Additional properties stored on the node (spelling, file, line, …).
    """

    label: str
    usr: str
    props: dict[str, Any]


class EdgeRecord(TypedDict):
    """Flat representation of one directed graph edge to be upserted.

    Idempotency key is ``(source_usr, target_usr, edge_type)``.
    """

    source_usr: str
    target_usr: str
    edge_type: str
    props: dict[str, Any]


class GraphDriver(Protocol):
    """Structural Protocol for graph database backends (ADR-7).

    All methods are synchronous; callers run them inside the ThreadPoolExecutor
    that already serialises libclang work, so no async is needed here.

    Implementations MUST be idempotent: ``upsert_nodes`` and ``upsert_edges``
    MUST use MERGE-style semantics (or equivalent) so that re-exporting the
    same file does not duplicate data.
    """

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Establish a connection to the graph database at *uri*.

        Raises:
            :exc:`cpp_mcp.core.error_envelope.DBUnreachableError`: if the
                database cannot be reached (network failure, bad auth, …).
        """
        ...

    def upsert_nodes(self, batch: list[NodeRecord]) -> int:
        """Write *batch* of nodes using MERGE-on-USR semantics.

        Returns:
            Number of nodes **actually created** (inserts only).  A repeated
            upsert of identical ``(label, usr)`` records returns 0 — the
            operation is idempotent and the return value proves it (ADR-17).
        """
        ...

    def upsert_edges(self, batch: list[EdgeRecord]) -> int:
        """Write *batch* of edges using MERGE semantics.

        Returns:
            Number of edges **actually created** (inserts only).  A repeated
            upsert of identical ``(src, type, tgt)`` returns 0 (ADR-17).
        """
        ...

    def close(self) -> None:
        """Release all resources held by this driver."""
        ...
