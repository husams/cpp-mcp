"""GraphDB package: Protocol, schema constants, and driver implementations.

Public API
----------
- :class:`~cpp_mcp.graphdb.driver.GraphDriver` — structural Protocol
- :class:`~cpp_mcp.graphdb.driver.NodeRecord` — TypedDict for nodes
- :class:`~cpp_mcp.graphdb.driver.EdgeRecord` — TypedDict for edges
- :func:`select_driver` — pure scheme dispatch: returns an *unconnected* driver
  instance for the given URI; caller must invoke :meth:`GraphDriver.connect` next.

URI schemes
-----------
``bolt://``, ``bolt+s://``, ``bolt+ssc://``, ``neo4j://``, ``neo4j+s://``, ``neo4j+ssc://``
    Returns a :class:`~cpp_mcp.graphdb.neo4j_driver.Neo4jDriver`.

``indradb://``, ``grpc://``, ``indradb+grpc://``
    Returns a :class:`~cpp_mcp.graphdb.indradb_driver.IndraDBDriver`.
"""

from __future__ import annotations

from urllib.parse import urlparse

from cpp_mcp.core.error_envelope import InvalidArgumentError
from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord

__all__ = [
    "EdgeRecord",
    "GraphDriver",
    "NodeRecord",
    "select_driver",
]

_NEO4J_SCHEMES: frozenset[str] = frozenset(
    {"bolt", "bolt+s", "bolt+ssc", "neo4j", "neo4j+s", "neo4j+ssc"}
)
_INDRADB_SCHEMES: frozenset[str] = frozenset({"indradb", "grpc", "indradb+grpc"})


def select_driver(db_uri: str) -> GraphDriver:
    """Return an *unconnected* :class:`GraphDriver` instance for *db_uri*'s scheme.

    This function is pure scheme dispatch — no I/O, no package imports.
    The caller must invoke :meth:`GraphDriver.connect` after receiving the instance.

    Args:
        db_uri: Driver URI including scheme (e.g. ``"bolt://localhost:7687"``).
            Supported schemes:

            - Neo4j: ``bolt``, ``bolt+s``, ``bolt+ssc``, ``neo4j``, ``neo4j+s``,
              ``neo4j+ssc``.
            - IndraDB: ``indradb``, ``grpc``, ``indradb+grpc``.

    Returns:
        An unconnected :class:`GraphDriver` instance appropriate for the scheme.

    Raises:
        :exc:`~cpp_mcp.core.error_envelope.InvalidArgumentError`: if *db_uri* is
            empty, missing ``://``, or has an unrecognised scheme.

    Example::

        driver = select_driver("bolt://localhost:7687")
        driver.connect("bolt://localhost:7687")
    """
    if not db_uri or "://" not in db_uri:
        raise InvalidArgumentError(
            f"db_uri must include a scheme (got {db_uri!r}); "
            f"supported: {sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
        )
    scheme = urlparse(db_uri).scheme
    if scheme in _NEO4J_SCHEMES:
        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        return Neo4jDriver()
    if scheme in _INDRADB_SCHEMES:
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        return IndraDBDriver()
    raise InvalidArgumentError(
        f"Unsupported db_uri scheme {scheme!r}; "
        f"supported: {sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
    )
