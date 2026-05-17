"""S4: Unit tests for IndraDbSchemaIntrospector and Neo4jSchemaIntrospector.

Tests cover:
  - Ordering (count desc, name asc) — AC-Q2-5
  - sample_size clamping — AC-Q2-4
  - Empty-graph (no vertices / edges)
  - Schema-version mismatch note (File node with different version)
  - Pre-v6 note (File node without schema_version)
  - No note when schema_version matches current
  - select_introspector dispatch
"""

from __future__ import annotations

import sys
import types
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from cpp_mcp.core.error_envelope import InvalidArgumentError
from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Minimal fake IndraDB for introspector tests
# ---------------------------------------------------------------------------


class _FakeNamedProp:
    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.value = value


class _FakeVertexProperties:
    """S5: matches the real VertexProperties shape (.vertex, .props)."""

    def __init__(self, vertex: _FakeVertex, props: list[_FakeNamedProp]) -> None:
        self.vertex = vertex
        self.props = props


class _FakeEdgeProperties:
    """S5: matches the real EdgeProperties shape (.edge, .props)."""

    def __init__(self, edge: _FakeEdge, props: list[_FakeNamedProp]) -> None:
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
    """Internal: marks a query as properties-mode."""

    def __init__(self, source: Any) -> None:
        self.source = source


class _FakeSpecificVertexQuery:
    """Supports .properties() chaining for property fetching.

    S5: accepts variadic vids to match real API; exposes .vids list.
    """

    def __init__(self, vid: uuid.UUID) -> None:
        self.vid = vid
        self.vids = [vid]

    def properties(self) -> _FakePropertiesQuery:
        return _FakePropertiesQuery(self)


class _FakeSpecificEdgeQuery:
    """Supports .properties() chaining for property fetching."""

    def __init__(self, edge: _FakeEdge) -> None:
        self.edge = edge

    def properties(self) -> _FakePropertiesQuery:
        return _FakePropertiesQuery(self)


class _FakeIndraDBClient:
    """Minimal fake IndraDB client for introspector tests.

    S5: get() returns VertexProperties/EdgeProperties objects for .properties() queries.
    """

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
        self._fail_on_ping = False

    def ping(self) -> None:
        if self._fail_on_ping:
            raise RuntimeError("fake IndraDB: ping failed")

    def close(self) -> None:
        pass

    def get(self, query: Any) -> list[list[Any]]:
        # Properties-mode: return VertexProperties / EdgeProperties objects.
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
            return [self._vertices]  # one batch
        if hasattr(query, "__class__") and query.__class__.__name__ == "AllEdgeQuery":
            return [self._edges]  # one batch
        return [[]]


# ---------------------------------------------------------------------------
# Fake indradb module for injection
# ---------------------------------------------------------------------------


class _FakeAllVertexQuery:
    """Module-level class so __name__ == 'AllVertexQuery' after rename."""


# Rename so class __name__ matches the real indradb class name used in get() checks.
_FakeAllVertexQuery.__name__ = "AllVertexQuery"
_FakeAllVertexQuery.__qualname__ = "AllVertexQuery"


class _FakeAllEdgeQuery:
    """Module-level class so __name__ == 'AllEdgeQuery' after rename."""


_FakeAllEdgeQuery.__name__ = "AllEdgeQuery"
_FakeAllEdgeQuery.__qualname__ = "AllEdgeQuery"


def _make_fake_indradb_module(client: _FakeIndraDBClient) -> types.ModuleType:
    """Build a fake ``indradb`` module that returns *client* from Client()."""
    mod = types.ModuleType("indradb")

    class _Client:
        def __init__(self, host: str = "localhost:27615", **kwargs: Any) -> None:
            pass

    # Override: always return the provided client instance.
    _Client.__new__ = lambda cls, *a, **kw: client  # type: ignore[method-assign]

    mod.AllVertexQuery = _FakeAllVertexQuery  # type: ignore[attr-defined]
    mod.AllEdgeQuery = _FakeAllEdgeQuery  # type: ignore[attr-defined]
    mod.Client = _Client  # type: ignore[attr-defined]
    mod.SpecificVertexQuery = _FakeSpecificVertexQuery  # type: ignore[attr-defined]
    mod.SpecificEdgeQuery = _FakeSpecificEdgeQuery  # type: ignore[attr-defined]
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vid() -> uuid.UUID:
    return uuid.uuid4()


