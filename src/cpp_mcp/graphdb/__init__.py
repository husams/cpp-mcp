"""GraphDB package: Protocol, schema constants, and driver implementations.

Public API
----------
- :class:`~cpp_mcp.graphdb.driver.GraphDriver` — structural Protocol
- :class:`~cpp_mcp.graphdb.driver.NodeRecord` — TypedDict for nodes
- :class:`~cpp_mcp.graphdb.driver.EdgeRecord` — TypedDict for edges
- :func:`make_driver` — factory: returns the right driver for a given URI scheme

URI schemes
-----------
``bolt://...``
    Returns a :class:`~cpp_mcp.graphdb.neo4j_driver.Neo4jDriver`.

``cognee://<dataset>``
    Returns a :class:`~cpp_mcp.graphdb.cognee_driver.CogneeDriver` targeting
    the named Cognee dataset.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord

__all__ = [
    "EdgeRecord",
    "GraphDriver",
    "NodeRecord",
    "make_driver",
]


def make_driver(uri: str, **kwargs: Any) -> GraphDriver:
    """Return a concrete :class:`GraphDriver` appropriate for *uri*'s scheme.

    Args:
        uri:      Driver URI.  Supported schemes:

                  - ``bolt://...`` — Neo4j Bolt driver.
                  - ``neo4j://...`` or ``neo4j+s://...`` — Neo4j routing driver.
                  - ``cognee://<dataset>`` — Cognee ingest driver.

        **kwargs: Forwarded verbatim to :meth:`GraphDriver.connect`.

    Returns:
        A connected :class:`GraphDriver` instance.

    Raises:
        :exc:`cpp_mcp.core.error_envelope.DBUnreachableError`: if the
            underlying driver cannot establish a connection.
        :exc:`ValueError`: if *uri*'s scheme is not recognised.

    Example::

        driver = make_driver("bolt://localhost:7687", auth=("neo4j", "pass"))
        driver = make_driver("cognee://cpp-knowledge", node_set=["project:myrepo"])
    """
    scheme = urlparse(uri).scheme

    if scheme in ("bolt", "neo4j", "neo4j+s", "bolt+s"):
        # Lazy import so neo4j package is optional.
        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        driver: GraphDriver = Neo4jDriver()
        driver.connect(uri, **kwargs)
        return driver

    if scheme == "cognee":
        from cpp_mcp.graphdb.cognee_driver import CogneeDriver

        cdriver = CogneeDriver()
        cdriver.connect(uri, **kwargs)
        return cdriver

    raise ValueError(
        f"Unsupported graph database URI scheme {scheme!r} in {uri!r}. "
        "Expected 'bolt://', 'neo4j://', or 'cognee://'."
    )
