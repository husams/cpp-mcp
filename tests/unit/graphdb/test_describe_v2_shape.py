"""P5: v2 describe_graph_schema shape tests.

Tests that a fresh v2 export surfaces the new schema through the introspector:
  - schema_version == "v2"
  - 'Field' and 'GlobalVariable' in node_types with the four new property keys
  - MEMBER_OF in edge_types with 'access' in property_keys

Satisfies AC: S1-4 AC1-AC4, SC1-SC4.
Design ref: §8, ADR-25 D1, D5.
"""

from __future__ import annotations

import sys
import types
import uuid
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Shared fake IndraDB infrastructure (local copy — same pattern as
# test_schema_introspector.py and test_describe_v1_compat.py)
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
# Fixture: v2 graph — fresh export shape with Field, GlobalVariable, MEMBER_OF.access
# ---------------------------------------------------------------------------

# v2 property keys emitted for Field and GlobalVariable nodes
_V2_FIELD_GLOBAL_PROP_KEYS = {
    "spelling",
    "type",
    "file",
    "line",
    "col",
    "is_const",
    "is_constexpr",
    "is_static",
    "storage_class",
}


def _make_v2_graph() -> tuple[_FakeIndraDBClient, types.ModuleType]:
    """Build an in-memory fake graph representing a v2 export.

    Contains:
      - 1 File node stamped with schema_version="v2"
      - 1 Field node (non-static class member) with all four new properties
      - 1 GlobalVariable node (VAR_DECL) with all four new properties
      - 1 Function node (unchanged from v1)
      - 1 MEMBER_OF edge from Field → Class with 'access'="private"
    """
    from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

    file_vid = uuid.uuid4()
    field_vid = uuid.uuid4()
    gvar_vid = uuid.uuid4()
    func_vid = uuid.uuid4()
    class_vid = uuid.uuid4()

    vertices = [
        _FakeVertex(file_vid, "File"),
        _FakeVertex(field_vid, "Field"),
        _FakeVertex(gvar_vid, "GlobalVariable"),
        _FakeVertex(func_vid, "Function"),
        _FakeVertex(class_vid, "Class"),
    ]
    member_of_edge = _FakeEdge(field_vid, "MEMBER_OF", class_vid)
    defines_edge = _FakeEdge(file_vid, "DEFINES", gvar_vid)
    edges = [member_of_edge, defines_edge]

    vertex_props: dict[uuid.UUID, dict[str, Any]] = {
        file_vid: {
            "path": "/src/v2.cpp",
            "spelling": "/src/v2.cpp",
            "schema_version": SCHEMA_VERSION,
        },
        field_vid: {
            "spelling": "value",
            "type": "int",
            "file": "/src/v2.cpp",
            "line": 5,
            "col": 5,
            "is_const": False,
            "is_constexpr": False,
            "is_static": False,
            "storage_class": "none",
        },
        gvar_vid: {
            "spelling": "counter",
            "type": "int",
            "file": "/src/v2.cpp",
            "line": 10,
            "col": 1,
            "is_const": False,
            "is_constexpr": False,
            "is_static": False,
            "storage_class": "none",
        },
        func_vid: {
            "spelling": "foo",
            "type": "void ()",
            "file": "/src/v2.cpp",
            "line": 12,
            "col": 1,
        },
        class_vid: {
            "spelling": "MyClass",
            "type": "",
            "file": "/src/v2.cpp",
            "line": 3,
            "col": 1,
        },
    }
    edge_props: dict[tuple[uuid.UUID, str, uuid.UUID], dict[str, Any]] = {
        (field_vid, "MEMBER_OF", class_vid): {"access": "private"},
        (file_vid, "DEFINES", gvar_vid): {},
    }

    client = _FakeIndraDBClient(
        vertices=vertices, edges=edges, vertex_props=vertex_props, edge_props=edge_props
    )
    return client, _make_fake_indradb_module(client)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDescribeV2Shape:
    """describe_graph_schema response shape for a v2 export (S1-4 AC1-AC4, SC1-SC4)."""

    def test_schema_version_is_v2(self) -> None:
        """Response schema_version == 'v2' for a v2 export (S1-4 AC1, SC1)."""
        from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        assert result["schema_version"] == "v2", (
            f"Expected schema_version='v2', got {result['schema_version']!r}"
        )
        assert result["schema_version"] == SCHEMA_VERSION

    def test_field_node_type_present(self) -> None:
        """'Field' appears in node_types for a v2 export (S1-4 AC2, SC2)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        node_names = {nt["name"] for nt in result["node_types"]}
        assert "Field" in node_names, (
            f"Expected 'Field' node type in v2 describe output. Got: {node_names}"
        )

    def test_global_variable_node_type_present(self) -> None:
        """'GlobalVariable' appears in node_types for a v2 export (S1-4 AC2, SC2)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        node_names = {nt["name"] for nt in result["node_types"]}
        assert "GlobalVariable" in node_names, (
            f"Expected 'GlobalVariable' node type in v2 describe output. Got: {node_names}"
        )

    def test_field_node_has_new_property_keys(self) -> None:
        """Field node_types entry includes the four new property keys (S1-4 AC3, SC3)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        field_entry = next((nt for nt in result["node_types"] if nt["name"] == "Field"), None)
        assert field_entry is not None, "Expected 'Field' entry in node_types"

        prop_keys = set(field_entry["property_keys"])
        new_props = {"is_const", "is_constexpr", "is_static", "storage_class"}
        assert new_props.issubset(prop_keys), (
            f"Expected new property keys {new_props} in Field.property_keys, got: {prop_keys}"
        )

    def test_global_variable_node_has_new_property_keys(self) -> None:
        """GlobalVariable node_types entry includes the four new property keys (S1-4 AC3, SC3)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        gvar_entry = next(
            (nt for nt in result["node_types"] if nt["name"] == "GlobalVariable"), None
        )
        assert gvar_entry is not None, "Expected 'GlobalVariable' entry in node_types"

        prop_keys = set(gvar_entry["property_keys"])
        new_props = {"is_const", "is_constexpr", "is_static", "storage_class"}
        assert new_props.issubset(prop_keys), (
            f"Expected new property keys {new_props} in GlobalVariable.property_keys, "
            f"got: {prop_keys}"
        )

    def test_member_of_edge_has_access_property_key(self) -> None:
        """MEMBER_OF edge_types entry includes 'access' in property_keys (S1-4 AC4, SC4)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        edge_names = {et["name"] for et in result["edge_types"]}
        assert "MEMBER_OF" in edge_names, f"Expected 'MEMBER_OF' in edge_types. Got: {edge_names}"

        member_of_entry = next(et for et in result["edge_types"] if et["name"] == "MEMBER_OF")
        assert "access" in member_of_entry["property_keys"], (
            f"Expected 'access' in MEMBER_OF.property_keys, got: {member_of_entry['property_keys']}"
        )

    def test_no_skew_note_for_matching_schema_version(self) -> None:
        """No skew note when stored schema_version matches code version (S1-4 AC1)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        notes: list[str] = result["notes"]
        # No schema_version skew note — stored and code version both "v2"
        skew_notes = [n for n in notes if "schema_version" in n and "v2" in n and "v1" in n]
        assert not skew_notes, f"Unexpected skew note for matching v2 schema: {skew_notes}"

    def test_result_has_required_keys(self) -> None:
        """Result dict has all required keys for a v2 graph (S1-4 AC1)."""
        client, fake_mod = _make_v2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        for key in ("schema_version", "backend", "node_types", "edge_types", "totals", "notes"):
            assert key in result, f"Missing required key {key!r} in v2 describe result"


# ---------------------------------------------------------------------------
# Fixture: v2-S2 graph — adds Type, Parameter, and the five new edges so the
# introspector autopickup test can assert their surface (SC-H-01..SC-H-03).
# ---------------------------------------------------------------------------


def _make_v2_s2_graph() -> tuple[_FakeIndraDBClient, types.ModuleType]:
    """Build an in-memory fake graph representing a v2 S2 export.

    Contains:
      - 1 File node stamped with schema_version="v2"
      - 1 Function node
      - 1 Parameter node
      - 1 Type node (return type "int")
      - 1 Type node (parameter type "const std::string &")
      - RETURNS edge: Function → int-Type
      - HAS_PARAM edge: Function → Parameter (index=0)
      - OF_TYPE edge: Parameter → string-ref-Type
      - POINTS_TO edge: int*-Type → int-Type  (pointer chain representative)
      - REFERS_TO edge: string-ref-Type → string-Type (ref chain representative)

    All five S2 edge types must appear so describe autopickup surfaces them.
    """
    from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

    file_vid = uuid.uuid4()
    func_vid = uuid.uuid4()
    param_vid = uuid.uuid4()
    type_int_vid = uuid.uuid4()
    type_int_ptr_vid = uuid.uuid4()
    type_str_ref_vid = uuid.uuid4()
    type_str_vid = uuid.uuid4()

    vertices = [
        _FakeVertex(file_vid, "File"),
        _FakeVertex(func_vid, "Function"),
        _FakeVertex(param_vid, "Parameter"),
        _FakeVertex(type_int_vid, "Type"),
        _FakeVertex(type_int_ptr_vid, "Type"),
        _FakeVertex(type_str_ref_vid, "Type"),
        _FakeVertex(type_str_vid, "Type"),
    ]

    returns_edge = _FakeEdge(func_vid, "RETURNS", type_int_vid)
    has_param_edge = _FakeEdge(func_vid, "HAS_PARAM", param_vid)
    of_type_edge = _FakeEdge(param_vid, "OF_TYPE", type_str_ref_vid)
    points_to_edge = _FakeEdge(type_int_ptr_vid, "POINTS_TO", type_int_vid)
    refers_to_edge = _FakeEdge(type_str_ref_vid, "REFERS_TO", type_str_vid)

    edges = [returns_edge, has_param_edge, of_type_edge, points_to_edge, refers_to_edge]

    vertex_props: dict[uuid.UUID, dict[str, Any]] = {
        file_vid: {
            "path": "/src/s2.cpp",
            "spelling": "/src/s2.cpp",
            "schema_version": SCHEMA_VERSION,
        },
        func_vid: {
            "spelling": "foo",
            "type": "int (const std::string &)",
            "file": "/src/s2.cpp",
            "line": 1,
            "col": 1,
            "signature": "foo(const std::string &)",
            "is_constexpr": False,
            "is_noexcept": False,
            "is_deleted": False,
            "is_defaulted": False,
            "cv_qualifiers": "",
            "ref_qualifier": "",
        },
        param_vid: {
            "spelling": "s",
            "name": "s",
            "index": 0,
            "default_value": "",
            "file": "/src/s2.cpp",
            "line": 1,
            "col": 10,
        },
        type_int_vid: {
            "spelling": "int",
            "is_const": False,
            "is_volatile": False,
            "is_pointer": False,
            "is_reference": False,
            "is_lvalue_reference": False,
            "is_rvalue_reference": False,
            "kind": "INT",
        },
        type_int_ptr_vid: {
            "spelling": "int *",
            "is_const": False,
            "is_volatile": False,
            "is_pointer": True,
            "is_reference": False,
            "is_lvalue_reference": False,
            "is_rvalue_reference": False,
            "kind": "POINTER",
        },
        type_str_ref_vid: {
            "spelling": "const std::string &",
            "is_const": False,
            "is_volatile": False,
            "is_pointer": False,
            "is_reference": True,
            "is_lvalue_reference": True,
            "is_rvalue_reference": False,
            "kind": "LVALUEREFERENCE",
        },
        type_str_vid: {
            "spelling": "const std::string",
            "is_const": True,
            "is_volatile": False,
            "is_pointer": False,
            "is_reference": False,
            "is_lvalue_reference": False,
            "is_rvalue_reference": False,
            "kind": "RECORD",
        },
    }

    edge_props: dict[tuple[uuid.UUID, str, uuid.UUID], dict[str, Any]] = {
        (func_vid, "RETURNS", type_int_vid): {},
        (func_vid, "HAS_PARAM", param_vid): {"index": 0},
        (param_vid, "OF_TYPE", type_str_ref_vid): {},
        (type_int_ptr_vid, "POINTS_TO", type_int_vid): {},
        (type_str_ref_vid, "REFERS_TO", type_str_vid): {},
    }

    client = _FakeIndraDBClient(
        vertices=vertices, edges=edges, vertex_props=vertex_props, edge_props=edge_props
    )
    return client, _make_fake_indradb_module(client)


# ---------------------------------------------------------------------------
# Tests: S2 additions autopickup (SC-H-01..SC-H-03)
# ---------------------------------------------------------------------------


class TestDescribeS2Additions:
    """describe_graph_schema autopickup surfaces S2 additions (SC-H-01..SC-H-03).

    The introspector is read-only and surfaces labels live — no code changes
    needed.  These tests verify that a graph seeded with Type, Parameter, and the
    five new S2 edge types is reported correctly by the introspector.

    ACs: S2-H.AC1 (SC-H-01), S2-H.AC2 (SC-H-02), S2-H.AC3 (SC-H-03).
    Design ref: §4, §8 (introspector autopickup).
    ADR-26 D9: no code change to introspector; labels surface automatically.
    """

    def test_sc_h_01_type_and_parameter_node_types_present(self) -> None:
        """SC-H-01: describe surfaces 'Type' and 'Parameter' node types (S2-H.AC1)."""
        client, fake_mod = _make_v2_s2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        node_names = {nt["name"] for nt in result["node_types"]}
        assert "Type" in node_names, (
            f"Expected 'Type' node type in S2 describe output. Got: {node_names}"
        )
        assert "Parameter" in node_names, (
            f"Expected 'Parameter' node type in S2 describe output. Got: {node_names}"
        )

    def test_sc_h_02_five_new_edge_types_present(self) -> None:
        """SC-H-02: describe surfaces all five new S2 edge types (S2-H.AC2).

        New edge types: RETURNS, HAS_PARAM, OF_TYPE, POINTS_TO, REFERS_TO.
        """
        client, fake_mod = _make_v2_s2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        edge_names = {et["name"] for et in result["edge_types"]}
        for new_edge in ("RETURNS", "HAS_PARAM", "OF_TYPE", "POINTS_TO", "REFERS_TO"):
            assert new_edge in edge_names, (
                f"Expected S2 edge type {new_edge!r} in describe output. Got: {edge_names}"
            )

    def test_sc_h_03_schema_version_still_v2(self) -> None:
        """SC-H-03: describe_graph_schema reports schema_version='v2' (S2-H.AC3)."""
        from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

        client, fake_mod = _make_v2_s2_graph()

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)

        assert result["schema_version"] == "v2", (
            f"Expected schema_version='v2' after S2, got {result['schema_version']!r}"
        )
        assert result["schema_version"] == SCHEMA_VERSION

    def test_sc_h_05_v2_s1_graph_no_type_parameter_no_error(self) -> None:
        """SC-H-05: v2-from-S1 graph with no Type/Parameter nodes does not error (S2-H.AC5).

        When an S1-exported graph (schema_version='v2', but no Type or Parameter
        nodes) is inspected after S2 ships, the introspector must not raise an
        error.  It reports zero counts for Type and Parameter.
        """
        client, fake_mod = _make_v2_graph()  # S1 graph: no Type/Parameter vertices

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector(client)
            result = introspector.describe(sample_size=10)  # must not raise

        assert isinstance(result, dict), "describe must return a dict even for S1-graph"
        node_names = {nt["name"] for nt in result["node_types"]}
        # Type and Parameter are absent in an S1 graph — zero-count or absent is fine.
        for absent_label in ("Type", "Parameter"):
            entry = next((nt for nt in result["node_types"] if nt["name"] == absent_label), None)
            if entry is not None:
                assert entry["count"] == 0, (
                    f"S1-graph should show count=0 for {absent_label!r}, got {entry['count']}"
                )
        # The original S1 labels must still appear
        assert "Field" in node_names, "Field should still appear in S1-graph describe"
        assert "GlobalVariable" in node_names, (
            "GlobalVariable should still appear in S1-graph describe"
        )
