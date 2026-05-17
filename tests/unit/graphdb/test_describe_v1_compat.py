"""P5: v1 backward-compatibility tests for describe_graph_schema.

Tests that the read path (describe_graph_schema via IndraDbSchemaIntrospector)
tolerates legacy v1 graphs — schema_version='v1', nodes typed 'Variable', no
'access' on MEMBER_OF edges, no new Field/GlobalVariable properties.

Satisfies AC: S1-1 AC4, S1-2 AC5, S1-3 AC8, S1-4 AC5.
Design ref: §8, ADR-25 D1 (read path).
"""

from __future__ import annotations

import sys
import types
import uuid
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Re-use the fake IndraDB infrastructure from test_schema_introspector
# ---------------------------------------------------------------------------


class _FakeNamedProp:
    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.value = value


class _FakeVertexProperties:
    def __init__(self, vertex: Any, props: list[_FakeNamedProp]) -> None:
        self.vertex = vertex
        self.props = props


class _FakeEdgeProperties:
    def __init__(self, edge: Any, props: list[_FakeNamedProp]) -> None:
        self.edge = edge
        self.props = props


class _FakeVertex:
    def __init__(self, vid: uuid.UUID, t: str) -> None:
        self.id = vid
        self.t = t


class _FakeEdge:
    def __init__(self, outbound_id: uuid.UUID, t: str, inbound_id: uuid.UUID) -> None:
        self.outbound_id = outbound_id
        self.t = t
        self.inbound_id = inbound_id


class _FakePropertiesQuery:
    def __init__(self, source: Any) -> None:
        self.source = source


class _FakeSpecificVertexQuery:
    def __init__(self, vid: uuid.UUID) -> None:
        self.vid = vid
        self.vids = [vid]

    def properties(self) -> _FakePropertiesQuery:
        return _FakePropertiesQuery(self)


class _FakeSpecificEdgeQuery:
    def __init__(self, edge: _FakeEdge) -> None:
        self.edge = edge

    def properties(self) -> _FakePropertiesQuery:
        return _FakePropertiesQuery(self)


class _FakeAllVertexQuery:
    pass


_FakeAllVertexQuery.__name__ = "AllVertexQuery"
_FakeAllVertexQuery.__qualname__ = "AllVertexQuery"


class _FakeAllEdgeQuery:
    pass


_FakeAllEdgeQuery.__name__ = "AllEdgeQuery"
_FakeAllEdgeQuery.__qualname__ = "AllEdgeQuery"


class _FakeIndraDBClient:
    def __init__(
        self,
        vertices: list[_FakeVertex] | None = None,
        edges: list[_FakeEdge] | None = None,
        vertex_props: dict[uuid.UUID, dict[str, Any]] | None = None,
        edge_props: dict[tuple[uuid.UUID, str, uuid.UUID], dict[str, Any]] | None = None,
    ) -> None:
        self._vertices = vertices or []
        self._edges = edges or []
        self._vertex_props: dict[uuid.UUID, dict[str, Any]] = vertex_props or {}
        self._edge_props: dict[tuple[uuid.UUID, str, uuid.UUID], dict[str, Any]] = edge_props or {}

    def ping(self) -> None:
        pass

    def close(self) -> None:
        pass

    def get(self, query: Any) -> list[list[Any]]:
        if isinstance(query, _FakePropertiesQuery):
            source = query.source
            if isinstance(source, _FakeSpecificVertexQuery):
                props = self._vertex_props.get(source.vid, {})
                named = [_FakeNamedProp(k, v) for k, v in props.items()]
                vertex = next((v for v in self._vertices if v.id == source.vid), None)
                if vertex is not None:
                    return [[_FakeVertexProperties(vertex, named)]]
                return [[]]
            if isinstance(source, _FakeSpecificEdgeQuery):
                edge = source.edge
                key = (edge.outbound_id, edge.t, edge.inbound_id)
                props = self._edge_props.get(key, {})
                named = [_FakeNamedProp(k, v) for k, v in props.items()]
                return [[_FakeEdgeProperties(edge, named)]]
            return [[]]
        if hasattr(query, "__class__") and query.__class__.__name__ == "AllVertexQuery":
            return [self._vertices]
        if hasattr(query, "__class__") and query.__class__.__name__ == "AllEdgeQuery":
            return [self._edges]
        return [[]]


def _make_fake_indradb_module(client: _FakeIndraDBClient) -> types.ModuleType:
    mod = types.ModuleType("indradb")

    class _Client:
        def __init__(self, host: str = "localhost:27615", **kwargs: Any) -> None:
            pass

    _Client.__new__ = lambda cls, *a, **kw: client  # type: ignore[method-assign]

    mod.AllVertexQuery = _FakeAllVertexQuery  # type: ignore[attr-defined]
    mod.AllEdgeQuery = _FakeAllEdgeQuery  # type: ignore[attr-defined]
    mod.Client = _Client  # type: ignore[attr-defined]
    mod.SpecificVertexQuery = _FakeSpecificVertexQuery  # type: ignore[attr-defined]
    mod.SpecificEdgeQuery = _FakeSpecificEdgeQuery  # type: ignore[attr-defined]
    return mod


