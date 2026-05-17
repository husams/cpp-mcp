"""P4: Field / GlobalVariable node properties — is_static, is_const, is_constexpr, storage_class.

Scenario-outline rows (all 10 from plan.md Story P4):

  Row  | Source declaration          | Key assertions                              | AC / SC
  -----|----------------------------|---------------------------------------------|--------
  SC1  | const int MAX = 100        | is_const=True                               | S1-3 AC1, SC1
  SC2  | constexpr int LIMIT = 42   | is_constexpr=True, is_const=True            | S1-3 AC2, SC2
  SC3  | static int file_var = 0    | is_static=True, storage_class="static"      | S1-3 AC3, SC3
  SC4  | extern int shared_val      | storage_class="extern"                      | S1-3 AC4, SC4
  SC5  | thread_local int tls = 0   | storage_class="thread_local"                | S1-3 AC5, SC5
  SC6  | int value (class member)   | is_static=False                             | S1-3 AC6, SC6
  SC7  | plain int plain_var = 0    | storage_class="none"                        | S1-3 AC7, SC7
  EC4  | int mutable_var = 0        | is_const=False, is_constexpr=False          | S1-3 EC4
  EC2  | non-static Field           | storage_class="none" (ADR-25 D6)           | S1-3 EC2
  EC1  | extern thread_local int    | storage_class="thread_local"                | S1-3 EC1

Libclang capability notes (ADR-25 F-3, recorded for P4):
  - ``cursor.is_constexpr`` is NOT available on the pinned libclang version.
    Token-scan fallback (``cursor.get_tokens()`` → look for "constexpr") is exercised.
  - ``cursor.is_thread_local`` is NOT available on pinned libclang.
    Token-scan fallback is exercised for thread_local detection.
  - No THREAD_LOCAL enum value in StorageClass (confirmed in P2 probe).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_FIELD, NODE_GLOBAL_VARIABLE

# ---------------------------------------------------------------------------
# Fake cursor / TU helpers (mirrors test_field_classification.py pattern)
# ---------------------------------------------------------------------------


def _make_token(spelling: str) -> Any:
    tok = MagicMock()
    tok.spelling = spelling
    return tok


def _make_var_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    storage_class: Any,
    is_const_qualified: bool = False,
    is_constexpr_available: bool = False,
    is_constexpr_val: bool = False,
    extra_tokens: list[str] | None = None,
    is_thread_local_available: bool = False,
    is_thread_local_val: bool = False,
) -> Any:
    """Build a fake VAR_DECL cursor.

    *extra_tokens*: additional spelling tokens to include in ``get_tokens()``
    (used for thread_local / constexpr token-scan fallback).
    """
    cursor = MagicMock()
    cursor.kind.name = "VAR_DECL"
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = True
    cursor.type.spelling = "int"
    cursor.type.is_const_qualified.return_value = is_const_qualified
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 3
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.referenced = None
    cursor.storage_class = storage_class

    # is_constexpr: absent on pinned libclang — use token scan.
    if is_constexpr_available:
        cursor.is_constexpr.return_value = is_constexpr_val
    else:
        del cursor.is_constexpr

    # is_thread_local: absent on pinned libclang — use token scan.
    if is_thread_local_available:
        cursor.is_thread_local.return_value = is_thread_local_val
    else:
        del cursor.is_thread_local

    tokens: list[str] = [spelling]
    if extra_tokens:
        tokens = extra_tokens + tokens

    cursor.get_tokens.return_value = [_make_token(t) for t in tokens]
    return cursor


def _make_field_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    storage_class: Any,
    is_const_qualified: bool = False,
    extra_tokens: list[str] | None = None,
) -> Any:
    """Build a fake FIELD_DECL cursor for property tests."""
    cursor = MagicMock()
    cursor.kind.name = "FIELD_DECL"
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = True
    cursor.type.spelling = "int"
    cursor.type.is_const_qualified.return_value = is_const_qualified
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 5
    cursor.location.column = 5
    cursor.get_children.return_value = []
    cursor.referenced = None
    cursor.storage_class = storage_class
    del cursor.is_static_member  # absent on pinned libclang
    del cursor.is_constexpr  # absent on pinned libclang
    del cursor.is_thread_local  # absent on pinned libclang

    tokens: list[str] = [spelling]
    if extra_tokens:
        tokens = extra_tokens + tokens
    cursor.get_tokens.return_value = [_make_token(t) for t in tokens]
    return cursor


def _make_class_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    children: list[Any],
    kind_name: str = "CLASS_DECL",
) -> Any:
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
    tu = MagicMock()
    tu.diagnostics = []
    tu.cursor.get_children.return_value = top_level_cursors
    tu.cursor.location.file = None
    tu.cursor.kind.name = "TRANSLATION_UNIT"
    tu.cursor.get_usr.return_value = ""
    tu.cursor.spelling = ""
    tu.cursor.is_definition.return_value = False
    return tu


def _node_for_usr(nodes: list[Any], usr: str) -> Any:
    """Return the single node for *usr* or raise AssertionError."""
    matches = [n for n in nodes if n["usr"] == usr]
    assert matches, f"No node found for USR {usr!r}"
    assert len(matches) == 1, f"Expected 1 node for USR {usr!r}, found {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# SC1 — const int MAX = 100  →  is_const=True  (S1-3 AC1, SC1)
# ---------------------------------------------------------------------------


class TestConstVar:
    def test_const_var_is_const_true(self, tmp_path: Path) -> None:
        """``const int MAX = 100`` → ``is_const=True``. (S1-3 AC1, SC1)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@MAX"
        cursor = _make_var_cursor(
            usr=usr,
            spelling="MAX",
            file_name=fname,
            storage_class=StorageClass.NONE,
            is_const_qualified=True,
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["is_const"] is True, "const int MAX must have is_const=True"


# ---------------------------------------------------------------------------
# SC2 — constexpr int LIMIT = 42  →  is_constexpr=True, is_const=True  (S1-3 AC2, SC2)
# ---------------------------------------------------------------------------


class TestConstexprVar:
    def test_constexpr_implies_both_flags(self, tmp_path: Path) -> None:
        """``constexpr int LIMIT = 42`` → ``is_constexpr=True`` AND ``is_const=True``.

        is_constexpr() is absent on pinned libclang; token-scan fallback fires.
        (S1-3 AC2, SC2, design §4.1)
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@LIMIT"
        # is_const_qualified True because constexpr implies const at the type level.
        # Token scan will find "constexpr" in extra_tokens.
        cursor = _make_var_cursor(
            usr=usr,
            spelling="LIMIT",
            file_name=fname,
            storage_class=StorageClass.NONE,
            is_const_qualified=True,
            is_constexpr_available=False,  # absent on pinned libclang
            extra_tokens=["constexpr", "int"],
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["is_constexpr"] is True, "constexpr var must have is_constexpr=True"
        assert node["props"]["is_const"] is True, "constexpr implies is_const=True (SC2, §4.1)"


# ---------------------------------------------------------------------------
# SC3 — static int file_var = 0  →  is_static=True, storage_class="static"  (S1-3 AC3, SC3)
# ---------------------------------------------------------------------------


class TestStaticVar:
    def test_static_var_is_static_and_storage_class(self, tmp_path: Path) -> None:
        """``static int file_var = 0`` → ``is_static=True``, ``storage_class="static"``.

        (S1-3 AC3, SC3)
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@file_var"
        cursor = _make_var_cursor(
            usr=usr,
            spelling="file_var",
            file_name=fname,
            storage_class=StorageClass.STATIC,
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["is_static"] is True, "static var must have is_static=True"
        assert node["props"]["storage_class"] == "static", (
            f"Expected storage_class='static', got {node['props']['storage_class']!r}"
        )


# ---------------------------------------------------------------------------
# SC4 — extern int shared_val  →  storage_class="extern"  (S1-3 AC4, SC4)
# ---------------------------------------------------------------------------


class TestExternVar:
    def test_extern_var_storage_class(self, tmp_path: Path) -> None:
        """``extern int shared_val`` → ``storage_class="extern"``. (S1-3 AC4, SC4)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@shared_val"
        cursor = _make_var_cursor(
            usr=usr,
            spelling="shared_val",
            file_name=fname,
            storage_class=StorageClass.EXTERN,
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["storage_class"] == "extern", (
            f"Expected storage_class='extern', got {node['props']['storage_class']!r}"
        )


# ---------------------------------------------------------------------------
# SC5 — thread_local int tls = 0  →  storage_class="thread_local"  (S1-3 AC5, SC5)
# ---------------------------------------------------------------------------


class TestThreadLocalVar:
    def test_thread_local_via_token_scan(self, tmp_path: Path) -> None:
        """``thread_local int tls = 0`` → ``storage_class="thread_local"``.

        No THREAD_LOCAL enum in pinned libclang; token-scan fallback fires.
        is_thread_local attr also absent — confirmed in P2 probe.
        (S1-3 AC5, SC5, design §4.3)
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@tls"
        # StorageClass.NONE because libclang doesn't have THREAD_LOCAL.
        # Token "thread_local" in extra_tokens triggers the scan fallback.
        cursor = _make_var_cursor(
            usr=usr,
            spelling="tls",
            file_name=fname,
            storage_class=StorageClass.NONE,
            is_thread_local_available=False,
            extra_tokens=["thread_local", "int"],
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["storage_class"] == "thread_local", (
            f"Expected storage_class='thread_local', got {node['props']['storage_class']!r}"
        )


# ---------------------------------------------------------------------------
# SC6 — non-static class member int value  →  is_static=False  (S1-3 AC6, SC6)
# ---------------------------------------------------------------------------


class TestNonStaticFieldIsStatic:
    def test_non_static_field_is_static_false(self, tmp_path: Path) -> None:
        """Non-static class member ``int value`` → ``is_static=False``. (S1-3 AC6, SC6)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field_usr = "c:@S@MyClass@FI@value"
        field = _make_field_cursor(
            usr=field_usr,
            spelling="value",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        cls = _make_class_cursor(
            usr="c:@S@MyClass",
            spelling="MyClass",
            file_name=fname,
            children=[field],
        )
        tu = _make_tu(source, [cls])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, field_usr)
        assert node["label"] == NODE_FIELD
        assert node["props"]["is_static"] is False, (
            "Non-static field must have is_static=False (SC6)"
        )


# ---------------------------------------------------------------------------
# SC7 — plain int plain_var = 0  →  storage_class="none"  (S1-3 AC7, SC7)
# ---------------------------------------------------------------------------


class TestPlainVar:
    def test_plain_var_storage_class_none(self, tmp_path: Path) -> None:
        """Plain ``int plain_var = 0`` → ``storage_class="none"``. (S1-3 AC7, SC7)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@plain_var"
        cursor = _make_var_cursor(
            usr=usr,
            spelling="plain_var",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["storage_class"] == "none", (
            f"Plain var must have storage_class='none', got {node['props']['storage_class']!r}"
        )


# ---------------------------------------------------------------------------
# EC4 — int mutable_var = 0  →  is_const=False, is_constexpr=False  (S1-3 EC4)
# ---------------------------------------------------------------------------


class TestMutableVar:
    def test_mutable_var_false_flags(self, tmp_path: Path) -> None:
        """Plain mutable ``int mutable_var = 0`` → ``is_const=False``, ``is_constexpr=False``.

        (S1-3 EC4)
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@mutable_var"
        cursor = _make_var_cursor(
            usr=usr,
            spelling="mutable_var",
            file_name=fname,
            storage_class=StorageClass.NONE,
            is_const_qualified=False,
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["props"]["is_const"] is False, "Mutable var must have is_const=False (EC4)"
        assert node["props"]["is_constexpr"] is False, (
            "Mutable var must have is_constexpr=False (EC4)"
        )


# ---------------------------------------------------------------------------
# EC2 — non-static Field.storage_class == "none"  (ADR-25 D6, S1-3 EC2)
# ---------------------------------------------------------------------------


class TestFieldStorageClassNone:
    def test_non_static_field_storage_class_none(self, tmp_path: Path) -> None:
        """Non-static ``Field`` always has ``storage_class="none"`` (ADR-25 D6, S1-3 EC2).

        D6: storage_class on Field is forced to "none" unconditionally.
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field_usr = "c:@S@Config@FI@timeout"
        field = _make_field_cursor(
            usr=field_usr,
            spelling="timeout",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        cls = _make_class_cursor(
            usr="c:@S@Config",
            spelling="Config",
            file_name=fname,
            children=[field],
        )
        tu = _make_tu(source, [cls])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, field_usr)
        assert node["label"] == NODE_FIELD
        assert node["props"]["storage_class"] == "none", (
            f"Non-static Field must have storage_class='none' (D6, EC2), "
            f"got {node['props']['storage_class']!r}"
        )


# ---------------------------------------------------------------------------
# EC1 — extern thread_local int ext_tls  →  storage_class="thread_local"  (S1-3 EC1)
# ---------------------------------------------------------------------------


class TestExternThreadLocal:
    def test_extern_thread_local_resolves_to_thread_local(self, tmp_path: Path) -> None:
        """``extern thread_local int ext_tls`` → ``storage_class="thread_local"``.

        thread_local takes priority over extern when both are present (EC1, design §4.3).
        Token-scan fallback fires because libclang has no THREAD_LOCAL enum.
        (S1-3 EC1)
        """
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@ext_tls"
        # storage_class is EXTERN from libclang's perspective (no THREAD_LOCAL enum).
        # Token scan must find "thread_local" and return it before the enum is consulted.
        cursor = _make_var_cursor(
            usr=usr,
            spelling="ext_tls",
            file_name=fname,
            storage_class=StorageClass.EXTERN,
            is_thread_local_available=False,
            extra_tokens=["extern", "thread_local", "int"],
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert node["label"] == NODE_GLOBAL_VARIABLE
        assert node["props"]["storage_class"] == "thread_local", (
            f"extern thread_local must resolve to 'thread_local' (EC1, design §4.3), "
            f"got {node['props']['storage_class']!r}"
        )


# ---------------------------------------------------------------------------
# Parametrized sanity: all Field/GlobalVariable nodes have the four properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prop_key",
    ["is_const", "is_constexpr", "is_static", "storage_class"],
)
class TestPropertyPresence:
    def test_global_variable_has_property(self, tmp_path: Path, prop_key: str) -> None:
        """Every GlobalVariable node must carry all four P4 properties."""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        usr = "c:@g_var"
        cursor = _make_var_cursor(
            usr=usr,
            spelling="g_var",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        tu = _make_tu(source, [cursor])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, usr)
        assert prop_key in node["props"], f"GlobalVariable node must carry property {prop_key!r}"

    def test_field_has_property(self, tmp_path: Path, prop_key: str) -> None:
        """Every Field node must carry all four P4 properties."""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "test.cpp"
        source.write_text("")
        fname = str(source)

        field_usr = "c:@S@Holder@FI@x"
        field = _make_field_cursor(
            usr=field_usr,
            spelling="x",
            file_name=fname,
            storage_class=StorageClass.NONE,
        )
        cls = _make_class_cursor(
            usr="c:@S@Holder",
            spelling="Holder",
            file_name=fname,
            children=[field],
        )
        tu = _make_tu(source, [cls])
        nodes, _ = extract_nodes_and_edges(tu, source)

        node = _node_for_usr(nodes, field_usr)
        assert node["label"] == NODE_FIELD
        assert prop_key in node["props"], f"Field node must carry property {prop_key!r}"
