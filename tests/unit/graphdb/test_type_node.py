"""P2 — Type node creation, properties, and deduplication (SC-A-01..SC-A-09).

Covers ADR-26 D1 (USR format), D2 (source-form spelling), D3 (per-export dedup).

Fake cursor fixtures are built with MagicMock; the helpers under test
(_type_usr, _type_props, _get_or_create_type) are pure functions of
cursor/type inputs so real libclang is not required.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord
from cpp_mcp.graphdb.exporter import (
    _get_or_create_type,
    _type_props,
    _type_usr,
    extract_nodes_and_edges,
)
from cpp_mcp.graphdb.schema import (
    NODE_TYPE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_type(
    *,
    spelling: str,
    kind_name: str = "INT",
    is_const: bool = False,
    is_volatile: bool = False,
    pointee: Any = None,
) -> Any:
    """Build a fake libclang ``Type`` object.

    Uses real ``clang.cindex.TypeKind`` so equality checks in
    ``_type_props`` and ``_get_or_create_type`` work correctly.
    """
    from clang.cindex import TypeKind  # type: ignore[import-untyped]

    t = MagicMock()
    t.spelling = spelling
    t.kind = getattr(TypeKind, kind_name)
    t.is_const_qualified.return_value = is_const
    t.is_volatile_qualified.return_value = is_volatile

    if pointee is not None:
        t.get_pointee.return_value = pointee
    else:
        # Non-ptr/ref types: get_pointee returns something with empty spelling.
        empty = MagicMock()
        empty.spelling = ""
        t.get_pointee.return_value = empty

    return t


def _make_func_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    result_type: Any,
    kind_name: str = "FUNCTION_DECL",
) -> Any:
    """Build a fake FUNCTION_DECL cursor that returns *result_type*."""
    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = False
    cursor.type.spelling = spelling
    cursor.result_type = result_type
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.get_arguments.return_value = []  # P3: no params → no HAS_PARAM edges
    cursor.referenced = None
    return cursor


def _make_tu(file_path: Path, top_level_cursors: list[Any]) -> Any:
    tu = MagicMock()
    tu.diagnostics = []
    tu.cursor.get_children.return_value = top_level_cursors
    tu.cursor.location.file = None
    tu.cursor.kind.name = "TRANSLATION_UNIT"
    tu.cursor.get_usr.return_value = ""
    tu.cursor.spelling = ""
    tu.cursor.is_definition.return_value = False
    return tu


def _type_nodes(nodes: list[NodeRecord]) -> list[NodeRecord]:
    return [n for n in nodes if n["label"] == NODE_TYPE]


def _find_type_node(nodes: list[NodeRecord], spelling: str) -> NodeRecord | None:
    for n in nodes:
        if n["label"] == NODE_TYPE and n["props"].get("spelling") == spelling:
            return n
    return None


# ---------------------------------------------------------------------------
# SC-A-01 — lvalue reference type: all 8 properties present and correct
# ---------------------------------------------------------------------------


class TestTypeNodeBasicProperties:
    """SC-A-01: Type node created with all required properties."""

    def test_lvalue_ref_type_properties(self) -> None:
        """const std::string & → 8 props; is_lvalue_reference=True, is_rvalue_reference=False."""
        from clang.cindex import TypeKind  # type: ignore[import-untyped]

        referent = _make_type(spelling="const std::string", kind_name="RECORD", is_const=True)
        t = _make_type(
            spelling="const std::string &",
            kind_name="LVALUEREFERENCE",
            is_const=False,
            pointee=referent,
        )

        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()
        usr = _get_or_create_type(t, nodes, edges, seen)

        assert usr is not None
        assert len(nodes) >= 1
        node = next(n for n in nodes if n["props"]["spelling"] == "const std::string &")
        p = node["props"]

        assert p["spelling"] == "const std::string &"
        assert p["is_const"] is False  # top-level const — lvalue-ref is not const-qualified
        assert p["is_volatile"] is False
        assert p["is_pointer"] is False
        assert p["is_reference"] is True
        assert p["is_lvalue_reference"] is True
        assert p["is_rvalue_reference"] is False
        assert p["kind"] == TypeKind.LVALUEREFERENCE.name


# ---------------------------------------------------------------------------
# SC-A-02 — pointer type: is_pointer=True, is_reference=False
# ---------------------------------------------------------------------------


class TestPointerTypeNode:
    """SC-A-02: Pointer Type node has is_pointer true."""

    def test_pointer_type_properties(self) -> None:
        from clang.cindex import TypeKind  # type: ignore[import-untyped]

        pointee = _make_type(spelling="int", kind_name="INT")
        t = _make_type(spelling="int *", kind_name="POINTER", pointee=pointee)

        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()
        _get_or_create_type(t, nodes, edges, seen)

        ptr_node = next(n for n in nodes if n["props"]["spelling"] == "int *")
        p = ptr_node["props"]
        assert p["is_pointer"] is True
        assert p["is_reference"] is False
        assert p["is_lvalue_reference"] is False
        assert p["is_rvalue_reference"] is False
        assert p["kind"] == TypeKind.POINTER.name


# ---------------------------------------------------------------------------
# SC-A-03 — builtin int dedup: two functions sharing "int" produce one Type node
# ---------------------------------------------------------------------------


class TestBuiltinIntDedup:
    """SC-A-03: Builtin type int creates a single Type node across two functions."""

    def test_int_deduplicated_across_functions(self, tmp_path: Path) -> None:
        fname = str(tmp_path / "test.cpp")
        (tmp_path / "test.cpp").write_text("")

        int_type = _make_type(spelling="int", kind_name="INT")
        f1 = _make_func_cursor(usr="c:@F@f", spelling="f", file_name=fname, result_type=int_type)
        f2 = _make_func_cursor(usr="c:@F@g", spelling="g", file_name=fname, result_type=int_type)

        tu = _make_tu(tmp_path / "test.cpp", [f1, f2])
        nodes, _ = extract_nodes_and_edges(tu, tmp_path / "test.cpp")

        int_nodes = [
            n for n in nodes if n["label"] == NODE_TYPE and n["props"]["spelling"] == "int"
        ]
        assert len(int_nodes) == 1, f"Expected 1 'int' Type node, got {len(int_nodes)}"


# ---------------------------------------------------------------------------
# SC-A-04 — void dedup: two void-returning functions produce exactly one "void" Type node
# ---------------------------------------------------------------------------


class TestBuiltinVoidDedup:
    """SC-A-04: Builtin type void creates a single Type node."""

    def test_void_deduplicated_across_functions(self, tmp_path: Path) -> None:
        fname = str(tmp_path / "test.cpp")
        (tmp_path / "test.cpp").write_text("")

        void_type = _make_type(spelling="void", kind_name="VOID")
        f1 = _make_func_cursor(usr="c:@F@f", spelling="f", file_name=fname, result_type=void_type)
        f2 = _make_func_cursor(usr="c:@F@g", spelling="g", file_name=fname, result_type=void_type)

        tu = _make_tu(tmp_path / "test.cpp", [f1, f2])
        nodes, _ = extract_nodes_and_edges(tu, tmp_path / "test.cpp")

        void_nodes = [
            n for n in nodes if n["label"] == NODE_TYPE and n["props"]["spelling"] == "void"
        ]
        assert len(void_nodes) == 1, f"Expected 1 'void' Type node, got {len(void_nodes)}"


# ---------------------------------------------------------------------------
# SC-A-05 — dedup across two declarations with same type spelling
# ---------------------------------------------------------------------------


class TestTypeDedup:
    """SC-A-05: Two declarations sharing the same canonical type produce one Type node."""

    def test_same_spelling_produces_one_type_node(self) -> None:
        t1 = _make_type(spelling="const std::string &", kind_name="LVALUEREFERENCE")
        t2 = _make_type(spelling="const std::string &", kind_name="LVALUEREFERENCE")

        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()

        usr1 = _get_or_create_type(t1, nodes, edges, seen)
        usr2 = _get_or_create_type(t2, nodes, edges, seen)

        assert usr1 == usr2
        string_ref_nodes = [n for n in nodes if n["props"]["spelling"] == "const std::string &"]
        assert len(string_ref_nodes) == 1, (
            "Two cursors with same type spelling must produce one Type node"
        )


# ---------------------------------------------------------------------------
# SC-A-06 — USR format: type:<sha1_hex_40_chars>
# ---------------------------------------------------------------------------


class TestTypeUsr:
    """SC-A-06: Type node USR follows type:<sha1(canonical_spelling)> format (ADR-26 D1)."""

    def test_usr_format_matches_pattern(self) -> None:
        usr = _type_usr("int")
        assert re.match(r"^type:[0-9a-f]{40}$", usr), f"USR {usr!r} does not match expected format"

    def test_usr_deterministic(self) -> None:
        assert _type_usr("int") == _type_usr("int")

    def test_usr_unique_for_different_spellings(self) -> None:
        assert _type_usr("int") != _type_usr("int *")
        assert _type_usr("int *") != _type_usr("int **")

    def test_usr_matches_manual_sha1(self) -> None:
        spelling = "const std::string &"
        expected = "type:" + hashlib.sha1(spelling.encode("utf-8")).hexdigest()
        assert _type_usr(spelling) == expected

    @pytest.mark.parametrize(
        "spelling",
        ["int", "void", "int *", "const std::string &", "int &&", "double"],
    )
    def test_usr_prefix_type(self, spelling: str) -> None:
        assert _type_usr(spelling).startswith("type:")

    def test_usr_is_40_char_hex_after_prefix(self) -> None:
        usr = _type_usr("int **")
        hex_part = usr[len("type:") :]
        assert len(hex_part) == 40
        assert re.match(r"^[0-9a-f]{40}$", hex_part)

    def test_source_form_not_desugared(self) -> None:
        """ADR-26 D2: 'const std::string &' must NOT be desugared.

        The USR for 'const std::string &' must differ from the USR for the
        desugared form 'const std::basic_string<char, std::char_traits<char>, ...> &'.
        This ensures _type_usr uses the source-form spelling, not get_canonical().
        """
        source_form_usr = _type_usr("const std::string &")
        desugared_form_usr = _type_usr(
            "const std::basic_string<char, std::char_traits<char>, std::allocator<char>> &"
        )
        assert source_form_usr != desugared_form_usr, (
            "Source-form and desugared spellings must produce distinct USRs (ADR-26 D2)"
        )


# ---------------------------------------------------------------------------
# SC-A-07 — lvalue reference mutual exclusion
# ---------------------------------------------------------------------------


class TestLvalueRefMutualExclusion:
    """SC-A-07: lvalue reference Type has is_lvalue_reference=True, is_rvalue_reference=False."""

    def test_lvalue_ref_flags(self) -> None:
        t = _make_type(spelling="int &", kind_name="LVALUEREFERENCE")
        props = _type_props(t)

        assert props["is_lvalue_reference"] is True
        assert props["is_rvalue_reference"] is False
        assert props["is_reference"] is True
        assert props["is_pointer"] is False


# ---------------------------------------------------------------------------
# SC-A-08 — rvalue reference mutual exclusion
# ---------------------------------------------------------------------------


class TestRvalueRefMutualExclusion:
    """SC-A-08: rvalue reference Type has is_rvalue_reference=True, is_lvalue_reference=False."""

    def test_rvalue_ref_flags(self) -> None:
        t = _make_type(spelling="int &&", kind_name="RVALUEREFERENCE")
        props = _type_props(t)

        assert props["is_rvalue_reference"] is True
        assert props["is_lvalue_reference"] is False
        assert props["is_reference"] is True
        assert props["is_pointer"] is False


# ---------------------------------------------------------------------------
# SC-A-09 — no Type node ever has both is_lvalue_reference and is_rvalue_reference true
# ---------------------------------------------------------------------------


class TestNoTypeNodeHasBothRefFlags:
    """SC-A-09: No Type node ever has both is_lvalue_reference and is_rvalue_reference true."""

    @pytest.mark.parametrize(
        "spelling,kind_name",
        [
            ("int &", "LVALUEREFERENCE"),
            ("int &&", "RVALUEREFERENCE"),
            ("const std::string &", "LVALUEREFERENCE"),
            ("int", "INT"),
            ("int *", "POINTER"),
            ("void", "VOID"),
        ],
    )
    def test_no_type_has_both_ref_flags(self, spelling: str, kind_name: str) -> None:
        t = _make_type(spelling=spelling, kind_name=kind_name)
        props = _type_props(t)

        assert not (props["is_lvalue_reference"] and props["is_rvalue_reference"]), (
            f"Type '{spelling}' has both is_lvalue_reference and is_rvalue_reference set to True"
        )


# ---------------------------------------------------------------------------
# Additional: _get_or_create_type returns None for None input / empty spelling
# ---------------------------------------------------------------------------


class TestGetOrCreateTypeEdgeCases:
    def test_none_input_returns_none(self) -> None:
        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()
        assert _get_or_create_type(None, nodes, edges, seen) is None
        assert nodes == []

    def test_empty_spelling_returns_none(self) -> None:
        t = MagicMock()
        t.spelling = ""
        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()
        assert _get_or_create_type(t, nodes, edges, seen) is None
        assert nodes == []

    def test_idempotent_second_call(self) -> None:
        """Calling _get_or_create_type twice with same type must not double-append."""
        t = _make_type(spelling="int", kind_name="INT")
        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []
        seen: set[str] = set()

        usr1 = _get_or_create_type(t, nodes, edges, seen)
        count_after_first = len(nodes)
        usr2 = _get_or_create_type(t, nodes, edges, seen)

        assert usr1 == usr2
        assert len(nodes) == count_after_first, "Second call must not append a duplicate node"
