"""P2: FIELD_DECL classifier — Field vs GlobalVariable split.

Covers:
  - Non-static class data member → Field (S1-1 AC1, SC1, ADR-25 D1).
  - Static class data member → GlobalVariable (S1-1 AC3, SC3, ADR-25 D7).
  - Anonymous struct/union member → Field (ADR-25 D3, minimal coverage).
  - PARM_DECL → Variable (ADR-25 D2; ensures D2 invariant holds alongside D1).

Libclang capability probe (F-3 per ADR-25):
  ``Cursor.is_static_member`` is NOT available on the pinned libclang version
  (clang-python binding, verified during P2 implementation). All static-member
  detection uses the ``StorageClass.STATIC`` fallback path in ``_is_static_member``.

Note on USR-scoped assertions (ADR-25 D2):
  Tests assert on specific USRs only. Never assert "no Variable nodes globally"
  because PARM_DECL still emits Variable in S1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_FIELD, NODE_GLOBAL_VARIABLE, NODE_VARIABLE

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
    """Build a fake PARM_DECL cursor (Variable per ADR-25 D2)."""
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
    """Build a fake FUNCTION_DECL cursor containing *params* as children."""
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
    cursor.get_children.return_value = params
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
# Tests — PARM_DECL → Variable (ADR-25 D2 invariant)
# ---------------------------------------------------------------------------


class TestParmDeclInvariant:
    def test_parm_decl_produces_variable(self, tmp_path: Path) -> None:
        """PARM_DECL still emits Variable in S1 (transitional until S2). (ADR-25 D2)

        This positive assertion proves D2 holds: a PARM_DECL cursor must not be
        swallowed, misclassified as GlobalVariable, or emitted as Field.
        """
        source = tmp_path / "func.cpp"
        source.write_text("")
        fname = str(source)

        param_usr = "c:func.cpp@10@F@doWork#I#@x"
        param = _make_parm_cursor(usr=param_usr, spelling="x", file_name=fname)
        func = _make_function_cursor(
            usr="c:@F@doWork#I#",
            spelling="doWork",
            file_name=fname,
            params=[param],
        )
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        param_nodes = [n for n in nodes if n["usr"] == param_usr]
        assert param_nodes, f"Expected a node for PARM_DECL USR {param_usr!r} (D2)"
        assert param_nodes[0]["label"] == NODE_VARIABLE, (
            f"PARM_DECL must emit Variable in S1, got {param_nodes[0]['label']!r} (D2)"
        )

    @pytest.mark.parametrize(
        "bad_label",
        [NODE_FIELD, NODE_GLOBAL_VARIABLE],
    )
    def test_parm_decl_not_field_or_global_variable(self, tmp_path: Path, bad_label: str) -> None:
        """PARM_DECL USR must not appear as Field or GlobalVariable. (ADR-25 D2, USR-scoped)"""
        source = tmp_path / "func.cpp"
        source.write_text("")
        fname = str(source)

        param_usr = "c:func.cpp@10@F@helper#I#@n"
        param = _make_parm_cursor(usr=param_usr, spelling="n", file_name=fname)
        func = _make_function_cursor(
            usr="c:@F@helper#I#",
            spelling="helper",
            file_name=fname,
            params=[param],
        )
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        bad_nodes = [n for n in nodes if n["usr"] == param_usr and n["label"] == bad_label]
        assert not bad_nodes, (
            f"PARM_DECL USR {param_usr!r} must not produce {bad_label!r} node (D2)"
        )