def _build_introspector_with_client(client: _FakeIndraDBClient) -> Any:
    """Import IndraDbSchemaIntrospector and inject *client* into its connect call."""
    from cpp_mcp.graphdb.schema_introspector import IndraDbSchemaIntrospector

    introspector = IndraDbSchemaIntrospector()
    introspector._client = client  # inject directly
    return introspector


# ---------------------------------------------------------------------------
# Tests: ordering
# ---------------------------------------------------------------------------


class TestOrdering:
    """AC-Q2-5: node_types/edge_types sorted by (-count, name)."""

    def test_node_types_sorted_count_desc_then_name_asc(self) -> None:
        # 3 vertex types: B(5), A(5), C(2) → A(5), B(5), C(2)
        vids: dict[str, list[uuid.UUID]] = {
            "A": [_make_vid() for _ in range(5)],
            "B": [_make_vid() for _ in range(5)],
            "C": [_make_vid() for _ in range(2)],
        }
        vertices: list[_FakeVertex] = []
        for t, ids in vids.items():
            for vid in ids:
                vertices.append(_FakeVertex(vid, t))

        client = _FakeIndraDBClient(vertices=vertices)
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        names = [t["name"] for t in result["node_types"]]
        assert names == ["A", "B", "C"], f"Expected ['A','B','C'] got {names}"

    def test_edge_types_sorted_count_desc_then_name_asc(self) -> None:
        v1 = _make_vid()
        v2 = _make_vid()
        edges = [
            _FakeEdge(v1, "Z", v2),
            _FakeEdge(v1, "A", v2),
            _FakeEdge(v2, "A", v1),
        ]
        client = _FakeIndraDBClient(edges=edges)
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        names = [t["name"] for t in result["edge_types"]]
        assert names == ["A", "Z"], f"Expected ['A','Z'] got {names}"


# ---------------------------------------------------------------------------
# Tests: empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    """AC-Q2-2: empty node_types/edge_types + correct totals on empty graph."""

    def test_empty_graph_returns_zero_totals(self) -> None:
        client = _FakeIndraDBClient()
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=100)

        assert result["node_types"] == []
        assert result["edge_types"] == []
        assert result["totals"] == {"vertices": 0, "edges": 0}
        assert result["schema_version"] == SCHEMA_VERSION

    def test_empty_graph_has_two_static_notes(self) -> None:
        client = _FakeIndraDBClient()
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=100)

        assert len(result["notes"]) == 2
        assert any("sample" in n.lower() for n in result["notes"])
        assert any("live" in n.lower() for n in result["notes"])


# ---------------------------------------------------------------------------
# Tests: schema_version notes (ADR-24)
# ---------------------------------------------------------------------------


class TestSchemaVersionNotes:
    """ADR-24: schema-version mismatch and pre-v6 notes."""

    def _make_file_graph(
        self, schema_version_value: str | None
    ) -> tuple[_FakeIndraDBClient, types.ModuleType]:
        """Return a client with one File vertex, optionally stamped."""
        vid = _make_vid()
        vertex = _FakeVertex(vid, "File")
        props: dict[uuid.UUID, dict[str, Any]] = {}
        if schema_version_value is not None:
            props[vid] = {"schema_version": schema_version_value, "path": "/a.cpp"}
        else:
            props[vid] = {"path": "/a.cpp"}  # no schema_version key
        client = _FakeIndraDBClient(vertices=[vertex], vertex_props=props)
        fake_mod = _make_fake_indradb_module(client)
        return client, fake_mod

    def test_no_note_when_schema_version_matches(self) -> None:
        client, fake_mod = self._make_file_graph(SCHEMA_VERSION)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        version_notes = [n for n in result["notes"] if "schema_version" in n]
        assert not version_notes, f"Unexpected schema_version note: {version_notes}"

    def test_mismatch_note_when_old_schema_version(self) -> None:
        client, fake_mod = self._make_file_graph("v0")

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        mismatch_notes = [n for n in result["notes"] if "v0" in n]
        assert mismatch_notes, f"Expected mismatch note mentioning 'v0' in notes: {result['notes']}"
        assert SCHEMA_VERSION in mismatch_notes[0]

    def test_pre_v6_note_when_no_schema_version_stamp(self) -> None:
        client, fake_mod = self._make_file_graph(None)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        pre_v6_notes = [n for n in result["notes"] if "pre-v6" in n]
        assert pre_v6_notes, f"Expected pre-v6 note in notes: {result['notes']}"

    def test_no_version_note_when_no_file_vertices(self) -> None:
        vid = _make_vid()
        vertex = _FakeVertex(vid, "Function")
        client = _FakeIndraDBClient(vertices=[vertex])
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        version_notes = [n for n in result["notes"] if "schema_version" in n or "pre-v6" in n]
        assert not version_notes, f"Unexpected schema_version note: {version_notes}"


