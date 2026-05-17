"""P2 — POINTS_TO and REFERS_TO type-shape edges (SC-B-01..SC-B-05).

Covers ADR-26 D4: depth-1 per edge, chained recursion; int** produces a
2-edge chain (int** →POINTS_TO→ int* →POINTS_TO→ int).

Fake type objects are built with MagicMock and real clang.cindex.TypeKind
so that the isinstance-like comparisons inside _get_or_create_type work.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord
from cpp_mcp.graphdb.exporter import _get_or_create_type
from cpp_mcp.graphdb.schema import EDGE_POINTS_TO, EDGE_REFERS_TO, NODE_TYPE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_type(
    *,
    spelling: str,
    kind_name: str,
    is_const: bool = False,
    pointee: Any = None,
) -> Any:
    """Build a fake libclang Type with real TypeKind enum values."""
    from clang.cindex import TypeKind  # type: ignore[import-untyped]

    t = MagicMock()
    t.spelling = spelling
    t.kind = getattr(TypeKind, kind_name)
    t.is_const_qualified.return_value = is_const
    t.is_volatile_qualified.return_value = False

    if pointee is not None:
        t.get_pointee.return_value = pointee
    else:
        empty = MagicMock()
        empty.spelling = ""
        t.get_pointee.return_value = empty

    return t


def _run(t: Any) -> tuple[list[NodeRecord], list[EdgeRecord]]:
    """Call _get_or_create_type and return resulting nodes and edges."""
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    seen: set[str] = set()
    _get_or_create_type(t, nodes, edges, seen)
    return nodes, edges


def _edges_of_type(edges: list[EdgeRecord], edge_type: str) -> list[EdgeRecord]:
    return [e for e in edges if e["edge_type"] == edge_type]


def _spelling_for_usr(nodes: list[NodeRecord], usr: str) -> str:
    matches = [n for n in nodes if n["usr"] == usr]
    assert matches, f"No node for USR {usr!r}"
    return matches[0]["props"]["spelling"]


# ---------------------------------------------------------------------------
# SC-B-01 — Pointer Type has exactly one outgoing POINTS_TO edge
# ---------------------------------------------------------------------------


class TestPointsToEdge:
    """SC-B-01: Pointer Type has exactly one outgoing POINTS_TO edge."""

    def test_int_pointer_has_one_points_to_edge(self) -> None:
        int_t = _make_type(spelling="int", kind_name="INT")
        ptr_t = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t)

        nodes, edges = _run(ptr_t)

        pts_edges = _edges_of_type(edges, EDGE_POINTS_TO)
        assert len(pts_edges) == 1, f"Expected exactly 1 POINTS_TO edge; got {len(pts_edges)}"

        # source must be int*, target must be int
        e = pts_edges[0]
        assert _spelling_for_usr(nodes, e["source_usr"]) == "int *"
        assert _spelling_for_usr(nodes, e["target_usr"]) == "int"

    def test_no_refers_to_on_pointer(self) -> None:
        int_t = _make_type(spelling="int", kind_name="INT")
        ptr_t = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t)
        _, edges = _run(ptr_t)
        assert _edges_of_type(edges, EDGE_REFERS_TO) == []


# ---------------------------------------------------------------------------
# SC-B-02 — lvalue reference Type has exactly one outgoing REFERS_TO edge
# ---------------------------------------------------------------------------


class TestRefersToEdgeLvalue:
    """SC-B-02: Reference Type has exactly one outgoing REFERS_TO edge."""

    def test_const_string_ref_has_one_refers_to_edge(self) -> None:
        referent = _make_type(spelling="const std::string", kind_name="RECORD", is_const=True)
        ref_t = _make_type(
            spelling="const std::string &",
            kind_name="LVALUEREFERENCE",
            pointee=referent,
        )

        nodes, edges = _run(ref_t)

        ref_edges = _edges_of_type(edges, EDGE_REFERS_TO)
        assert len(ref_edges) == 1, f"Expected 1 REFERS_TO edge; got {len(ref_edges)}"

        e = ref_edges[0]
        assert _spelling_for_usr(nodes, e["source_usr"]) == "const std::string &"
        assert _spelling_for_usr(nodes, e["target_usr"]) == "const std::string"

    def test_no_points_to_on_reference(self) -> None:
        referent = _make_type(spelling="const std::string", kind_name="RECORD")
        ref_t = _make_type(
            spelling="const std::string &",
            kind_name="LVALUEREFERENCE",
            pointee=referent,
        )
        _, edges = _run(ref_t)
        assert _edges_of_type(edges, EDGE_POINTS_TO) == []


# ---------------------------------------------------------------------------
# SC-B-03 — rvalue reference Type has exactly one outgoing REFERS_TO edge
# ---------------------------------------------------------------------------


class TestRefersToEdgeRvalue:
    """SC-B-03: Rvalue reference Type has exactly one outgoing REFERS_TO edge."""

    def test_rvalue_ref_has_one_refers_to_edge(self) -> None:
        referent = _make_type(spelling="int", kind_name="INT")
        rref_t = _make_type(
            spelling="int &&",
            kind_name="RVALUEREFERENCE",
            pointee=referent,
        )

        nodes, edges = _run(rref_t)

        ref_edges = _edges_of_type(edges, EDGE_REFERS_TO)
        assert len(ref_edges) == 1, f"Expected 1 REFERS_TO edge; got {len(ref_edges)}"

        e = ref_edges[0]
        assert _spelling_for_usr(nodes, e["source_usr"]) == "int &&"
        assert _spelling_for_usr(nodes, e["target_usr"]) == "int"


# ---------------------------------------------------------------------------
# SC-B-04 — Non-pointer, non-reference Type has zero POINTS_TO / REFERS_TO
# ---------------------------------------------------------------------------


class TestNoEdgesForPlainType:
    """SC-B-04: Non-pointer non-reference Type has zero outgoing POINTS_TO or REFERS_TO edges."""

    @pytest.mark.parametrize(
        "spelling,kind_name",
        [
            ("int", "INT"),
            ("double", "DOUBLE"),
            ("void", "VOID"),
        ],
    )
    def test_plain_type_has_no_shape_edges(self, spelling: str, kind_name: str) -> None:
        t = _make_type(spelling=spelling, kind_name=kind_name)
        _, edges = _run(t)

        assert _edges_of_type(edges, EDGE_POINTS_TO) == [], (
            f"'{spelling}' must have zero POINTS_TO edges"
        )
        assert _edges_of_type(edges, EDGE_REFERS_TO) == [], (
            f"'{spelling}' must have zero REFERS_TO edges"
        )


# ---------------------------------------------------------------------------
# SC-B-05 — int** chain: 3 Type nodes, 2 chained POINTS_TO edges (ADR-26 D4)
# ---------------------------------------------------------------------------


class TestDoublePointerChain:
    """SC-B-05: int** produces 3 Type nodes and 2 chained POINTS_TO edges (ADR-26 D4).

    Chain: int** →POINTS_TO→ int* →POINTS_TO→ int
    This verifies that recursion naturally extends through pointer levels.
    """

    def test_double_pointer_chain_three_nodes(self) -> None:
        int_t = _make_type(spelling="int", kind_name="INT")
        int_ptr_t = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t)
        int_ptr_ptr_t = _make_type(spelling="int **", kind_name="POINTER", pointee=int_ptr_t)

        nodes, _edges = _run(int_ptr_ptr_t)

        type_nodes = [n for n in nodes if n["label"] == NODE_TYPE]
        spellings = {n["props"]["spelling"] for n in type_nodes}
        assert "int **" in spellings, "int** Type node must exist"
        assert "int *" in spellings, "int* Type node must exist"
        assert "int" in spellings, "int Type node must exist"

    def test_double_pointer_chain_two_points_to_edges(self) -> None:
        int_t = _make_type(spelling="int", kind_name="INT")
        int_ptr_t = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t)
        int_ptr_ptr_t = _make_type(spelling="int **", kind_name="POINTER", pointee=int_ptr_t)

        _nodes, edges = _run(int_ptr_ptr_t)

        pts_edges = _edges_of_type(edges, EDGE_POINTS_TO)
        assert len(pts_edges) == 2, (
            f"int** must produce exactly 2 POINTS_TO edges; got {len(pts_edges)}"
        )

    def test_double_pointer_chain_topology(self) -> None:
        """int** →POINTS_TO→ int* →POINTS_TO→ int (in that direction)."""
        int_t = _make_type(spelling="int", kind_name="INT")
        int_ptr_t = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t)
        int_ptr_ptr_t = _make_type(spelling="int **", kind_name="POINTER", pointee=int_ptr_t)

        nodes, edges = _run(int_ptr_ptr_t)

        pts_edges = _edges_of_type(edges, EDGE_POINTS_TO)

        # Build source→target spelling map
        edge_pairs = {
            (_spelling_for_usr(nodes, e["source_usr"]), _spelling_for_usr(nodes, e["target_usr"]))
            for e in pts_edges
        }

        assert ("int **", "int *") in edge_pairs, "int** must have POINTS_TO edge to int*"
        assert ("int *", "int") in edge_pairs, "int* must have POINTS_TO edge to int"

    def test_double_pointer_dedup_within_run(self) -> None:
        """Same spelling encountered twice within one export run produces one node (ADR-26 D3)."""
        int_t1 = _make_type(spelling="int", kind_name="INT")
        int_ptr_t = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t1)
        int_ptr_ptr_t = _make_type(spelling="int **", kind_name="POINTER", pointee=int_ptr_t)

        # Add a second reference to int * (simulates two params of same type)
        int_t2 = _make_type(spelling="int", kind_name="INT")
        int_ptr_t2 = _make_type(spelling="int *", kind_name="POINTER", pointee=int_t2)

        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()

        _get_or_create_type(int_ptr_ptr_t, nodes, edges, seen)
        _get_or_create_type(int_ptr_t2, nodes, edges, seen)  # already in seen

        int_ptr_nodes = [n for n in nodes if n["props"]["spelling"] == "int *"]
        assert len(int_ptr_nodes) == 1, "Dedup must prevent duplicate 'int *' Type node"
