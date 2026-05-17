"""P2: FIELD_DECL classifier — Field vs GlobalVariable split.

Covers:
  - Non-static class data member → Field (S1-1 AC1, SC1, ADR-25 D1).
  - Static class data member → GlobalVariable (S1-1 AC3, SC3, ADR-25 D7).
  - Anonymous struct/union member → Field (ADR-25 D3, minimal coverage).
  - PARM_DECL → Parameter (ADR-26 D9; replaces ADR-25 D2 transitional Variable).

Libclang capability probe (F-3 per ADR-25):
  ``Cursor.is_static_member`` is NOT available on the pinned libclang version
  (clang-python binding, verified during P2 implementation). All static-member
  detection uses the ``StorageClass.STATIC`` fallback path in ``_is_static_member``.

Note on USR-scoped assertions (ADR-26 D9):
  P3 wires Parameter emission via ``cursor.get_arguments()`` in the parent function
  block with the synthetic USR ``<fn-usr>#param:<i>``.  Tests must assert on the
  synthetic USR, not on the libclang-native PARM_DECL USR (which is now skipped by
  the PARM_DECL guard in generic recursion).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_FIELD, NODE_GLOBAL_VARIABLE, NODE_PARAMETER, NODE_VARIABLE

# ---------------------------------------------------------------------------
# Fake cursor / TU helpers
# ---------------------------------------------------------------------------


def _make_field_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    storage_class: Any = None,
    children: list[Any] | None = None,
) -> Any:
    """Build a fake FIELD_DECL cursor.

    *storage_class*: if None defaults to a mock that does not equal STATIC.
    """
    from clang.cindex import StorageClass  # type: ignore[import-untyped]

    cursor = MagicMock()
    cursor.kind.name = "FIELD_DECL"
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = True
    cursor.type.spelling = "int"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 5
    cursor.location.column = 5
    cursor.get_children.return_value = children or []
    cursor.referenced = None
    # is_static_member is absent on pinned libclang — always use fallback.
    # Explicitly remove the attribute so _is_static_member uses storage_class.
    del cursor.is_static_member
    cursor.storage_class = storage_class if storage_class is not None else StorageClass.NONE
    return cursor


def _make_parm_cursor(*, usr: str, spelling: str, file_name: str) -> Any:
    """Build a fake PARM_DECL cursor (Parameter per ADR-26 D9).

    get_arguments() returns [] so nested params don't recurse.
    get_tokens() returns [] so _render_default_value yields "".
    """
    cursor = MagicMock()
    cursor.kind.name = "PARM_DECL"
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = False
    cursor.type.spelling = "int"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 2
    cursor.location.column = 14
    cursor.get_children.return_value = []
    cursor.get_tokens.return_value = []
    cursor.referenced = None
    return cursor


def _make_class_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    children: list[Any],
    kind_name: str = "CLASS_DECL",
) -> Any:
    """Build a fake CLASS_DECL/STRUCT_DECL cursor containing *children*."""
    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = True
    cursor.type.spelling = spelling
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = children
    cursor.referenced = None
    return cursor


def _make_function_cursor(*, usr: str, spelling: str, file_name: str, params: list[Any]) -> Any:
    """Build a fake FUNCTION_DECL cursor containing *params* as get_arguments().

    P3 (ADR-26 D9): Parameter nodes are emitted via ``cursor.get_arguments()``
    in the explicit function-block loop, not via generic child recursion.
    ``get_children`` returns an empty list so PARM_DECL cursors are not visited
    by the generic recursion path (the PARM_DECL guard returns early anyway).
    """
    cursor = MagicMock()
    cursor.kind.name = "FUNCTION_DECL"
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = True
    cursor.type.spelling = "void (int)"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.get_arguments.return_value = params
    cursor.referenced = None
    return cursor


def _make_tu(file_path: Path, top_level_cursors: list[Any]) -> Any:
    """Build a fake TranslationUnit whose root children are *top_level_cursors*."""
    tu = MagicMock()
    tu.diagnostics = []
    tu.cursor.get_children.return_value = top_level_cursors
    tu.cursor.location.file = None
    tu.cursor.kind.name = "TRANSLATION_UNIT"
    tu.cursor.get_usr.return_value = ""
    tu.cursor.spelling = ""
    tu.cursor.is_definition.return_value = False
    return tu


# ---------------------------------------------------------------------------
# Tests — non-static class data member → Field  (S1-1 AC1, SC1)
# ---------------------------------------------------------------------------


class TestNonStaticFieldDecl:
    def test_non_static_member_produces_field_node(self, tmp_path: Path) -> None:
        """Non-static int x in class → one Field node for that USR. (S1-1 AC1, SC1)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field = _make_field_cursor(
            usr="c:@S@Foo@FI@x",
            spelling="x",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        cls = _make_class_cursor(
            usr="c:@S@Foo",
            spelling="Foo",
            file_name=fname,
            children=[field],
        )
        tu = _make_tu(source, [cls])

        nodes, _ = extract_nodes_and_edges(tu, source)

        field_usr = "c:@S@Foo@FI@x"
        nodes_for_usr = [n for n in nodes if n["usr"] == field_usr]
        assert len(nodes_for_usr) == 1, f"Expected exactly 1 node for USR {field_usr!r}"
        assert nodes_for_usr[0]["label"] == NODE_FIELD, (
            f"Expected label {NODE_FIELD!r}, got {nodes_for_usr[0]['label']!r}"
        )

    def test_non_static_member_not_classified_as_global_variable(self, tmp_path: Path) -> None:
        """Non-static member USR must not appear as GlobalVariable. (S1-1 AC1, D7)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field_usr = "c:@S@Bar@FI@value"
        field = _make_field_cursor(
            usr=field_usr,
            spelling="value",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        cls = _make_class_cursor(
            usr="c:@S@Bar",
            spelling="Bar",
            file_name=fname,
            children=[field],
        )
        tu = _make_tu(source, [cls])

        nodes, _ = extract_nodes_and_edges(tu, source)

        global_var_for_usr = [
            n for n in nodes if n["usr"] == field_usr and n["label"] == NODE_GLOBAL_VARIABLE
        ]
        assert not global_var_for_usr, (
            f"Non-static field USR {field_usr!r} must not produce GlobalVariable"
        )


# ---------------------------------------------------------------------------
# Tests — static class data member → GlobalVariable  (S1-1 AC3, SC3, ADR-25 D7)
# ---------------------------------------------------------------------------


class TestStaticMemberDecl:
    def test_static_member_produces_global_variable_node(self, tmp_path: Path) -> None:
        """static int count in class → GlobalVariable, no Field for that USR. (S1-1 AC3, SC3, D7)

        Note: is_static_member() is absent on pinned libclang; StorageClass.STATIC
        fallback is exercised (F-3 per ADR-25, documented in implementation-notes.md).
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        static_usr = "c:@S@Counter@FI@count"
        static_field = _make_field_cursor(
            usr=static_usr,
            spelling="count",
            file_name=fname,
            storage_class=StorageClass.STATIC,
        )
        cls = _make_class_cursor(
            usr="c:@S@Counter",
            spelling="Counter",
            file_name=fname,
            children=[static_field],
        )
        tu = _make_tu(source, [cls])

        nodes, _ = extract_nodes_and_edges(tu, source)

        nodes_for_usr = [n for n in nodes if n["usr"] == static_usr]
        assert len(nodes_for_usr) == 1, f"Expected exactly 1 node for USR {static_usr!r}"
        assert nodes_for_usr[0]["label"] == NODE_GLOBAL_VARIABLE, (
            f"Static member must be GlobalVariable, got {nodes_for_usr[0]['label']!r} (D7)"
        )

    def test_static_member_not_classified_as_field(self, tmp_path: Path) -> None:
        """Static member USR must not appear as Field (D7 invariant). (S1-1 AC3, D7)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        static_usr = "c:@S@Widget@FI@instances"
        static_field = _make_field_cursor(
            usr=static_usr,
            spelling="instances",
            file_name=fname,
            storage_class=StorageClass.STATIC,
        )
        cls = _make_class_cursor(
            usr="c:@S@Widget",
            spelling="Widget",
            file_name=fname,
            children=[static_field],
        )
        tu = _make_tu(source, [cls])

        nodes, _ = extract_nodes_and_edges(tu, source)

        field_for_usr = [n for n in nodes if n["usr"] == static_usr and n["label"] == NODE_FIELD]
        assert not field_for_usr, (
            f"Static member USR {static_usr!r} must never produce a Field node (D7)"
        )


# ---------------------------------------------------------------------------
# Tests — anonymous struct/union member → Field  (ADR-25 D3, minimal coverage)
# ---------------------------------------------------------------------------


class TestAnonymousStructMember:
    def test_anonymous_struct_member_produces_field(self, tmp_path: Path) -> None:
        """Anonymous struct/union member → Field, MEMBER_OF nearest named class. (ADR-25 D3)

        libclang exposes anonymous-record members as FIELD_DECL cursors in the
        enclosing scope. With StorageClass.NONE they classify as Field.
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "anon.cpp"
        source.write_text("")
        fname = str(source)

        # Simulate: struct Outer { union { int x; }; };
        # libclang surfaces the anonymous union member as a FIELD_DECL in Outer.
        anon_usr = "c:@S@Outer@FI@x"
        anon_field = _make_field_cursor(
            usr=anon_usr,
            spelling="x",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        outer = _make_class_cursor(
            usr="c:@S@Outer",
            spelling="Outer",
            file_name=fname,
            kind_name="STRUCT_DECL",
            children=[anon_field],
        )
        tu = _make_tu(source, [outer])

        nodes, _ = extract_nodes_and_edges(tu, source)

        nodes_for_usr = [n for n in nodes if n["usr"] == anon_usr]
        assert nodes_for_usr, f"Expected a node for anonymous member USR {anon_usr!r}"
        assert nodes_for_usr[0]["label"] == NODE_FIELD, (
            f"Anonymous struct member must be Field, got {nodes_for_usr[0]['label']!r} (D3)"
        )


# ---------------------------------------------------------------------------
# Tests — PARM_DECL → Parameter (ADR-26 D9; replaces ADR-25 D2 transitional)
# ---------------------------------------------------------------------------


class TestParmDeclInvariant:
    def test_parm_decl_produces_parameter(self, tmp_path: Path) -> None:
        """PARM_DECL emits Parameter (not Variable) in S2 (ADR-26 D9).

        Parameter nodes are emitted with the synthetic USR ``<fn-usr>#param:<i>``
        via the get_arguments() loop, not via the libclang native PARM_DECL USR.
        """
        source = tmp_path / "func.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@doWork#I#"
        param = _make_parm_cursor(usr="c:func.cpp@10@F@doWork#I#@x", spelling="x", file_name=fname)
        func = _make_function_cursor(
            usr=fn_usr,
            spelling="doWork",
            file_name=fname,
            params=[param],
        )
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        # Synthetic USR for first parameter: <fn-usr>#param:0
        synthetic_usr = f"{fn_usr}#param:0"
        param_nodes = [n for n in nodes if n["usr"] == synthetic_usr]
        assert param_nodes, (
            f"Expected a Parameter node with synthetic USR {synthetic_usr!r} (ADR-26 D9)"
        )
        assert param_nodes[0]["label"] == NODE_PARAMETER, (
            f"PARM_DECL must emit Parameter in S2, got {param_nodes[0]['label']!r} (ADR-26 D9)"
        )

    @pytest.mark.parametrize(
        "bad_label",
        [NODE_FIELD, NODE_GLOBAL_VARIABLE, NODE_VARIABLE],
    )
    def test_parm_decl_not_field_global_variable_or_variable(
        self, tmp_path: Path, bad_label: str
    ) -> None:
        """PARM_DECL must not emit Field, GlobalVariable, or Variable. (ADR-26 D9)

        Variable is now explicitly prohibited: PARM_DECL must emit Parameter.
        """
        source = tmp_path / "func.cpp"
        source.write_text("")
        fname = str(source)

        param = _make_parm_cursor(usr="c:func.cpp@10@F@helper#I#@n", spelling="n", file_name=fname)
        func = _make_function_cursor(
            usr="c:@F@helper#I#",
            spelling="helper",
            file_name=fname,
            params=[param],
        )
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        bad_nodes = [n for n in nodes if n["label"] == bad_label]
        assert not bad_nodes, (
            f"PARM_DECL must not produce {bad_label!r} nodes (ADR-26 D9); found: {bad_nodes}"
        )


# ---------------------------------------------------------------------------
# P4 (SC-D-03) — Field → OF_TYPE → Type
# ---------------------------------------------------------------------------


class TestFieldOfTypeEdge:
    """SC-D-03: Field node has exactly one outgoing OF_TYPE edge to its Type node.

    ADR-26 §3.4: OF_TYPE is emitted inside the seen_usrs guard in _walk_cursor,
    once per Field node creation.
    """

    def test_field_has_of_type_edge(self, tmp_path: Path) -> None:
        """double x in class Point → 1 OF_TYPE edge from the Field to Type{spelling="double"}."""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        from cpp_mcp.graphdb.schema import EDGE_OF_TYPE, NODE_TYPE

        source = tmp_path / "point.cpp"
        source.write_text("")
        fname = str(source)

        field_x = _make_field_cursor(
            usr="c:@S@Point@FI@x",
            spelling="x",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        field_x.type.spelling = "double"

        field_y = _make_field_cursor(
            usr="c:@S@Point@FI@y",
            spelling="y",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        field_y.type.spelling = "double"

        cls = _make_class_cursor(
            usr="c:@S@Point",
            spelling="Point",
            file_name=fname,
            children=[field_x, field_y],
        )
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        field_usrs = {"c:@S@Point@FI@x", "c:@S@Point@FI@y"}
        for field_usr in field_usrs:
            of_edges = [
                e for e in edges if e["edge_type"] == EDGE_OF_TYPE and e["source_usr"] == field_usr
            ]
            assert len(of_edges) == 1, (
                f"Field {field_usr!r} must have exactly 1 OF_TYPE edge, got {len(of_edges)}"
            )
            type_node = next((n for n in nodes if n["usr"] == of_edges[0]["target_usr"]), None)
            assert type_node is not None, f"No Type node at OF_TYPE target for {field_usr!r}"
            assert type_node["label"] == NODE_TYPE, (
                f"OF_TYPE target must be Type, got {type_node['label']!r}"
            )
            assert type_node["props"]["spelling"] == "double", (
                f"Expected 'double', got {type_node['props']['spelling']!r}"
            )

    def test_field_of_type_no_duplicate_edges(self, tmp_path: Path) -> None:
        """OF_TYPE is emitted exactly once per Field (dedup via seen_usrs guard)."""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        from cpp_mcp.graphdb.schema import EDGE_OF_TYPE

        source = tmp_path / "dedup_field.cpp"
        source.write_text("")
        fname = str(source)

        field = _make_field_cursor(
            usr="c:@S@Box@FI@width",
            spelling="width",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        field.type.spelling = "float"

        cls = _make_class_cursor(usr="c:@S@Box", spelling="Box", file_name=fname, children=[field])
        tu = _make_tu(source, [cls])

        _nodes, edges = extract_nodes_and_edges(tu, source)

        of_edges = [
            e
            for e in edges
            if e["edge_type"] == EDGE_OF_TYPE and e["source_usr"] == "c:@S@Box@FI@width"
        ]
        assert len(of_edges) == 1, (
            f"Field must have exactly 1 OF_TYPE edge (no duplicates), got {len(of_edges)}"
        )
