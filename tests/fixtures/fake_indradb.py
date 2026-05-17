"""In-memory fake for the ``indradb`` Python client.

Provides the subset of the IndraDB API surface used by ``IndraDBDriver``
and ``IndraDbQueryExecutor``:

    Client, Vertex, Edge, Identifier, NamedProperty, VertexProperties,
    EdgeProperties, SpecificVertexQuery, SpecificEdgeQuery, BulkInserter,
    AllVertexQuery, AllEdgeQuery, VertexWithPropertyValueQuery,
    EdgeWithPropertyValueQuery, PipeQuery

S5 note: the real indradb client has no VertexWithTypeQuery or
EdgeWithTypeQuery — type filtering is done client-side in the executor.
Those classes are kept here as no-ops for any legacy test that imports them.

Install via monkeypatch before the driver module is imported::

    import types
    import fake_indradb
    monkeypatch.setitem(sys.modules, "indradb", fake_indradb)

The backing store is per-Client instance, so multiple clients do not share
data.  This matches the production isolation expectation (ADR-14 §5.7).

Configurable failure mode (for BDD and unit fail-path tests):

    client = Client(host="localhost:27615")
    client._fail_on_ping = True  # next ping() call raises RuntimeError

S5: ``client.get(query.properties())`` now returns batches of
``VertexProperties`` / ``EdgeProperties`` objects matching the real API:
  - VertexProperties: .vertex (Vertex), .props (list[NamedProperty])
  - EdgeProperties:   .edge (Edge),     .props (list[NamedProperty])
  - NamedProperty:    .name (str),       .value (Any)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


def _type_name(t: Identifier | str) -> str:
    """Normalise an edge/vertex type to a plain str.

    The real indradb 3.x Client accepts plain str for Vertex.t and Edge.t;
    fake_indradb must handle both to stay compat with drivers that pass str
    (post-v4-S1 patch) and legacy tests that still construct Identifier().
    """
    return t.name if isinstance(t, Identifier) else t


# ---------------------------------------------------------------------------
# Property value types (S5: match real indradb API shapes)
# ---------------------------------------------------------------------------


class NamedProperty:
    """Fake IndraDB NamedProperty (one property key+value on a vertex or edge)."""

    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f"NamedProperty({self.name!r}, {self.value!r})"


class VertexProperties:
    """Fake IndraDB VertexProperties (vertex + its properties, as returned by .properties())."""

    def __init__(self, vertex: Vertex, props: list[NamedProperty]) -> None:
        self.vertex = vertex
        self.props = props

    def __repr__(self) -> str:
        return f"VertexProperties({self.vertex!r}, {self.props!r})"


class EdgeProperties:
    """Fake IndraDB EdgeProperties (edge + its properties, as returned by .properties())."""

    def __init__(self, edge: Edge, props: list[NamedProperty]) -> None:
        self.edge = edge
        self.props = props

    def __repr__(self) -> str:
        return f"EdgeProperties({self.edge!r}, {self.props!r})"


# ---------------------------------------------------------------------------
# Core graph types
# ---------------------------------------------------------------------------


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

    def __init__(self, id: UUID, t: Identifier | str) -> None:
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

    def __init__(self, outbound_id: UUID, t: Identifier | str, inbound_id: UUID) -> None:
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


# ---------------------------------------------------------------------------
# Properties-mode query wrappers (returned by .properties() chaining)
# ---------------------------------------------------------------------------


class _VertexPropertiesQuery:
    """Internal: marks a query as properties-mode for vertex queries."""

    def __init__(self, source: Any) -> None:
        self.source = source  # the originating query


class _EdgePropertiesQuery:
    """Internal: marks a query as properties-mode for edge queries."""

    def __init__(self, source: Any) -> None:
        self.source = source  # the originating query


# ---------------------------------------------------------------------------
# Query types
# ---------------------------------------------------------------------------


class SpecificEdgeQuery:
    """Fake IndraDB query selecting one or more specific edges by Edge key.

    S5: real API accepts multiple edges (variadic). Fake stores as a list.
    """

    def __init__(self, *edges: Edge) -> None:
        self.edges = list(edges)

    def properties(self) -> _EdgePropertiesQuery:
        return _EdgePropertiesQuery(self)


class AllVertexQuery:
    """Fake IndraDB query selecting all vertices."""

    def properties(self) -> _VertexPropertiesQuery:
        return _VertexPropertiesQuery(self)


class AllEdgeQuery:
    """Fake IndraDB query selecting all edges."""

    def properties(self) -> _EdgePropertiesQuery:
        return _EdgePropertiesQuery(self)


class VertexWithPropertyValueQuery:
    """Fake IndraDB query selecting vertices where a property equals a value."""

    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.value = value

    def properties(self) -> _VertexPropertiesQuery:
        return _VertexPropertiesQuery(self)


class EdgeWithPropertyValueQuery:
    """Fake IndraDB query selecting edges where a property equals a value."""

    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.value = value

    def properties(self) -> _EdgePropertiesQuery:
        return _EdgePropertiesQuery(self)


class PipeQuery:
    """Fake IndraDB pipe traversal query (one hop from a specific vertex)."""

    def __init__(self, direction: str, t: str | None = None) -> None:
        self.direction = direction
        self.t = t


class SpecificVertexQuery:
    """Fake IndraDB query selecting one or more specific vertices by UUID.

    S5: real API accepts multiple UUIDs (variadic). Fake stores as a list.
    """

    def __init__(self, *vids: UUID) -> None:
        self.vids = list(vids)
        # Legacy single-vid compat: expose .vid for tests that read it.
        self.vid: UUID | None = vids[0] if len(vids) == 1 else None

    def __rshift__(self, pipe: PipeQuery) -> _PipeComposed:
        """Support ``SpecificVertexQuery(...) >> PipeQuery(...)`` syntax."""
        return _PipeComposed(self, pipe)

    def properties(self) -> _VertexPropertiesQuery:
        return _VertexPropertiesQuery(self)


# Legacy no-op classes (real indradb has no VertexWithTypeQuery / EdgeWithTypeQuery).
# Kept so any legacy test import doesn't fail; executor no longer uses them.


class VertexWithTypeQuery:
    """Legacy stub — real indradb has no VertexWithTypeQuery; type-filtering is client-side."""

    def __init__(self, t: str) -> None:
        self.t = t


class EdgeWithTypeQuery:
    """Legacy stub — real indradb has no EdgeWithTypeQuery; type-filtering is client-side."""

    def __init__(self, t: str) -> None:
        self.t = t


class _PipeComposed:
    """Internal: result of ``SpecificVertexQuery >> PipeQuery``."""

    def __init__(self, vertex_query: SpecificVertexQuery, pipe: PipeQuery) -> None:
        self.vertex_query = vertex_query
        self.pipe = pipe


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
            for vid in query.vids:
                props = self._vertex_props.setdefault(vid, {})
                props[name] = value
        elif isinstance(query, SpecificEdgeQuery):
            for edge in query.edges:
                edge_key = (
                    edge.outbound_id,
                    _type_name(edge.t),
                    edge.inbound_id,
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

    def get(self, query: Any) -> list[list[Any]]:
        """Return matching records for a query.

        The real ``indradb.Client.get()`` is a gRPC streaming call that yields
        *batches* of results — each batch is a list of items.  To match that
        shape, this fake returns ``[[item, ...]]`` (one batch) or ``[[]]`` when
        nothing matches, so that callers using the batch-flatten idiom
        ``any(item for batch in client.get(q) for item in batch)``
        work correctly against both the real daemon and this fake.

        Properties-mode queries (``query.properties()`` calls) return batches of
        ``VertexProperties`` / ``EdgeProperties`` objects (S5 API shape).

        Supports:
          - ``SpecificVertexQuery`` — single/multi vertex lookup.
          - ``SpecificEdgeQuery`` — single/multi edge lookup.
          - ``AllVertexQuery`` — all vertices.
          - ``AllEdgeQuery`` — all edges.
          - ``VertexWithPropertyValueQuery`` — vertices where property == value.
          - ``EdgeWithPropertyValueQuery`` — edges where property == value.
          - ``_VertexPropertiesQuery`` — VertexProperties batches.
          - ``_EdgePropertiesQuery`` — EdgeProperties batches.
          - ``_PipeComposed`` (``SpecificVertexQuery >> PipeQuery``) — one-hop
            neighbor vertices.
        """
        # Properties-mode: return VertexProperties / EdgeProperties objects.
        if isinstance(query, _VertexPropertiesQuery):
            return self._get_vertex_properties(query.source)
        if isinstance(query, _EdgePropertiesQuery):
            return self._get_edge_properties(query.source)

        if isinstance(query, SpecificVertexQuery):
            items = [self._vertices[vid] for vid in query.vids if vid in self._vertices]
            return [items] if items else [[]]
        if isinstance(query, SpecificEdgeQuery):
            items = [e for e in query.edges if e in self._edges]
            return [items] if items else [[]]
        if isinstance(query, AllVertexQuery):
            items_v = list(self._vertices.values())
            return [items_v] if items_v else [[]]
        if isinstance(query, AllEdgeQuery):
            items_e = list(self._edges)
            return [items_e] if items_e else [[]]
        if isinstance(query, VertexWithPropertyValueQuery):
            matched = [
                v
                for vid, v in self._vertices.items()
                if self._vertex_props.get(vid, {}).get(query.name) == query.value
            ]
            return [matched] if matched else [[]]
        if isinstance(query, EdgeWithPropertyValueQuery):
            matched_e = [
                e
                for e in self._edges
                if self._edge_props.get((e.outbound_id, _type_name(e.t), e.inbound_id), {}).get(
                    query.name
                )
                == query.value
            ]
            return [matched_e] if matched_e else [[]]
        if isinstance(query, _PipeComposed):
            return self._get_pipe(query)
        return [[]]

    def _get_vertex_properties(self, source: Any) -> list[list[Any]]:
        """Return VertexProperties batches for a vertex query."""
        vertices: list[Vertex] = []

        if isinstance(source, SpecificVertexQuery):
            for vid in source.vids:
                if vid in self._vertices:
                    vertices.append(self._vertices[vid])
        elif isinstance(source, AllVertexQuery):
            vertices = list(self._vertices.values())
        elif isinstance(source, VertexWithPropertyValueQuery):
            vertices = [
                v
                for vid, v in self._vertices.items()
                if self._vertex_props.get(vid, {}).get(source.name) == source.value
            ]

        result: list[VertexProperties] = []
        for vertex in vertices:
            props_dict = self._vertex_props.get(vertex.id, {})
            named_props = [NamedProperty(k, v) for k, v in props_dict.items()]
            result.append(VertexProperties(vertex, named_props))
        return [result] if result else [[]]

    def _get_edge_properties(self, source: Any) -> list[list[Any]]:
        """Return EdgeProperties batches for an edge query."""
        edges: list[Edge] = []

        if isinstance(source, SpecificEdgeQuery):
            edges = [e for e in source.edges if e in self._edges]
        elif isinstance(source, AllEdgeQuery):
            edges = list(self._edges)
        elif isinstance(source, EdgeWithPropertyValueQuery):
            edges = [
                e
                for e in self._edges
                if self._edge_props.get((e.outbound_id, _type_name(e.t), e.inbound_id), {}).get(
                    source.name
                )
                == source.value
            ]

        result: list[EdgeProperties] = []
        for edge in edges:
            key = (edge.outbound_id, _type_name(edge.t), edge.inbound_id)
            props_dict = self._edge_props.get(key, {})
            named_props = [NamedProperty(k, v) for k, v in props_dict.items()]
            result.append(EdgeProperties(edge, named_props))
        return [result] if result else [[]]

    def _get_pipe(self, query: _PipeComposed) -> list[list[Any]]:
        """Resolve a pipe (one-hop neighbor vertex) query."""
        # Use first vid if multi-id (pipe only makes sense from a single vertex).
        vids = query.vertex_query.vids
        if not vids:
            return [[]]
        vid = vids[0]
        direction = query.pipe.direction
        t_filter = query.pipe.t
        neighbor_ids: list[UUID] = []
        for edge in self._edges:
            edge_t = _type_name(edge.t)
            if t_filter is not None and edge_t != t_filter:
                continue
            if direction == "outbound" and edge.outbound_id == vid:
                neighbor_ids.append(edge.inbound_id)
            elif direction == "inbound" and edge.inbound_id == vid:
                neighbor_ids.append(edge.outbound_id)
        items = [self._vertices[nid] for nid in neighbor_ids if nid in self._vertices]
        return [items] if items else [[]]

    def get_properties(self, query: Any) -> list[list[Any]]:
        """Legacy method — delegates to get(query.properties()) for compat.

        The real indradb Client does not expose get_properties(); this exists
        only to avoid breaking any test that still calls it directly.
        """
        if hasattr(query, "properties"):
            return self.get(query.properties())
        return [[]]

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
