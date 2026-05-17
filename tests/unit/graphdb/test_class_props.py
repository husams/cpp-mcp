"""P6 — Class properties (SC-G-01..SC-G-06).

Covers ADR-26 D8 (UNION_DECL → NODE_CLASS, record_kind), D10 (is_final via
CXX_FINAL_ATTR child, is_abstract via is_abstract_record()), design §2.5, §3.1.

Properties tested:
  - is_final    : bool  (CXX_FINAL_ATTR child present?)
  - is_abstract : bool  (cursor.is_abstract_record())
  - record_kind : str   ("class" | "struct" | "union")

DEFERRED: is_template (S3).

All fixtures use MagicMock; real libclang is not required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_CLASS

# ---------------------------------------------------------------------------
# Helpers to build fake cursors
# ---------------------------------------------------------------------------


def _make_child(kind_name: str) -> Any:
    """Return a minimal fake child cursor with the given kind name."""
    child = MagicMock()
    child.kind.name = kind_name
    child.get_usr.return_value = ""
    child.spelling = ""
    child.location.file = None
    child.get_children.return_value = []
    child.get_arguments.return_value = []
    child.get_tokens.return_value = []
    child.referenced = None
    child.is_definition.return_value = False
    child.type.spelling = ""
    return child


def _make_class_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    kind_name: str = "CLASS_DECL",
    is_abstract: bool = False,
    has_final_attr: bool = False,
    extra_children: list[Any] | None = None,
) -> Any:
    """Build a fake class/struct/union cursor for P6 tests.

    Parameters
    ----------
    usr, spelling, file_name:
        Basic cursor identity fields.
    kind_name:
        CursorKind name — one of CLASS_DECL, STRUCT_DECL, UNION_DECL.
    is_abstract:
        Return value for ``cursor.is_abstract_record()``.
    has_final_attr:
        If True, a CXX_FINAL_ATTR child is added to ``cursor.get_children()``.
    extra_children:
        Additional fake child cursors (e.g. field members).  Appended after
        the optional CXX_FINAL_ATTR child.
    """
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
    cursor.get_arguments.return_value = []
    cursor.get_tokens.return_value = []
    cursor.referenced = None

    # is_abstract_record
    cursor.is_abstract_record.return_value = is_abstract

    # Build children list
    children: list[Any] = []
    if has_final_attr:
        children.append(_make_child("CXX_FINAL_ATTR"))
    if extra_children:
        children.extend(extra_children)
    cursor.get_children.return_value = children

    return cursor


def _make_tu(file_path: Path, top_level_cursors: list[Any]) -> Any:
    tu = MagicMock()
    root = MagicMock()
    root.get_children.return_value = top_level_cursors
    root.kind.name = "TRANSLATION_UNIT"
    root.get_usr.return_value = ""
    root.spelling = ""
    root.location.file = None
    tu.cursor = root
    return tu


def _extract_class_node(file_path: Path, cursor: Any) -> dict[str, Any] | None:
    """Run extract_nodes_and_edges and return the Class node matching *cursor*."""
    tu = _make_tu(file_path, [cursor])
    nodes, _edges = extract_nodes_and_edges(tu, file_path)
    for node in nodes:
        if node["label"] == NODE_CLASS and node["usr"] == cursor.get_usr():
            return node
    return None


# ---------------------------------------------------------------------------
# SC-G-01 — Every Class node has is_final, is_abstract, and record_kind
# ---------------------------------------------------------------------------


class TestAllPropertiesPresent:
    """SC-G-01: every Class node has all required S2 class properties."""

    from typing import ClassVar

    REQUIRED_PROPS: ClassVar[set[str]] = {"is_final", "is_abstract", "record_kind"}

    def test_all_props_present_class(self, tmp_path: Path) -> None:
        """SC-G-01: CLASS_DECL — all three properties exist."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@Simple",
            spelling="Simple",
            file_name=str(file_path),
            kind_name="CLASS_DECL",
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None, "Class node must be created"
        for prop in self.REQUIRED_PROPS:
            assert prop in node["props"], f"Missing property: {prop}"

    def test_prop_types_class(self, tmp_path: Path) -> None:
        """SC-G-01: properties have correct types (bool, bool, str)."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@Simple",
            spelling="Simple",
            file_name=str(file_path),
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        props = node["props"]
        assert isinstance(props["is_final"], bool), "is_final must be bool"
        assert isinstance(props["is_abstract"], bool), "is_abstract must be bool"
        assert isinstance(props["record_kind"], str), "record_kind must be str"

    @pytest.mark.parametrize("kind_name", ["CLASS_DECL", "STRUCT_DECL", "UNION_DECL"])
    def test_all_props_present_all_kinds(self, tmp_path: Path, kind_name: str) -> None:
        """SC-G-01: all three kinds produce a Class node with all three properties."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr=f"c:@S@T{kind_name}",
            spelling=f"T{kind_name}",
            file_name=str(file_path),
            kind_name=kind_name,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None, f"Class node must be created for {kind_name}"
        for prop in self.REQUIRED_PROPS:
            assert prop in node["props"], f"Missing {prop} for {kind_name}"


# ---------------------------------------------------------------------------
# SC-G-02 — is_final = True for `class Sealed final {}`
# ---------------------------------------------------------------------------