# ---------------------------------------------------------------------------
# Tests: result shape
# ---------------------------------------------------------------------------


class TestResultShape:
    """AC-Q2-2: result must have the expected keys and schema_version == SCHEMA_VERSION."""

    def test_result_has_required_keys(self) -> None:
        client = _FakeIndraDBClient()
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=100)

        for key in ("schema_version", "backend", "node_types", "edge_types", "totals", "notes"):
            assert key in result, f"Missing key {key!r} in result"

    def test_schema_version_field_equals_constant(self) -> None:
        client = _FakeIndraDBClient()
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=100)

        assert result["schema_version"] == SCHEMA_VERSION

    def test_backend_field_is_indradb(self) -> None:
        client = _FakeIndraDBClient()
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=100)

        assert result["backend"] == "indradb"


# ---------------------------------------------------------------------------
# Tests: select_introspector dispatch
# ---------------------------------------------------------------------------


class TestSelectIntrospector:
    """Scheme dispatch returns correct introspector type."""

    def test_bolt_uri_returns_neo4j_introspector(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import (
            Neo4jSchemaIntrospector,
            select_introspector,
        )

        intr = select_introspector("bolt://localhost:7687")
        assert isinstance(intr, Neo4jSchemaIntrospector)

    def test_neo4j_uri_returns_neo4j_introspector(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import (
            Neo4jSchemaIntrospector,
            select_introspector,
        )

        intr = select_introspector("neo4j://localhost:7687")
        assert isinstance(intr, Neo4jSchemaIntrospector)

    def test_indradb_uri_returns_indradb_introspector(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import (
            IndraDbSchemaIntrospector,
            select_introspector,
        )

        intr = select_introspector("indradb://localhost:27615")
        assert isinstance(intr, IndraDbSchemaIntrospector)

    def test_grpc_uri_returns_indradb_introspector(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import (
            IndraDbSchemaIntrospector,
            select_introspector,
        )

        intr = select_introspector("grpc://localhost:27615")
        assert isinstance(intr, IndraDbSchemaIntrospector)

    def test_unknown_scheme_raises_invalid_argument(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import select_introspector

        with pytest.raises(InvalidArgumentError, match="Unsupported db_uri scheme"):
            select_introspector("redis://localhost:6379")

    def test_empty_uri_raises_invalid_argument(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import select_introspector

        with pytest.raises(InvalidArgumentError):
            select_introspector("")

    def test_uri_without_scheme_raises_invalid_argument(self) -> None:
        from cpp_mcp.graphdb.schema_introspector import select_introspector

        with pytest.raises(InvalidArgumentError):
            select_introspector("localhost:7687")


# ---------------------------------------------------------------------------
# Tests: property key collection
# ---------------------------------------------------------------------------


class TestPropertyKeys:
    """Property keys are collected from sampled vertices/edges."""

    def test_vertex_property_keys_collected(self) -> None:
        vid = _make_vid()
        vertex = _FakeVertex(vid, "Function")
        props = {vid: {"name": "foo", "line": 1}}
        client = _FakeIndraDBClient(vertices=[vertex], vertex_props=props)
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        fn_type = next(t for t in result["node_types"] if t["name"] == "Function")
        assert "name" in fn_type["property_keys"]
        assert "line" in fn_type["property_keys"]

    def test_edge_property_keys_collected(self) -> None:
        v1, v2 = _make_vid(), _make_vid()
        edge = _FakeEdge(v1, "DEFINES", v2)
        edge_props = {(v1, "DEFINES", v2): {"weight": 1}}
        client = _FakeIndraDBClient(edges=[edge], edge_props=edge_props)
        fake_mod = _make_fake_indradb_module(client)

        with patch.dict(sys.modules, {"indradb": fake_mod}):
            introspector = _build_introspector_with_client(client)
            result = introspector.describe(sample_size=10)

        defines_type = next(t for t in result["edge_types"] if t["name"] == "DEFINES")
        assert "weight" in defines_type["property_keys"]
