"""In-memory fake for the ``indradb`` Python client.

Provides the subset of the IndraDB API surface used by ``IndraDBDriver``:

    Client, Vertex, Edge, Identifier, SpecificVertexQuery,
    SpecificEdgeQuery, BulkInserter

Install via monkeypatch before the driver module is imported::

    import types
    import fake_indradb
    monkeypatch.setitem(sys.modules, "indradb", fake_indradb)

The backing store is per-Client instance, so multiple clients do not share
data.  This matches the production isolation expectation (ADR-14 §5.7).

Configurable failure mode (for BDD and unit fail-path tests):

    client = Client(host="localhost:27615")
    client._fail_on_ping = True  # next ping() call raises RuntimeError
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


def _type_name(t: "Identifier | str") -> str:
    """Normalise an edge/vertex type to a plain str.

    The real indradb 3.x Client accepts plain str for Vertex.t and Edge.t;
    fake_indradb must handle both to stay compat with drivers that pass str
    (post-v4-S1 patch) and legacy tests that still construct Identifier().
    """
    return t.name if isinstance(t, Identifier) else t


class Identifier:
    """Fake IndraDB Identifier (a named type/label string)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Identifier) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"Identifier({self.name!r})"


class Vertex:
    """Fake IndraDB Vertex (id: UUID, t: Identifier | str)."""

    def __init__(self, id: UUID, t: "Identifier | str") -> None:
        self.id = id
        self.t = t

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Vertex)
            and self.id == other.id
            and _type_name(self.t) == _type_name(other.t)
        )

    def __hash__(self) -> int:
        return hash((self.id, _type_name(self.t)))

    def __repr__(self) -> str:
        return f"Vertex({self.id!r}, {self.t!r})"


class Edge:
    """Fake IndraDB Edge (outbound_id: UUID, t: Identifier | str, inbound_id: UUID)."""

    def __init__(self, outbound_id: UUID, t: "Identifier | str", inbound_id: UUID) -> None:
        self.outbound_id = outbound_id
        self.t = t
        self.inbound_id = inbound_id

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Edge)
            and self.outbound_id == other.outbound_id
            and _type_name(self.t) == _type_name(other.t)
            and self.inbound_id == other.inbound_id
        )

    def __hash__(self) -> int:
        return hash((self.outbound_id, _type_name(self.t), self.inbound_id))

    def __repr__(self) -> str:
        return f"Edge({self.outbound_id!r}, {self.t!r}, {self.inbound_id!r})"


class SpecificVertexQuery:
    """Fake IndraDB query selecting a single vertex by UUID."""

    def __init__(self, vid: UUID) -> None:
        self.vid = vid


class SpecificEdgeQuery:
    """Fake IndraDB query selecting a single edge by Edge key."""

    def __init__(self, edge: Edge) -> None:
        self.edge = edge


class BulkInserter:
    """Stub BulkInserter — not used by IndraDBDriver but present for API completeness."""

    def __enter__(self) -> BulkInserter:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class Client:
    """In-memory fake IndraDB client.

    Attributes
    ----------
    _fail_on_ping:
        When True, the next ``ping()`` call raises ``RuntimeError``.  Used to
        simulate a connectivity failure in fail-path tests and BDD.
    _vertices:
        ``dict[UUID, Vertex]`` — the vertex store.
    _vertex_props:
        ``dict[UUID, dict[str, Any]]`` — properties keyed by vertex UUID.
    _edges:
        ``set[Edge]`` — the edge store (uses Edge.__hash__/__eq__).
    _edge_props:
        ``dict[tuple[UUID, str, UUID], dict[str, Any]]`` — edge properties.
    """

    def __init__(self, host: str = "localhost:27615", **kwargs: Any) -> None:
        self.host = host
        self._fail_on_ping: bool = False
        self._vertices: dict[UUID, Vertex] = {}
        self._vertex_props: dict[UUID, dict[str, Any]] = {}
        self._edges: set[Edge] = set()
        self._edge_props: dict[tuple[UUID, str, UUID], dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def ping(self) -> None:
        """Simulate connectivity check.  Raises RuntimeError if _fail_on_ping is True."""
        if self._fail_on_ping:
            raise RuntimeError("fake IndraDB: ping failed (configured failure)")

    def close(self) -> None:
        """No-op close — satisfies idempotent close contract."""

    # ------------------------------------------------------------------
    # Vertex operations
    # ------------------------------------------------------------------

    def create_vertex(self, vertex: Vertex) -> bool:
        """Insert vertex.  Returns True if new, False if already exists (idempotent)."""
        if vertex.id in self._vertices:
            return False
        self._vertices[vertex.id] = vertex
        return True

    def set_properties(
        self,
        query: SpecificVertexQuery | SpecificEdgeQuery,
        name: str,
        value: Any,
    ) -> None:
        """Overwrite a named property on the target vertex or edge."""
        if isinstance(query, SpecificVertexQuery):
            props = self._vertex_props.setdefault(query.vid, {})
            props[name] = value
        elif isinstance(query, SpecificEdgeQuery):
            edge_key = (
                query.edge.outbound_id,
                _type_name(query.edge.t),
                query.edge.inbound_id,
            )
            props = self._edge_props.setdefault(edge_key, {})
            props[name] = value

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def create_edge(self, edge: Edge) -> bool:
        """Insert edge.  Returns True if new, False if already exists (idempotent)."""
        if edge in self._edges:
            return False
        self._edges.add(edge)
        return True

    # ------------------------------------------------------------------
    # Introspection helpers (used by unit tests and BDD step impls)
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Number of vertices currently in the fake store."""
        return len(self._vertices)

    @property
    def edge_count(self) -> int:
        """Number of edges currently in the fake store."""
        return len(self._edges)

    def get_vertex_props(self, vid: UUID) -> dict[str, Any]:
        """Return property dict for a vertex UUID, or empty dict if absent."""
        return dict(self._vertex_props.get(vid, {}))

    def get_edge_props(self, outbound: UUID, edge_type: str, inbound: UUID) -> dict[str, Any]:
        """Return property dict for an edge triple, or empty dict if absent."""
        return dict(self._edge_props.get((outbound, edge_type, inbound), {}))