class TestIsFinalTrue:
    """SC-G-02: is_final = True when CXX_FINAL_ATTR child is present."""

    def test_is_final_true_with_attr(self, tmp_path: Path) -> None:
        """SC-G-02: CLASS_DECL with CXX_FINAL_ATTR child → is_final=True."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@Sealed",
            spelling="Sealed",
            file_name=str(file_path),
            has_final_attr=True,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_final"] is True

    def test_is_final_true_struct_final(self, tmp_path: Path) -> None:
        """SC-G-02: STRUCT_DECL with CXX_FINAL_ATTR child → is_final=True."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@SealedS",
            spelling="SealedS",
            file_name=str(file_path),
            kind_name="STRUCT_DECL",
            has_final_attr=True,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_final"] is True


# ---------------------------------------------------------------------------
# SC-G-03 — is_abstract = True when pure virtual method present
# ---------------------------------------------------------------------------


class TestIsAbstractTrue:
    """SC-G-03: is_abstract = True when is_abstract_record() returns True."""

    def test_is_abstract_true(self, tmp_path: Path) -> None:
        """SC-G-03: cursor.is_abstract_record() = True → is_abstract=True."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@IShape",
            spelling="IShape",
            file_name=str(file_path),
            is_abstract=True,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_abstract"] is True


# ---------------------------------------------------------------------------
# SC-G-04 — is_abstract = False for concrete class
# ---------------------------------------------------------------------------


class TestIsAbstractFalse:
    """SC-G-04: is_abstract = False when is_abstract_record() returns False."""

    def test_is_abstract_false(self, tmp_path: Path) -> None:
        """SC-G-04: cursor.is_abstract_record() = False → is_abstract=False."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@Concrete",
            spelling="Concrete",
            file_name=str(file_path),
            is_abstract=False,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_abstract"] is False

    def test_is_abstract_false_when_method_absent(self, tmp_path: Path) -> None:
        """SC-G-04 (defensive): is_abstract defaults to False when is_abstract_record absent."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@NoAbstract",
            spelling="NoAbstract",
            file_name=str(file_path),
        )
        # Simulate missing is_abstract_record (old libclang)
        del cursor.is_abstract_record
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_abstract"] is False


# ---------------------------------------------------------------------------
# SC-G-05 — record_kind reflects C++ keyword (class/struct/union)
# ---------------------------------------------------------------------------


class TestRecordKind:
    """SC-G-05: record_kind = "class" | "struct" | "union"."""

    @pytest.mark.parametrize(
        ("kind_name", "expected_record_kind"),
        [
            ("CLASS_DECL", "class"),
            ("STRUCT_DECL", "struct"),
            ("UNION_DECL", "union"),
            ("CLASS_TEMPLATE", "class"),
        ],
    )
    def test_record_kind_value(
        self, tmp_path: Path, kind_name: str, expected_record_kind: str
    ) -> None:
        """SC-G-05: each CursorKind name maps to the correct record_kind string."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr=f"c:@S@R{kind_name}",
            spelling=f"R{kind_name}",
            file_name=str(file_path),
            kind_name=kind_name,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None, f"Class node must be created for {kind_name}"
        assert node["props"]["record_kind"] == expected_record_kind, (
            f"Expected record_kind={expected_record_kind!r} for {kind_name}, "
            f"got {node['props']['record_kind']!r}"
        )

    def test_union_decl_produces_class_node(self, tmp_path: Path) -> None:
        """SC-G-05 (ADR-26 D8): UNION_DECL maps to NODE_CLASS label."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@U@MyUnion",
            spelling="MyUnion",
            file_name=str(file_path),
            kind_name="UNION_DECL",
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None, "UNION_DECL must produce a Class node (ADR-26 D8)"
        assert node["label"] == NODE_CLASS
        assert node["props"]["record_kind"] == "union"


# ---------------------------------------------------------------------------
# SC-G-06 — is_final = False for non-final class
# ---------------------------------------------------------------------------


class TestIsFinalFalse:
    """SC-G-06: is_final = False when no CXX_FINAL_ATTR child."""

    def test_is_final_false_no_attr(self, tmp_path: Path) -> None:
        """SC-G-06: CLASS_DECL without CXX_FINAL_ATTR child → is_final=False."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr="c:@S@Regular",
            spelling="Regular",
            file_name=str(file_path),
            has_final_attr=False,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_final"] is False

    def test_is_final_false_other_children_present(self, tmp_path: Path) -> None:
        """SC-G-06: children that are NOT CXX_FINAL_ATTR must not set is_final=True."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        # Add a non-final-attr child (e.g. CXX_BASE_SPECIFIER)
        non_final = _make_child("CXX_BASE_SPECIFIER")
        cursor = _make_class_cursor(
            usr="c:@S@WithBase",
            spelling="WithBase",
            file_name=str(file_path),
            has_final_attr=False,
            extra_children=[non_final],
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_final"] is False

    @pytest.mark.parametrize("kind_name", ["STRUCT_DECL", "UNION_DECL"])
    def test_is_final_false_for_struct_and_union(self, tmp_path: Path, kind_name: str) -> None:
        """SC-G-06: struct/union without final attr also get is_final=False."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_class_cursor(
            usr=f"c:@S@T{kind_name}",
            spelling=f"T{kind_name}",
            file_name=str(file_path),
            kind_name=kind_name,
            has_final_attr=False,
        )
        node = _extract_class_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_final"] is False
