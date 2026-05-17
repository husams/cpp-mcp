"""P3: MEMBER_OF.access property on all MEMBER_OF edges.

Covers:
  - Explicit public/protected/private specifiers → correct access string (S1-2 AC1, SC1).
  - struct member, no specifier → access="public" (S1-2 AC2, SC2, ADR-25 D4).
  - class member, no specifier → access="private" (S1-2 AC3, SC3).
  - union member, no specifier → access="public" via _resolve_access (ADR-25 D4, S1-2 EC1).
  - method MEMBER_OF carries access (ADR-25 D5, S1-2 EC2).
  - Negative bound: every emitted MEMBER_OF.access value in {public,protected,private} (S1-2 EC3).

Libclang probe — union members (ADR-25 F-4):
  The AccessSpecifier enum is available on the pinned libclang (PUBLIC, PROTECTED,
  PRIVATE, INVALID, NONE all present). libclang returns AccessSpecifier.INVALID for
  union members that have no explicit access specifier (union members are implicitly
  public per ISO C++ but libclang does not return PUBLIC for them). The
  ``_resolve_access`` function handles this via the parent-kind default:
  ``UNION_DECL`` → ``"public"``.  This is verified by the unit test
  ``test_union_member_defaults_to_public`` which directly calls ``_resolve_access``
  with a cursor whose ``access_specifier`` is ``AccessSpecifier.INVALID`` and
  ``parent_kind="UNION_DECL"``.

Note: UNION_DECL is not in ``_MEMBER_PARENT_KINDS`` and union members do not emit
MEMBER_OF edges in S1. The union default is therefore tested via ``_resolve_access``
directly (unit on the helper), not end-to-end via ``extract_nodes_and_edges``.
Extending MEMBER_OF emission to unions is a follow-up (see implementation-notes.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from cpp_mcp.graphdb.exporter import _resolve_access, extract_nodes_and_edges
from cpp_mcp.graphdb.schema import EDGE_MEMBER_OF

# ---------------------------------------------------------------------------
# Fake cursor / TU helpers
# ---------------------------------------------------------------------------

_VALID_ACCESS_STRINGS: frozenset[str] = frozenset({"public", "protected", "private"})


def _make_access_specifier_mock(spec_enum: Any) -> Any:
    """Return a mock whose `access_specifier` attribute equals *spec_enum*."""
    cursor = MagicMock()
    type(cursor).access_specifier = PropertyMock(return_value=spec_enum)
    return cursor


def _make_member_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    kind_name: str = "FIELD_DECL",
    access_specifier: Any = None,
    children: list[Any] | None = None,
) -> Any:
    """Build a fake member cursor (FIELD_DECL, CXX_METHOD, CONSTRUCTOR, DESTRUCTOR)."""
    from clang.cindex import AccessSpecifier, StorageClass  # type: ignore[import-untyped]

    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = True
    cursor.type.spelling = "int"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 5
    cursor.location.column = 5
    cursor.get_children.return_value = children or []
    cursor.get_arguments.return_value = []  # P3: no params for these test fixtures
    cursor.referenced = None
    # Remove is_static_member (not on pinned libclang) so fallback fires.
    del cursor.is_static_member
    cursor.storage_class = StorageClass.NONE

    if access_specifier is None:
        # Simulate implicit specifier — libclang returns INVALID (as observed for unions).
        type(cursor).access_specifier = PropertyMock(return_value=AccessSpecifier.INVALID)
    else:
        type(cursor).access_specifier = PropertyMock(return_value=access_specifier)

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
# Tests — explicit access specifiers (S1-2 AC1, SC1)
# ---------------------------------------------------------------------------


class TestExplicitAccessSpecifiers:
    @pytest.mark.parametrize(
        "access_enum_name,expected_str",
        [
            ("PUBLIC", "public"),
            ("PROTECTED", "protected"),
            ("PRIVATE", "private"),
        ],
    )
    def test_explicit_specifier_on_field_member_of(
        self, tmp_path: Path, access_enum_name: str, expected_str: str
    ) -> None:
        """Explicit public/protected/private field → MEMBER_OF.access == expected.

        Covers S1-2 AC1, SC1.
        """
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        spec_enum = getattr(AccessSpecifier, access_enum_name)
        field_usr = f"c:@S@Foo@FI@field_{expected_str}"
        field = _make_member_cursor(
            usr=field_usr,
            spelling=f"field_{expected_str}",
            file_name=fname,
            kind_name="FIELD_DECL",
            access_specifier=spec_enum,
        )
        cls = _make_class_cursor(
            usr="c:@S@Foo",
            spelling="Foo",
            file_name=fname,
            kind_name="CLASS_DECL",
            children=[field],
        )
        tu = _make_tu(source, [cls])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [
            e for e in edges if e["edge_type"] == EDGE_MEMBER_OF and e["source_usr"] == field_usr
        ]
        assert len(member_of_edges) == 1, (
            f"Expected 1 MEMBER_OF edge for {field_usr!r}, got {len(member_of_edges)}"
        )
        assert member_of_edges[0]["props"]["access"] == expected_str, (
            f"Expected access={expected_str!r}, got {member_of_edges[0]['props']['access']!r}"
        )


# ---------------------------------------------------------------------------
# Tests — struct member implicit → public  (S1-2 AC2, SC2)
# ---------------------------------------------------------------------------


class TestStructDefaultPublic:
    def test_struct_member_no_specifier_is_public(self, tmp_path: Path) -> None:
        """struct member with no explicit specifier → access='public'. (S1-2 AC2, SC2)"""
        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field_usr = "c:@S@MyStruct@FI@val"
        field = _make_member_cursor(
            usr=field_usr,
            spelling="val",
            file_name=fname,
            kind_name="FIELD_DECL",
            access_specifier=None,  # INVALID — triggers parent-kind default
        )
        struct = _make_class_cursor(
            usr="c:@S@MyStruct",
            spelling="MyStruct",
            file_name=fname,
            kind_name="STRUCT_DECL",
            children=[field],
        )
        tu = _make_tu(source, [struct])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [
            e for e in edges if e["edge_type"] == EDGE_MEMBER_OF and e["source_usr"] == field_usr
        ]
        assert len(member_of_edges) == 1, (
            f"Expected 1 MEMBER_OF edge for struct member, got {len(member_of_edges)}"
        )
        assert member_of_edges[0]["props"]["access"] == "public", (
            f"struct member default must be 'public', got {member_of_edges[0]['props']['access']!r}"
        )


# ---------------------------------------------------------------------------
# Tests — class member implicit → private  (S1-2 AC3, SC3)
# ---------------------------------------------------------------------------


class TestClassDefaultPrivate:
    def test_class_member_no_specifier_is_private(self, tmp_path: Path) -> None:
        """class member with no explicit specifier → access='private'. (S1-2 AC3, SC3)"""
        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field_usr = "c:@C@MyClass@FI@data"
        field = _make_member_cursor(
            usr=field_usr,
            spelling="data",
            file_name=fname,
            kind_name="FIELD_DECL",
            access_specifier=None,  # INVALID — triggers parent-kind default → private
        )
        cls = _make_class_cursor(
            usr="c:@C@MyClass",
            spelling="MyClass",
            file_name=fname,
            kind_name="CLASS_DECL",
            children=[field],
        )
        tu = _make_tu(source, [cls])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [
            e for e in edges if e["edge_type"] == EDGE_MEMBER_OF and e["source_usr"] == field_usr
        ]
        assert len(member_of_edges) == 1, (
            f"Expected 1 MEMBER_OF edge for class member, got {len(member_of_edges)}"
        )
        assert member_of_edges[0]["props"]["access"] == "private", (
            f"class member default must be 'private', got {member_of_edges[0]['props']['access']!r}"
        )


# ---------------------------------------------------------------------------
# Tests — union member default via _resolve_access (ADR-25 D4, S1-2 EC1)
# ---------------------------------------------------------------------------


class TestUnionDefaultAccess:
    def test_union_member_defaults_to_public_via_resolve_access(self) -> None:
        """union member: _resolve_access with INVALID + UNION_DECL parent → 'public'. (ADR-25 D4)

        UNION_DECL is not in _MEMBER_PARENT_KINDS, so no MEMBER_OF edge is emitted
        for union members in S1. The union default is therefore tested by calling
        _resolve_access directly.

        Union-access probe (ADR-25 F-4): the pinned libclang AccessSpecifier enum
        has INVALID (verified). Libclang returns INVALID for union members that have
        no explicit specifier (union members are implicitly public per ISO C++ but
        libclang does not emit PUBLIC for them). Extending emission to union members
        is a follow-up item (implementation-notes.md).
        """
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        cursor = _make_access_specifier_mock(AccessSpecifier.INVALID)
        result = _resolve_access(cursor, "UNION_DECL")
        assert result == "public", (
            f"Union member with INVALID access spec must default to 'public', got {result!r}"
        )

    def test_union_member_explicit_public_is_public(self) -> None:
        """If libclang returns PUBLIC for a union member, _resolve_access must honour it."""
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        cursor = _make_access_specifier_mock(AccessSpecifier.PUBLIC)
        result = _resolve_access(cursor, "UNION_DECL")
        assert result == "public"


# ---------------------------------------------------------------------------
# Tests — method MEMBER_OF carries access (ADR-25 D5, S1-2 EC2)
# ---------------------------------------------------------------------------


class TestMethodMemberOfAccess:
    def test_cxx_method_member_of_has_access(self, tmp_path: Path) -> None:
        """CXX_METHOD MEMBER_OF edge carries access property. (ADR-25 D5, S1-2 EC2)"""
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        method_usr = "c:@C@Foo@F@doSomething#"
        method = _make_member_cursor(
            usr=method_usr,
            spelling="doSomething",
            file_name=fname,
            kind_name="CXX_METHOD",
            access_specifier=AccessSpecifier.PUBLIC,
        )
        cls = _make_class_cursor(
            usr="c:@C@Foo",
            spelling="Foo",
            file_name=fname,
            kind_name="CLASS_DECL",
            children=[method],
        )
        tu = _make_tu(source, [cls])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [
            e for e in edges if e["edge_type"] == EDGE_MEMBER_OF and e["source_usr"] == method_usr
        ]
        assert len(member_of_edges) == 1, (
            f"Expected 1 MEMBER_OF edge for CXX_METHOD {method_usr!r}, got {len(member_of_edges)}"
        )
        assert "access" in member_of_edges[0]["props"], "MEMBER_OF edge must have 'access' property"
        assert member_of_edges[0]["props"]["access"] == "public", (
            f"Method with PUBLIC specifier must emit access='public', "
            f"got {member_of_edges[0]['props']['access']!r}"
        )

    def test_constructor_member_of_has_access(self, tmp_path: Path) -> None:
        """CONSTRUCTOR MEMBER_OF edge carries access property. (ADR-25 D5)"""
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        ctor_usr = "c:@C@Bar@F@Bar#"
        ctor = _make_member_cursor(
            usr=ctor_usr,
            spelling="Bar",
            file_name=fname,
            kind_name="CONSTRUCTOR",
            access_specifier=AccessSpecifier.PUBLIC,
        )
        cls = _make_class_cursor(
            usr="c:@C@Bar",
            spelling="Bar",
            file_name=fname,
            kind_name="CLASS_DECL",
            children=[ctor],
        )
        tu = _make_tu(source, [cls])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [
            e for e in edges if e["edge_type"] == EDGE_MEMBER_OF and e["source_usr"] == ctor_usr
        ]
        assert len(member_of_edges) == 1, (
            f"Expected 1 MEMBER_OF edge for CONSTRUCTOR {ctor_usr!r}, got {len(member_of_edges)}"
        )
        assert member_of_edges[0]["props"]["access"] == "public"

    def test_destructor_member_of_has_access(self, tmp_path: Path) -> None:
        """DESTRUCTOR MEMBER_OF edge carries access property. (ADR-25 D5)"""
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        dtor_usr = "c:@C@Bar@F@~Bar#"
        dtor = _make_member_cursor(
            usr=dtor_usr,
            spelling="~Bar",
            file_name=fname,
            kind_name="DESTRUCTOR",
            access_specifier=AccessSpecifier.PUBLIC,
        )
        cls = _make_class_cursor(
            usr="c:@C@Bar",
            spelling="Bar",
            file_name=fname,
            kind_name="CLASS_DECL",
            children=[dtor],
        )
        tu = _make_tu(source, [cls])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [
            e for e in edges if e["edge_type"] == EDGE_MEMBER_OF and e["source_usr"] == dtor_usr
        ]
        assert len(member_of_edges) == 1, (
            f"Expected 1 MEMBER_OF edge for DESTRUCTOR {dtor_usr!r}, got {len(member_of_edges)}"
        )
        assert member_of_edges[0]["props"]["access"] == "public"


# ---------------------------------------------------------------------------
# Tests — negative bound: all MEMBER_OF.access in valid set  (S1-2 EC3)
# ---------------------------------------------------------------------------


class TestNegativeBoundAllAccessValid:
    def test_all_emitted_member_of_access_in_valid_set(self, tmp_path: Path) -> None:
        """Every emitted MEMBER_OF.access value must be in {public, protected, private}. (S1-2 EC3)

        Fixture: class with public field, protected method, private field.
        Asserts every MEMBER_OF edge in the output has a valid access string.
        """
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        pub_field_usr = "c:@C@Mixed@FI@pub"
        prot_method_usr = "c:@C@Mixed@F@protMethod#"
        priv_field_usr = "c:@C@Mixed@FI@priv"

        pub_field = _make_member_cursor(
            usr=pub_field_usr,
            spelling="pub",
            file_name=fname,
            kind_name="FIELD_DECL",
            access_specifier=AccessSpecifier.PUBLIC,
        )
        prot_method = _make_member_cursor(
            usr=prot_method_usr,
            spelling="protMethod",
            file_name=fname,
            kind_name="CXX_METHOD",
            access_specifier=AccessSpecifier.PROTECTED,
        )
        priv_field = _make_member_cursor(
            usr=priv_field_usr,
            spelling="priv",
            file_name=fname,
            kind_name="FIELD_DECL",
            access_specifier=AccessSpecifier.PRIVATE,
        )
        cls = _make_class_cursor(
            usr="c:@C@Mixed",
            spelling="Mixed",
            file_name=fname,
            kind_name="CLASS_DECL",
            children=[pub_field, prot_method, priv_field],
        )
        tu = _make_tu(source, [cls])

        _, edges = extract_nodes_and_edges(tu, source)

        member_of_edges = [e for e in edges if e["edge_type"] == EDGE_MEMBER_OF]
        assert len(member_of_edges) >= 3, (
            f"Expected at least 3 MEMBER_OF edges, got {len(member_of_edges)}"
        )
        for edge in member_of_edges:
            assert "access" in edge["props"], f"MEMBER_OF edge {edge!r} missing 'access' property"
            access_val = edge["props"]["access"]
            assert access_val in _VALID_ACCESS_STRINGS, (
                f"MEMBER_OF.access must be in {_VALID_ACCESS_STRINGS!r}, got {access_val!r}"
            )
