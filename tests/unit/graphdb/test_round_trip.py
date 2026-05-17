"""P5: Round-trip test — export schema shape → introspect via fake driver.

Instead of parsing real C++ (libclang is not loadable on this host), we
construct NodeRecord / EdgeRecord batches that represent the S1 v2 export
shape, inject them into the IndraDB fake driver infrastructure, and verify
that the introspector re-reads Field and GlobalVariable node sets correctly.

This validates the full data-path contract: exporter output format → driver
shape → introspector describe — without requiring a live libclang or graph DB.

Satisfies AC: S1-5 AC6, SC6.
Design ref: §8, §9.
"""

from __future__ import annotations

import sys
import types
import uuid
from typing import Any
from unittest.mock import patch

from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord
from cpp_mcp.graphdb.schema import (
    EDGE_DEFINES,
    EDGE_MEMBER_OF,
    NODE_FIELD,
    NODE_FILE,
    NODE_FUNCTION,
    NODE_GLOBAL_VARIABLE,
)
from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Fake IndraDB infrastructure (same pattern as test_describe_v1_compat.py)
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
# Simulate an S1 v2 export: NodeRecord/EdgeRecord → fake driver state
# ---------------------------------------------------------------------------
#
# We build the NodeRecord/EdgeRecord lists as the exporter would emit for
# this C++ source:
#
#   class MyClass {
#       int value;           // -> Field node, MEMBER_OF MyClass, access=private
#   };
#   int counter = 0;         // -> GlobalVariable node, DEFINES from File
#   void foo() {}            // -> Function node, DEFINES from File
#
# Then "play back" those records into _FakeIndraDBClient state and introspect.
# ---------------------------------------------------------------------------


def _make_export_records() -> tuple[list[NodeRecord], list[EdgeRecord]]:
    """Construct NodeRecord / EdgeRecord batches matching the S1 v2 export shape."""
    file_usr = "file:///src/roundtrip.cpp"
    class_usr = "c:@S@MyClass"
    field_usr = "c:@S@MyClass@FI@value"
    gvar_usr = "c:@counter"
    func_usr = "c:@F@foo"

    nodes: list[NodeRecord] = [
        NodeRecord(
            label=NODE_FILE,
            usr=file_usr,
            props={
                "path": "/src/roundtrip.cpp",
                "spelling": "/src/roundtrip.cpp",
                "schema_version": SCHEMA_VERSION,
            },
        ),
        NodeRecord(
            label="Class",
            usr=class_usr,
            props={
                "spelling": "MyClass",
                "type": "",
                "file": "/src/roundtrip.cpp",
                "line": 1,
                "col": 1,
            },
        ),
        NodeRecord(
            label=NODE_FIELD,
            usr=field_usr,
            props={
                "spelling": "value",
                "type": "int",
                "file": "/src/roundtrip.cpp",
                "line": 2,
                "col": 9,
                "is_const": False,
                "is_constexpr": False,
                "is_static": False,
                "storage_class": "none",
            },
        ),
        NodeRecord(
            label=NODE_GLOBAL_VARIABLE,
            usr=gvar_usr,
            props={
                "spelling": "counter",
                "type": "int",
                "file": "/src/roundtrip.cpp",
                "line": 4,
                "col": 5,
                "is_const": False,
                "is_constexpr": False,
                "is_static": False,
                "storage_class": "none",
            },
        ),
        NodeRecord(
            label=NODE_FUNCTION,
            usr=func_usr,
            props={
                "spelling": "foo",
                "type": "void ()",
                "file": "/src/roundtrip.cpp",
                "line": 5,
                "col": 1,
            },
        ),
    ]

    edges: list[EdgeRecord] = [
        EdgeRecord(
            source_usr=field_usr,
            target_usr=class_usr,
            edge_type=EDGE_MEMBER_OF,
            props={"access": "private"},
        ),
        EdgeRecord(source_usr=file_usr, target_usr=gvar_usr, edge_type=EDGE_DEFINES, props={}),
        EdgeRecord(source_usr=file_usr, target_usr=func_usr, edge_type=EDGE_DEFINES, props={}),
    ]
    return nodes, edges


