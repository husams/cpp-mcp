"""P2: VAR_DECL classifier — all VAR_DECL cursors → GlobalVariable.

Covers:
  - Namespace-scope variable (S1-1 AC2, SC2).
  - File-scope static variable (S1-1 AC2, SC2b).
  - Extern variable declaration (S1-1 AC2, SC2c).

ADR-25 D1: VAR_DECL unconditionally maps to GlobalVariable in the static table
(no runtime branching needed — contrast with FIELD_DECL which needs D7 check).

Assertion discipline (ADR-25 D2): assertions are USR-scoped. PARM_DECL nodes
(Variable) may coexist in the same TU; we never assert "no Variable globally".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_GLOBAL_VARIABLE, NODE_VARIABLE

# ---------------------------------------------------------------------------
# Fake cursor / TU helpers
# ---------------------------------------------------------------------------


def _make_var_decl_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    storage_class: Any = None,
    is_definition: bool = True,
) -> Any:
    """Build a fake VAR_DECL cursor."""
    from clang.cindex import StorageClass  # type: ignore[import-untyped]

    cursor = MagicMock()
    cursor.kind.name = "VAR_DECL"
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = is_definition
    cursor.type.spelling = "int"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 3
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.referenced = None
    cursor.storage_class = storage_class if storage_class is not None else StorageClass.NONE
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


# ---------------------------------------------------------------------------
# Parametrized test cases
# ---------------------------------------------------------------------------

_VAR_DECL_CASES = [
    pytest.param(
        "c:@counter",
        "counter",
        None,  # StorageClass.NONE → plain namespace-scope variable
        True,
        id="namespace_scope_var",
    ),
    pytest.param(
        "c:@file_count",
        "file_count",
        "STATIC",
        True,
        id="file_scope_static",
    ),
    pytest.param(
        "c:@shared_val",
        "shared_val",
        "EXTERN",
        False,  # extern declaration — is_definition=False
        id="extern_declaration",
    ),
]


class TestVarDeclClassification:
    """All VAR_DECL cursors → GlobalVariable (S1-1 AC2, SC2/SC2b/SC2c)."""

    @pytest.mark.parametrize("usr,spelling,sc_name,is_def", _VAR_DECL_CASES)
    def test_var_decl_produces_global_variable(
        self,
        tmp_path: Path,
        usr: str,
        spelling: str,
        sc_name: str | None,
        is_def: bool,
    ) -> None:
        """VAR_DECL cursor → exactly one GlobalVariable node for that USR."""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "globals.cpp"
        source.write_text("")
        fname = str(source)

        sc = getattr(StorageClass, sc_name) if sc_name else StorageClass.NONE
        var = _make_var_decl_cursor(
            usr=usr,
            spelling=spelling,
            file_name=fname,
            storage_class=sc,
            is_definition=is_def,
        )
        tu = _make_tu(source, [var])

        nodes, _ = extract_nodes_and_edges(tu, source)

        nodes_for_usr = [n for n in nodes if n["usr"] == usr]
        assert len(nodes_for_usr) == 1, (
            f"Expected exactly 1 node for USR {usr!r}, got {nodes_for_usr}"
        )
        assert nodes_for_usr[0]["label"] == NODE_GLOBAL_VARIABLE, (
            f"VAR_DECL must produce GlobalVariable, got {nodes_for_usr[0]['label']!r} "
            f"(case: {spelling!r}, storage={sc_name})"
        )

    @pytest.mark.parametrize("usr,spelling,sc_name,is_def", _VAR_DECL_CASES)
    def test_var_decl_not_classified_as_variable(
        self,
        tmp_path: Path,
        usr: str,
        spelling: str,
        sc_name: str | None,
        is_def: bool,
    ) -> None:
        """VAR_DECL USR must not appear as legacy Variable. (ADR-25 D1, USR-scoped)"""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "globals.cpp"
        source.write_text("")
        fname = str(source)

        sc = getattr(StorageClass, sc_name) if sc_name else StorageClass.NONE
        var = _make_var_decl_cursor(
            usr=usr,
            spelling=spelling,
            file_name=fname,
            storage_class=sc,
            is_definition=is_def,
        )
        tu = _make_tu(source, [var])

        nodes, _ = extract_nodes_and_edges(tu, source)

        variable_for_usr = [n for n in nodes if n["usr"] == usr and n["label"] == NODE_VARIABLE]
        assert not variable_for_usr, (
            f"VAR_DECL USR {usr!r} must not produce Variable node (D1); found: {variable_for_usr}"
        )

    def test_multiple_var_decls_all_global_variable(self, tmp_path: Path) -> None:
        """Multiple VAR_DECL in same TU all classify as GlobalVariable."""
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        source = tmp_path / "multi.cpp"
        source.write_text("")
        fname = str(source)

        usrs = ["c:@g_a", "c:@g_b", "c:@g_c"]
        cursors = [
            _make_var_decl_cursor(
                usr=u,
                spelling=f"g_{i}",
                file_name=fname,
                storage_class=StorageClass.NONE,
            )
            for i, u in enumerate(usrs)
        ]
        tu = _make_tu(source, cursors)

        nodes, _ = extract_nodes_and_edges(tu, source)

        for usr in usrs:
            matches = [n for n in nodes if n["usr"] == usr]
            assert matches and matches[0]["label"] == NODE_GLOBAL_VARIABLE, (
                f"USR {usr!r} must be GlobalVariable"
            )