def _build_introspector(client: _FakeIndraDBClient) -> Any:
    from cpp_mcp.graphdb.schema_introspector import IndraDbSchemaIntrospector

    introspector = IndraDbSchemaIntrospector()
    introspector._client = client
    return introspector


# ---------------------------------------------------------------------------
# Fixture: v1 graph — File node with schema_version="v1", Variable nodes,
# MEMBER_OF edges without 'access' property (legacy v1 export shape).
# ---------------------------------------------------------------------------


def _make_v1_graph() -> tuple[_FakeIndraDBClient, types.ModuleType]:
    """Build an in-memory fake graph representing a v1 export.

    Contains:
      - 1 File node stamped with schema_version="v1"
      - 2 Variable nodes (legacy; replaced by Field/GlobalVariable in v2)
      - 1 MEMBER_OF edge with NO 'access' property
    """
    file_vid = uuid.uuid4()
    var1_vid = uuid.uuid4()
    var2_vid = uuid.uuid4()

    vertices = [
        _FakeVertex(file_vid, "File"),
        _FakeVertex(var1_vid, "Variable"),
        _FakeVertex(var2_vid, "Variable"),
    ]
    # MEMBER_OF edge has no 'access' property (legacy v1)
    member_edge = _FakeEdge(var1_vid, "MEMBER_OF", var2_vid)
    edges = [member_edge]

    vertex_props: dict[uuid.UUID, dict[str, Any]] = {
        file_vid: {"path": "/old/src.cpp", "spelling": "/old/src.cpp", "schema_version": "v1"},
        var1_vid: {"spelling": "x", "type": "int", "file": "/old/src.cpp", "line": 3, "col": 5},
        var2_vid: {"spelling": "MyClass", "type": "", "file": "/old/src.cpp", "line": 1, "col": 1},
    }
    # Edge has no 'access' property
    edge_props: dict[tuple[uuid.UUID, str, uuid.UUID], dict[str, Any]] = {
        (var1_vid, "MEMBER_OF", var2_vid): {},
    }

    client = _FakeIndraDBClient(
        vertices=vertices, edges=edges, vertex_props=vertex_props, edge_props=edge_props
    )
    return client, _make_fake_indradb_module(client)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestV1Compatibility:
    """describe_graph_schema read path must tolerate legacy v1 graphs (S1-4 AC5)."""

    def test_describe_v1_graph_does_not_raise(self) -> None:
        """No exception raised when introspecting a v1 graph (S1-1 AC4, S1-4 AC5)."""
        client, fake_mod = _make_v1_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)  # must not raise

        assert isinstance(result, dict)

    def test_describe_v1_graph_echoes_v1_schema_version(self) -> None:
        """The introspector DOES NOT inject SCHEMA_VERSION into legacy graphs.

        The describe response schema_version comes from the code constant
        (SCHEMA_VERSION), not from the stored graph value.  The stored v1
        value is surfaced as a skew note, not overwritten.  This test confirms
        the skew note is present and no exception is raised (S1-4 AC5).
        """
        client, fake_mod = _make_v1_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        # schema_version in the response is the *current* code version (SCHEMA_VERSION).
        # A skew note must appear because the stored File node has "v1" but code is "v2".
        from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

        assert result["schema_version"] == SCHEMA_VERSION

        # The skew note mentions the old value "v1".
        notes: list[str] = result["notes"]
        skew_notes = [n for n in notes if "v1" in n]
        assert skew_notes, (
            f"Expected a skew note mentioning 'v1' for a legacy v1 graph. Notes: {notes}"
        )

    def test_describe_v1_graph_includes_variable_node_type(self) -> None:
        """Legacy 'Variable' nodes appear in node_types without error (S1-1 AC4, ADR-25 D1)."""
        client, fake_mod = _make_v1_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        node_names = {nt["name"] for nt in result["node_types"]}
        assert "Variable" in node_names, (
            f"Expected legacy 'Variable' node type in v1 describe output. Got: {node_names}"
        )

    def test_describe_v1_member_of_edges_without_access_no_error(self) -> None:
        """MEMBER_OF edges without 'access' (v1) don't break describe (S1-2 AC5, S1-3 AC8)."""
        client, fake_mod = _make_v1_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        edge_names = {et["name"] for et in result["edge_types"]}
        assert "MEMBER_OF" in edge_names, (
            f"Expected 'MEMBER_OF' edge type in describe output. Got: {edge_names}"
        )

        member_of_entry = next(et for et in result["edge_types"] if et["name"] == "MEMBER_OF")
        # Legacy MEMBER_OF has no 'access' prop — property_keys should be empty.
        assert member_of_entry["property_keys"] == [], (
            f"Expected empty property_keys for legacy MEMBER_OF edge, "
            f"got: {member_of_entry['property_keys']}"
        )

    def test_describe_v1_graph_has_required_result_keys(self) -> None:
        """Result dict has all required keys even for v1 graphs (S1-4 AC5)."""
        client, fake_mod = _make_v1_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        for key in ("schema_version", "backend", "node_types", "edge_types", "totals", "notes"):
            assert key in result, f"Missing required key {key!r} in v1 compat describe result"