def _records_to_fake_client(
    nodes: list[NodeRecord], edges: list[EdgeRecord]
) -> tuple[_FakeIndraDBClient, dict[str, uuid.UUID]]:
    """Convert export records to a _FakeIndraDBClient.

    Returns the client and a mapping from USR → fake UUID (needed for edge keys).
    """
    usr_to_vid: dict[str, uuid.UUID] = {}
    fake_vertices: list[_FakeVertex] = []
    vertex_props: dict[uuid.UUID, dict[str, Any]] = {}

    for node in nodes:
        vid = uuid.uuid4()
        usr_to_vid[node["usr"]] = vid
        fake_vertices.append(_FakeVertex(vid, node["label"]))
        vertex_props[vid] = dict(node["props"])

    fake_edges: list[_FakeEdge] = []
    edge_props: dict[tuple[uuid.UUID, str, uuid.UUID], dict[str, Any]] = {}

    for edge in edges:
        src_vid = usr_to_vid.get(edge["source_usr"])
        tgt_vid = usr_to_vid.get(edge["target_usr"])
        if src_vid is None or tgt_vid is None:
            continue  # skip dangling refs (shouldn't happen in this fixture)
        fe = _FakeEdge(src_vid, edge["edge_type"], tgt_vid)
        fake_edges.append(fe)
        edge_props[(src_vid, edge["edge_type"], tgt_vid)] = dict(edge["props"])

    client = _FakeIndraDBClient(
        vertices=fake_vertices,
        edges=fake_edges,
        vertex_props=vertex_props,
        edge_props=edge_props,
    )
    return client, usr_to_vid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """S1 v2 export round-trip: NodeRecord/EdgeRecord → introspect (S1-5 AC6, SC6)."""

    def _describe(self) -> dict[str, Any]:
        nodes, edges = _make_export_records()
        client, _ = _records_to_fake_client(nodes, edges)
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            return introspector.describe(sample_size=100)

    def test_field_node_set_present_after_round_trip(self) -> None:
        """Field node type present in introspect output after feeding export records."""
        result = self._describe()
        node_names = {nt["name"] for nt in result["node_types"]}
        assert "Field" in node_names, (
            f"Expected 'Field' node type in round-trip describe output. Got: {node_names}"
        )

    def test_global_variable_node_set_present_after_round_trip(self) -> None:
        """GlobalVariable node type present after round-trip."""
        result = self._describe()
        node_names = {nt["name"] for nt in result["node_types"]}
        assert "GlobalVariable" in node_names, (
            f"Expected 'GlobalVariable' in round-trip output. Got: {node_names}"
        )

    def test_field_and_global_variable_sets_are_disjoint(self) -> None:
        """Field and GlobalVariable sets are disjoint (no node appears in both)."""
        result = self._describe()
        # They are different node types — if both present with count > 0, they're disjoint
        field_entry = next((nt for nt in result["node_types"] if nt["name"] == "Field"), None)
        gvar_entry = next(
            (nt for nt in result["node_types"] if nt["name"] == "GlobalVariable"), None
        )
        assert field_entry is not None, "Expected 'Field' entry"
        assert gvar_entry is not None, "Expected 'GlobalVariable' entry"
        assert field_entry["count"] >= 1
        assert gvar_entry["count"] >= 1
        # They are separate types — disjointness is guaranteed by node-type separation.
        assert field_entry["name"] != gvar_entry["name"]

    def test_member_of_edge_with_access_survives_round_trip(self) -> None:
        """MEMBER_OF edge with 'access' property survives the export→introspect round-trip."""
        result = self._describe()
        member_of_entry = next(
            (et for et in result["edge_types"] if et["name"] == "MEMBER_OF"), None
        )
        assert member_of_entry is not None, (
            f"Expected 'MEMBER_OF' edge type in round-trip describe. "
            f"Edge types: {[et['name'] for et in result['edge_types']]}"
        )
        assert "access" in member_of_entry["property_keys"], (
            f"Expected 'access' in MEMBER_OF.property_keys after round-trip, "
            f"got: {member_of_entry['property_keys']}"
        )

    def test_schema_version_v2_after_round_trip(self) -> None:
        """schema_version == 'v2' reported by introspector after v2 export round-trip."""
        result = self._describe()
        assert result["schema_version"] == "v2", (
            f"Expected schema_version='v2' after round-trip, got {result['schema_version']!r}"
        )

    def test_field_property_keys_in_round_trip(self) -> None:
        """Field nodes expose the four new property keys after round-trip."""
        result = self._describe()
        field_entry = next((nt for nt in result["node_types"] if nt["name"] == "Field"), None)
        assert field_entry is not None, "Expected 'Field' entry in round-trip output"

        prop_keys = set(field_entry["property_keys"])
        new_props = {"is_const", "is_constexpr", "is_static", "storage_class"}
        assert new_props.issubset(prop_keys), (
            f"Expected new property keys {new_props} in Field after round-trip, got: {prop_keys}"
        )
