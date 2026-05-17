"""QA addition — S2 parametrized boundary tests (cpp-mcp-v7-s2).

Category: property-based / parametrised (mandatory addition category 2).

Covers:
  - Type dedup invariant: K function declarations sharing M distinct canonical
    spellings produce exactly M Type nodes regardless of K (SC-A-02..SC-A-05,
    ADR-26 D2/D3).  Parametrised over (K, M) pairs spanning the boundary:
    (1,1), (2,1), (5,1), (2,2), (5,3), (10,4).
  - SC-D-05: mixed-symbol OF_TYPE completeness — GlobalVariable + Field +
    Parameter each emit exactly 1 OF_TYPE edge in a single TU with no
    duplicates.  The scenarios.md SC-D-05 combined assertion is not covered
    by per-symbol individual tests; this test provides the combined check.
  - USR-collision boundary: two distinct spellings must never produce the
    same USR (ADR-26 D1).  Parametrised over 10 pairs from the S2 type
    vocabulary used in test fixtures.

References:
  scenarios.md: SC-A-03, SC-A-04, SC-A-05, SC-D-05
  ADR-26: D1 (USR), D2 (source-form spelling), D3 (per-export dedup)
  plan.md §P2, §P4
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import _type_usr, extract_nodes_and_edges
from cpp_mcp.graphdb.schema import (
    EDGE_OF_TYPE,
    NODE_TYPE,
)

# ---------------------------------------------------------------------------
# Shared fake-cursor helpers (mirror pattern from test_type_node.py)
# ---------------------------------------------------------------------------


def _make_type(
    *,
    spelling: str,
    kind_name: str = "INT",
    is_const: bool = False,
    is_volatile: bool = False,
    pointee: Any = None,
) -> Any:
    from clang.cindex import TypeKind  # type: ignore[import-untyped]

    t = MagicMock()
    t.spelling = spelling
    t.kind = getattr(TypeKind, kind_name)
    t.is_const_qualified.return_value = is_const
    t.is_volatile_qualified.return_value = is_volatile
    if pointee is not None:
        t.get_pointee.return_value = pointee
    else:
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
    params: list[Any] | None = None,
) -> Any:
    from clang.cindex import (  # type: ignore[import-untyped]
        ExceptionSpecificationKind,
        RefQualifierKind,
    )

    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.displayname = spelling
    cursor.is_definition.return_value = False
    cursor.type.spelling = spelling
    cursor.result_type = result_type
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.get_arguments.return_value = params or []
    cursor.referenced = None
    # Signature property defaults for _emit_function_signature_props
    cursor.is_const_method.return_value = False
    cursor.is_static_method.return_value = False
    cursor.is_virtual_method.return_value = False
    cursor.is_pure_virtual_method.return_value = False
    cursor.is_deleted_method.return_value = False
    cursor.is_default_method.return_value = False
    cursor.get_tokens.return_value = []
    cursor.type.get_ref_qualifier.return_value = RefQualifierKind.NONE
    cursor.exception_specification_kind = ExceptionSpecificationKind.NONE
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
# Parametrised boundary: K functions sharing M distinct canonical spellings
# → exactly M Type nodes (SC-A-03..SC-A-05, ADR-26 D3)
# ---------------------------------------------------------------------------

# Each tuple: (k_functions, m_distinct_spellings)
# We cycle through m_distinct_spellings spelling names for the k functions.
_DEDUP_CASES: list[tuple[int, list[str]]] = [
    # (k, spellings_pool)
    (1, ["int"]),  # 1 fn, 1 spelling → 1 Type
    (2, ["int"]),  # 2 fns, same int → 1 Type
    (5, ["int"]),  # 5 fns, same int → 1 Type
    (2, ["int", "double"]),  # 2 fns, 2 spellings → 2 Types
    (5, ["int", "double", "void"]),  # 5 fns cycling 3 spellings → 3 Types
    (10, ["int", "double", "float", "long"]),  # 10 fns cycling 4 spellings → 4 Types
]


@pytest.mark.parametrize("k_fns,spellings", _DEDUP_CASES)
def test_type_dedup_k_functions_m_spellings(
    tmp_path: Path, k_fns: int, spellings: list[str]
) -> None:
    """SC-A-03..SC-A-05: K function declarations sharing M distinct type spellings
    produce exactly M Type nodes — dedup invariant (ADR-26 D2/D3).

    Boundary cases: (1,1), (2,1), (5,1), (2,2), (5,3), (10,4).
    This is the parametrised category-2 mandatory addition for QA.
    """
    fname = str(tmp_path / "test.cpp")
    (tmp_path / "test.cpp").write_text("")

    _KIND_FOR_SPELLING = {
        "int": "INT",
        "double": "DOUBLE",
        "float": "FLOAT",
        "long": "LONG",
        "void": "VOID",
    }

    # Build one Type mock per distinct spelling (shared reference → same object → same USR)
    type_objects = {
        s: _make_type(spelling=s, kind_name=_KIND_FOR_SPELLING.get(s, "INT")) for s in spellings
    }

    # Build K function cursors, cycling through spellings
    cursors = [
        _make_func_cursor(
            usr=f"c:@F@f{i}",
            spelling=f"f{i}",
            file_name=fname,
            result_type=type_objects[spellings[i % len(spellings)]],
        )
        for i in range(k_fns)
    ]

    tu = _make_tu(tmp_path / "test.cpp", cursors)
    nodes, _ = extract_nodes_and_edges(tu, tmp_path / "test.cpp")

    type_nodes = [n for n in nodes if n["label"] == NODE_TYPE]
    # Each distinct spelling must appear exactly once regardless of how many
    # functions share it.
    for spelling in spellings:
        matching = [n for n in type_nodes if n["props"]["spelling"] == spelling]
        assert len(matching) == 1, (
            f"Spelling {spelling!r}: expected exactly 1 Type node with "
            f"K={k_fns} functions, got {len(matching)}"
        )

    # Total Type node count must equal M (one per distinct spelling).
    # Add 1 for the "void" return type injected by each function by default
    # ONLY if "void" is not already in spellings (the functions above have
    # their result_type set to the cycling spelling, not void).
    assert len(type_nodes) == len(spellings), (
        f"Expected {len(spellings)} distinct Type nodes for spellings {spellings!r} "
        f"with K={k_fns} functions, got {len(type_nodes)}"
    )


# ---------------------------------------------------------------------------
# USR collision boundary: distinct spellings must never produce the same USR
# (ADR-26 D1)
# ---------------------------------------------------------------------------

_USR_PAIRS = [
    ("int", "int *"),
    ("int *", "int **"),
    ("int &", "int &&"),
    ("const int", "int"),
    ("const std::string &", "const std::string"),
    ("void", "int"),
    ("double", "float"),
    ("long", "long long"),
    ("char *", "const char *"),
    ("int &", "int *"),
]


@pytest.mark.parametrize("sp_a,sp_b", _USR_PAIRS)
def test_distinct_spellings_produce_distinct_usrs(sp_a: str, sp_b: str) -> None:
    """ADR-26 D1: Two distinct type spellings must never produce the same USR.

    Boundary: 10 pairs from S2 type vocabulary; any collision is a hash defect.
    """
    usr_a = _type_usr(sp_a)
    usr_b = _type_usr(sp_b)
    assert usr_a != usr_b, (
        f"Distinct spellings {sp_a!r} and {sp_b!r} produced the same USR {usr_a!r}"
    )


# ---------------------------------------------------------------------------
# SC-D-05: combined OF_TYPE completeness — each symbol kind emits exactly 1
# OF_TYPE edge in a single TU (scenarios.md SC-D-05, S2-D.AC5)
# ---------------------------------------------------------------------------


def test_sc_d_05_combined_of_type_completeness(tmp_path: Path) -> None:
    """SC-D-05: GlobalVariable + Field + Parameter in one TU each have exactly 1 OF_TYPE edge.

    Scenarios.md SC-D-05 calls for a combined assertion across all symbol kinds.
    Individual per-kind tests exist in test_global_variable_classification.py,
    test_field_classification.py, and test_parameter_node.py; this test
    provides the combined scenario check (S2-D.AC5).

    The VAR_DECL inside the function body is classified as GlobalVariable
    per ADR-25 D2; documented inline per plan.md §P4 deviation note.
    """
    fname = str(tmp_path / "test.cpp")
    (tmp_path / "test.cpp").write_text("")

    int_type = _make_type(spelling="int", kind_name="INT")
    float_type = _make_type(spelling="float", kind_name="FLOAT")
    char_ptr_type = _make_type(
        spelling="char *",
        kind_name="POINTER",
        pointee=_make_type(spelling="char", kind_name="CHAR_S"),
    )

    # GlobalVariable: g_counter (int)
    gvar = MagicMock()
    gvar.kind.name = "VAR_DECL"
    gvar.get_usr.return_value = "c:@g_counter"
    gvar.spelling = "g_counter"
    gvar.is_definition.return_value = True
    gvar.type = int_type
    gvar.location.file = MagicMock()
    gvar.location.file.name = fname
    gvar.location.line = 1
    gvar.location.column = 1
    gvar.get_children.return_value = []
    gvar.get_tokens.return_value = []

    # Class + Field: Box.width (float)
    class_cursor = MagicMock()
    class_cursor.kind.name = "CLASS_DECL"
    class_cursor.get_usr.return_value = "c:@S@Box"
    class_cursor.spelling = "Box"
    class_cursor.is_definition.return_value = True
    class_cursor.type.spelling = "Box"
    class_cursor.location.file = MagicMock()
    class_cursor.location.file.name = fname
    class_cursor.location.line = 3
    class_cursor.location.column = 1
    class_cursor.get_tokens.return_value = []
    class_cursor.is_abstract_record.return_value = False

    field_cursor = MagicMock()
    field_cursor.kind.name = "FIELD_DECL"
    field_cursor.get_usr.return_value = "c:@S@Box@FI@width"
    field_cursor.spelling = "width"
    field_cursor.is_definition.return_value = True
    field_cursor.type = float_type
    field_cursor.location.file = MagicMock()
    field_cursor.location.file.name = fname
    field_cursor.location.line = 4
    field_cursor.location.column = 5
    field_cursor.get_children.return_value = []
    field_cursor.get_tokens.return_value = []
    field_cursor.access_specifier.name = "PRIVATE"

    class_cursor.get_children.return_value = [field_cursor]

    # Parameter: buf (char *) attached to function fn
    param_cursor = MagicMock()
    param_cursor.kind.name = "PARM_DECL"
    param_cursor.get_usr.return_value = "c:@F@fn#*c#0"
    param_cursor.spelling = "buf"
    param_cursor.is_definition.return_value = True
    param_cursor.type = char_ptr_type
    param_cursor.location.file = MagicMock()
    param_cursor.location.file.name = fname
    param_cursor.location.line = 7
    param_cursor.location.column = 13
    param_cursor.get_children.return_value = []
    param_cursor.get_tokens.return_value = []

    fn_cursor = _make_func_cursor(
        usr="c:@F@fn",
        spelling="fn",
        file_name=fname,
        result_type=_make_type(spelling="void", kind_name="VOID"),
        params=[param_cursor],
    )

    tu = _make_tu(tmp_path / "test.cpp", [gvar, class_cursor, fn_cursor])
    _nodes, edges = extract_nodes_and_edges(tu, tmp_path / "test.cpp")

    # Collect OF_TYPE edges per source USR
    of_type_edges = [e for e in edges if e["edge_type"] == EDGE_OF_TYPE]

    def _of_type_count(source_usr: str) -> int:
        return sum(1 for e in of_type_edges if e["source_usr"] == source_usr)

    # GlobalVariable: g_counter → exactly 1 OF_TYPE
    assert _of_type_count("c:@g_counter") == 1, (
        f"GlobalVariable g_counter must have exactly 1 OF_TYPE edge, "
        f"got {_of_type_count('c:@g_counter')}"
    )

    # Field: Box.width → exactly 1 OF_TYPE
    assert _of_type_count("c:@S@Box@FI@width") == 1, (
        f"Field width must have exactly 1 OF_TYPE edge, got {_of_type_count('c:@S@Box@FI@width')}"
    )

    # Parameter: buf → exactly 1 OF_TYPE.
    # The exporter builds a synthetic USR for parameters: "{fn_usr}#param:{idx}"
    # (see exporter.py line 1094).  The cursor's own USR is not used.
    param_synthetic_usr = "c:@F@fn#param:0"
    assert _of_type_count(param_synthetic_usr) == 1, (
        f"Parameter buf must have exactly 1 OF_TYPE edge (synthetic USR {param_synthetic_usr!r}), "
        f"got {_of_type_count(param_synthetic_usr)}"
    )

    # No symbol has zero OF_TYPE edges (completeness — no missing)
    symbol_usrs = {"c:@g_counter", "c:@S@Box@FI@width", param_synthetic_usr}
    for usr in symbol_usrs:
        count = _of_type_count(usr)
        assert count >= 1, f"Symbol {usr!r} has no OF_TYPE edge (expected exactly 1)"
