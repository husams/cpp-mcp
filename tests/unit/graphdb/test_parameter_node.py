"""P3 — Parameter node + HAS_PARAM edge + PARM_DECL reclassification (SC-C-01..SC-C-10).
P4 — OF_TYPE on Parameter (SC-D-01) and RETURNS on Function (SC-E-01..SC-E-05).

Covers ADR-26 D5 (ctor/dtor RETURNS void), D6 (synthetic positional USR),
D9 (PARM_DECL → Parameter), design §2.6 (_render_default_value), §3.2, §3.3.

All fixtures use MagicMock; real libclang is not required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import _render_default_value, extract_nodes_and_edges
from cpp_mcp.graphdb.schema import (
    EDGE_HAS_PARAM,
    EDGE_OF_TYPE,
    EDGE_RETURNS,
    NODE_FUNCTION,
    NODE_PARAMETER,
    NODE_TYPE,
)

# ---------------------------------------------------------------------------
# Fake cursor / TU helpers
# ---------------------------------------------------------------------------


def _make_token(spelling: str) -> Any:
    tok = MagicMock()
    tok.spelling = spelling
    return tok


def _make_param_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    default_tokens: list[str] | None = None,
) -> Any:
    """Build a fake PARM_DECL cursor.

    *default_tokens*: if provided, list of token spellings (e.g. ["=", "0"]) to simulate
    a default value.  If None or omitted, get_tokens() returns [] → default_value == "".
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
    cursor.location.column = 10
    cursor.get_children.return_value = []
    cursor.get_tokens.return_value = [_make_token(t) for t in (default_tokens or [])]
    cursor.referenced = None
    return cursor


def _make_func_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    params: list[Any],
    kind_name: str = "FUNCTION_DECL",
    return_type_spelling: str = "void",
) -> Any:
    """Build a fake function cursor that exposes *params* via get_arguments().

    P3 emits Parameters via the get_arguments() enumeration, NOT via child recursion.
    get_children() returns [] to avoid the PARM_DECL appearing in generic traversal.
    P4: *return_type_spelling* controls the result_type used for RETURNS edge emission.
    """
    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = False
    cursor.type.spelling = f"{return_type_spelling} (...)"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.get_arguments.return_value = params
    cursor.referenced = None
    # P4: result_type drives _get_or_create_type for the RETURNS edge.
    cursor.result_type = MagicMock()
    cursor.result_type.spelling = return_type_spelling
    cursor.result_type.kind = MagicMock()
    cursor.result_type.kind.name = "VOID" if return_type_spelling == "void" else "INT"
    cursor.result_type.is_const_qualified.return_value = False
    cursor.result_type.is_volatile_qualified.return_value = False
    cursor.result_type.get_pointee.return_value = None
    return cursor


def _make_class_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    children: list[Any],
) -> Any:
    cursor = MagicMock()
    cursor.kind.name = "CLASS_DECL"
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


def _param_nodes(nodes: list[Any]) -> list[Any]:
    return [n for n in nodes if n["label"] == NODE_PARAMETER]


def _has_param_edges(edges: list[Any]) -> list[Any]:
    return [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM]


def _func_node(nodes: list[Any]) -> Any | None:
    for n in nodes:
        if n["label"] == NODE_FUNCTION:
            return n
    return None


# ---------------------------------------------------------------------------
# SC-C-01 — 3-parameter function: correct index and name on each Parameter
# ---------------------------------------------------------------------------


class TestThreeParamFunction:
    """SC-C-01: Function with 3 parameters → 3 Parameter nodes with correct index/name."""

    def test_three_params_emit_three_parameter_nodes(self, tmp_path: Path) -> None:
        source = tmp_path / "add.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@add#I#d#&1S"
        params = [
            _make_param_cursor(usr=f"c:add@p{i}", spelling=name, file_name=fname)
            for i, name in enumerate(["a", "b", "c"])
        ]
        func = _make_func_cursor(usr=fn_usr, spelling="add", file_name=fname, params=params)
        tu = _make_tu(source, [func])

        nodes, _edges = extract_nodes_and_edges(tu, source)

        p_nodes = _param_nodes(nodes)
        assert len(p_nodes) == 3, f"Expected 3 Parameter nodes, got {len(p_nodes)}"

    def test_three_params_correct_index_and_name(self, tmp_path: Path) -> None:
        source = tmp_path / "add.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@add#I#d#&1S"
        expected = [("a", 0), ("b", 1), ("c", 2)]
        params = [
            _make_param_cursor(usr=f"c:add@p{i}", spelling=name, file_name=fname)
            for i, (name, _) in enumerate(expected)
        ]
        func = _make_func_cursor(usr=fn_usr, spelling="add", file_name=fname, params=params)
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        for name, idx in expected:
            synthetic_usr = f"{fn_usr}#param:{idx}"
            matching = [n for n in nodes if n["usr"] == synthetic_usr]
            assert matching, f"No Parameter node with synthetic USR {synthetic_usr!r}"
            p = matching[0]
            assert p["props"]["name"] == name, f"Expected name={name!r}, got {p['props']['name']!r}"
            assert p["props"]["index"] == idx, f"Expected index={idx}, got {p['props']['index']}"


# ---------------------------------------------------------------------------
# SC-C-02 — unnamed parameters: name == ""
# ---------------------------------------------------------------------------


class TestUnnamedParameter:
    """SC-C-02: Unnamed parameter emits Parameter with name=""."""

    def test_unnamed_param_name_is_empty_string(self, tmp_path: Path) -> None:
        source = tmp_path / "proc.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@process#I#d"
        params = [
            _make_param_cursor(usr=f"c:proc@p{i}", spelling="", file_name=fname) for i in range(2)
        ]
        func = _make_func_cursor(usr=fn_usr, spelling="process", file_name=fname, params=params)
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        for idx in range(2):
            synthetic_usr = f"{fn_usr}#param:{idx}"
            matching = [n for n in nodes if n["usr"] == synthetic_usr]
            assert matching, f"No Parameter node for unnamed param #{idx}"
            p = matching[0]
            assert p["props"]["name"] == "", (
                f"Unnamed param #{idx} must have name='', got {p['props']['name']!r}"
            )
            # spelling for unnamed gets the debug placeholder
            assert p["props"]["spelling"] == f"<param#{idx}>", (
                f"Unnamed param #{idx} must have spelling='<param#{idx}>', "
                f"got {p['props']['spelling']!r}"
            )


# ---------------------------------------------------------------------------
# SC-C-03 — default value stored as source-text string
# ---------------------------------------------------------------------------


class TestDefaultValueStorage:
    """SC-C-03: Parameter with default value → default_value is source-text spelling."""

    def test_integer_default_value(self, tmp_path: Path) -> None:
        """void resize(int n = 0) → default_value == "0"."""
        source = tmp_path / "resize.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@resize#I#b"
        param_n = _make_param_cursor(
            usr="c:resize@n", spelling="n", file_name=fname, default_tokens=["=", "0"]
        )
        func = _make_func_cursor(usr=fn_usr, spelling="resize", file_name=fname, params=[param_n])
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        synthetic_usr = f"{fn_usr}#param:0"
        matching = [n for n in nodes if n["usr"] == synthetic_usr]
        assert matching
        assert matching[0]["props"]["default_value"] == "0"

    def test_bool_default_value(self, tmp_path: Path) -> None:
        """void resize(bool clear = true) → default_value == "true"."""
        source = tmp_path / "resize2.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@resize2#b"
        param_cl = _make_param_cursor(
            usr="c:resize2@cl", spelling="clear", file_name=fname, default_tokens=["=", "true"]
        )
        func = _make_func_cursor(usr=fn_usr, spelling="resize2", file_name=fname, params=[param_cl])
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        synthetic_usr = f"{fn_usr}#param:0"
        matching = [n for n in nodes if n["usr"] == synthetic_usr]
        assert matching
        assert matching[0]["props"]["default_value"] == "true"


# ---------------------------------------------------------------------------
# SC-C-04 — parameter without default → default_value == ""
# ---------------------------------------------------------------------------


class TestNoDefaultValue:
    """SC-C-04: Parameter without default value → default_value=""."""

    def test_no_default_value_is_empty_string(self, tmp_path: Path) -> None:
        source = tmp_path / "foo.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@foo#I"
        param = _make_param_cursor(usr="c:foo@x", spelling="x", file_name=fname)
        func = _make_func_cursor(usr=fn_usr, spelling="foo", file_name=fname, params=[param])
        tu = _make_tu(source, [func])

        nodes, _ = extract_nodes_and_edges(tu, source)

        synthetic_usr = f"{fn_usr}#param:0"
        matching = [n for n in nodes if n["usr"] == synthetic_usr]
        assert matching
        assert matching[0]["props"]["default_value"] == "", (
            f"Expected default_value='', got {matching[0]['props']['default_value']!r}"
        )


# ---------------------------------------------------------------------------
# SC-C-05 — HAS_PARAM edge index property equals Parameter.index
# ---------------------------------------------------------------------------


class TestHasParamEdgeIndex:
    """SC-C-05: HAS_PARAM edge index property equals the Parameter node index."""

    def test_has_param_edge_index_matches_parameter_index(self, tmp_path: Path) -> None:
        source = tmp_path / "swap.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@swap#&I#&I"
        params = [
            _make_param_cursor(usr=f"c:swap@{name}", spelling=name, file_name=fname)
            for name in ["a", "b"]
        ]
        func = _make_func_cursor(usr=fn_usr, spelling="swap", file_name=fname, params=params)
        tu = _make_tu(source, [func])

        _nodes, edges = extract_nodes_and_edges(tu, source)

        hp_edges = _has_param_edges(edges)
        assert len(hp_edges) == 2, f"Expected 2 HAS_PARAM edges, got {len(hp_edges)}"

        for idx in range(2):
            synthetic_usr = f"{fn_usr}#param:{idx}"
            edge = next((e for e in hp_edges if e["target_usr"] == synthetic_usr), None)
            assert edge is not None, f"No HAS_PARAM edge targeting {synthetic_usr!r}"
            assert edge["props"]["index"] == idx, (
                f"HAS_PARAM edge for param#{idx} must have index={idx}, "
                f"got {edge['props']['index']}"
            )


# ---------------------------------------------------------------------------
# SC-C-06 — CXX_METHOD emits HAS_PARAM edges
# ---------------------------------------------------------------------------


class TestMethodHasParam:
    """SC-C-06: Member function emits HAS_PARAM edges to its Parameter nodes."""

    def test_method_has_param_edges(self, tmp_path: Path) -> None:
        source = tmp_path / "foo_class.cpp"
        source.write_text("")
        fname = str(source)

        cls_usr = "c:@S@Foo"
        fn_usr = "c:@S@Foo@F@bar#I#I#"
        params = [
            _make_param_cursor(usr=f"c:Foo@bar@p{i}", spelling=name, file_name=fname)
            for i, name in enumerate(["x", "y"])
        ]
        method = _make_func_cursor(
            usr=fn_usr, spelling="bar", file_name=fname, params=params, kind_name="CXX_METHOD"
        )
        cls = _make_class_cursor(usr=cls_usr, spelling="Foo", file_name=fname, children=[method])
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        p_nodes = _param_nodes(nodes)
        assert len(p_nodes) == 2, f"Expected 2 Parameter nodes, got {len(p_nodes)}"

        hp_edges = [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM]
        assert len(hp_edges) == 2, f"Expected 2 HAS_PARAM edges from method, got {len(hp_edges)}"


# ---------------------------------------------------------------------------
# SC-C-07 — CONSTRUCTOR emits HAS_PARAM edges
# ---------------------------------------------------------------------------


class TestConstructorHasParam:
    """SC-C-07: Constructor emits HAS_PARAM edges to its Parameter nodes."""

    def test_constructor_has_param_edges(self, tmp_path: Path) -> None:
        source = tmp_path / "widget.cpp"
        source.write_text("")
        fname = str(source)

        cls_usr = "c:@S@Widget"
        ctor_usr = "c:@S@Widget@F@Widget#I#I#"
        params = [
            _make_param_cursor(usr=f"c:Widget@ctor@p{i}", spelling=name, file_name=fname)
            for i, name in enumerate(["width", "height"])
        ]
        ctor = _make_func_cursor(
            usr=ctor_usr,
            spelling="Widget",
            file_name=fname,
            params=params,
            kind_name="CONSTRUCTOR",
        )
        cls = _make_class_cursor(usr=cls_usr, spelling="Widget", file_name=fname, children=[ctor])
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        p_nodes = _param_nodes(nodes)
        assert len(p_nodes) == 2

        hp_edges = [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM]
        assert len(hp_edges) == 2
        names = {n["props"]["name"] for n in p_nodes}
        assert names == {"width", "height"}


# ---------------------------------------------------------------------------
# SC-C-08 — DESTRUCTOR has 0 HAS_PARAM edges
# ---------------------------------------------------------------------------


class TestDestructorHasParam:
    """SC-C-08: Destructor emits 0 HAS_PARAM edges (destructors have no parameters)."""

    def test_destructor_zero_has_param_edges(self, tmp_path: Path) -> None:
        source = tmp_path / "widget_dtor.cpp"
        source.write_text("")
        fname = str(source)

        cls_usr = "c:@S@Widget"
        dtor_usr = "c:@S@Widget@F@~Widget#"
        dtor = _make_func_cursor(
            usr=dtor_usr,
            spelling="~Widget",
            file_name=fname,
            params=[],  # destructors have no parameters
            kind_name="DESTRUCTOR",
        )
        cls = _make_class_cursor(usr=cls_usr, spelling="Widget", file_name=fname, children=[dtor])
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        hp_edges = [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM]
        assert len(hp_edges) == 0, f"Destructor must have 0 HAS_PARAM edges, got {len(hp_edges)}"

        p_nodes = _param_nodes(nodes)
        assert len(p_nodes) == 0, f"Destructor must produce 0 Parameter nodes, got {len(p_nodes)}"


# ---------------------------------------------------------------------------
# SC-C-09 — Source declaration order preserved by index
# ---------------------------------------------------------------------------


class TestParameterSourceOrder:
    """SC-C-09: Parameters sorted by HAS_PARAM index appear in source declaration order."""

    def test_parameter_order_matches_source(self, tmp_path: Path) -> None:
        source = tmp_path / "build.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@build#*c#I#b"
        expected_order = ["name", "version", "debug"]
        params = [
            _make_param_cursor(usr=f"c:build@p{i}", spelling=name, file_name=fname)
            for i, name in enumerate(expected_order)
        ]
        func = _make_func_cursor(usr=fn_usr, spelling="build", file_name=fname, params=params)
        tu = _make_tu(source, [func])

        nodes, edges = extract_nodes_and_edges(tu, source)

        # Sort by HAS_PARAM.index and verify order matches source
        hp_edges = sorted(
            [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM],
            key=lambda e: e["props"]["index"],
        )
        assert len(hp_edges) == 3

        for idx, (edge, expected_name) in enumerate(zip(hp_edges, expected_order, strict=True)):
            param_node = next((n for n in nodes if n["usr"] == edge["target_usr"]), None)
            assert param_node is not None
            assert param_node["props"]["name"] == expected_name, (
                f"At index {idx}: expected name={expected_name!r}, "
                f"got {param_node['props']['name']!r}"
            )


# ---------------------------------------------------------------------------
# SC-C-10 — Zero-parameter function: no HAS_PARAM edges, no Parameter nodes
# ---------------------------------------------------------------------------


class TestZeroParamFunction:
    """SC-C-10: Function with no parameters → 0 HAS_PARAM edges and 0 Parameter nodes."""

    def test_zero_params_produce_no_has_param_or_parameter(self, tmp_path: Path) -> None:
        source = tmp_path / "empty.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@doNothing"
        func = _make_func_cursor(usr=fn_usr, spelling="doNothing", file_name=fname, params=[])
        tu = _make_tu(source, [func])

        nodes, edges = extract_nodes_and_edges(tu, source)

        hp_edges = [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM]
        assert len(hp_edges) == 0, f"Expected 0 HAS_PARAM edges, got {len(hp_edges)}"

        p_nodes = _param_nodes(nodes)
        assert len(p_nodes) == 0, f"Expected 0 Parameter nodes, got {len(p_nodes)}"


# ---------------------------------------------------------------------------
# Unit tests for _render_default_value helper (design §2.6)
# ---------------------------------------------------------------------------


class TestRenderDefaultValue:
    """Unit tests for _render_default_value helper (design §2.6)."""

    def test_no_tokens_returns_empty(self) -> None:
        param = MagicMock()
        param.get_tokens.return_value = []
        assert _render_default_value(param) == ""

    def test_no_equals_token_returns_empty(self) -> None:
        param = MagicMock()
        param.get_tokens.return_value = [_make_token("x")]
        assert _render_default_value(param) == ""

    def test_single_token_default(self) -> None:
        param = MagicMock()
        param.get_tokens.return_value = [_make_token("="), _make_token("0")]
        assert _render_default_value(param) == "0"

    def test_multi_token_default(self) -> None:
        param = MagicMock()
        param.get_tokens.return_value = [
            _make_token("="),
            _make_token("std"),
            _make_token("::"),
            _make_token("string"),
            _make_token("("),
            _make_token('"x"'),
            _make_token(")"),
        ]
        assert _render_default_value(param) == 'std :: string ( "x" )'

    def test_get_tokens_raises_returns_empty(self) -> None:
        param = MagicMock()
        param.get_tokens.side_effect = RuntimeError("libclang error")
        assert _render_default_value(param) == ""

    def test_bool_default(self) -> None:
        param = MagicMock()
        param.get_tokens.return_value = [_make_token("="), _make_token("true")]
        assert _render_default_value(param) == "true"


# ---------------------------------------------------------------------------
# Parametrized: all function kinds emit HAS_PARAM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind_name",
    ["FUNCTION_DECL", "CXX_METHOD", "CONSTRUCTOR", "FUNCTION_TEMPLATE"],
)
def test_all_function_kinds_emit_has_param(tmp_path: Path, kind_name: str) -> None:
    """All _FUNCTION_CURSOR_KINDS emit HAS_PARAM edges when get_arguments() is non-empty."""
    source = tmp_path / f"func_{kind_name.lower()}.cpp"
    source.write_text("")
    fname = str(source)

    fn_usr = f"c:@F@fn_{kind_name}"
    param = _make_param_cursor(usr=f"{fn_usr}@p0", spelling="x", file_name=fname)
    func = _make_func_cursor(
        usr=fn_usr, spelling=f"fn_{kind_name}", file_name=fname, params=[param], kind_name=kind_name
    )
    tu = _make_tu(source, [func])

    nodes, edges = extract_nodes_and_edges(tu, source)

    hp_edges = [e for e in edges if e["edge_type"] == EDGE_HAS_PARAM]
    assert len(hp_edges) == 1, (
        f"Expected 1 HAS_PARAM edge for kind {kind_name}, got {len(hp_edges)}"
    )
    assert _param_nodes(nodes), f"Expected 1 Parameter node for kind {kind_name}"


# ---------------------------------------------------------------------------
# Deduplication: same synthetic USR emitted only once
# ---------------------------------------------------------------------------


def test_parameter_no_duplicate_vertices(tmp_path: Path) -> None:
    """Each parameter USR is added to seen_usrs; re-processing the same function emits 1 node."""
    source = tmp_path / "dedup.cpp"
    source.write_text("")
    fname = str(source)

    fn_usr = "c:@F@dedup#I"
    param = _make_param_cursor(usr="c:dedup@p0", spelling="n", file_name=fname)
    func = _make_func_cursor(usr=fn_usr, spelling="dedup", file_name=fname, params=[param])
    tu = _make_tu(source, [func])

    nodes, _ = extract_nodes_and_edges(tu, source)

    synthetic_usr = f"{fn_usr}#param:0"
    dups = [n for n in nodes if n["usr"] == synthetic_usr]
    assert len(dups) == 1, (
        f"Expected exactly 1 Parameter node for {synthetic_usr!r}, got {len(dups)}"
    )


# ===========================================================================
# P4 — OF_TYPE edges on Parameter (SC-D-01) and RETURNS edges (SC-E-01..05)
# ===========================================================================


def _of_type_edges(edges: list[Any]) -> list[Any]:
    return [e for e in edges if e["edge_type"] == EDGE_OF_TYPE]


def _returns_edges(edges: list[Any]) -> list[Any]:
    return [e for e in edges if e["edge_type"] == EDGE_RETURNS]


def _type_nodes(nodes: list[Any]) -> list[Any]:
    return [n for n in nodes if n["label"] == NODE_TYPE]


# ---------------------------------------------------------------------------
# SC-D-01 — Parameter → OF_TYPE → Type
# ---------------------------------------------------------------------------


class TestParameterOfTypeEdge:
    """SC-D-01: Parameter node has exactly one outgoing OF_TYPE edge to its Type."""

    def test_parameter_of_type_edge_emitted(self, tmp_path: Path) -> None:
        source = tmp_path / "of_type_param.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@foo#S"
        param = _make_param_cursor(usr="c:foo@s", spelling="s", file_name=fname)
        # Override param type to a concrete spelling
        param.type = MagicMock()
        param.type.spelling = "const std::string &"
        param.type.kind = MagicMock()
        param.type.kind.name = "LVALUEREFERENCE"
        param.type.is_const_qualified.return_value = True
        param.type.is_volatile_qualified.return_value = False

        func = _make_func_cursor(
            usr=fn_usr, spelling="foo", file_name=fname, params=[param], return_type_spelling="void"
        )
        tu = _make_tu(source, [func])

        nodes, edges = extract_nodes_and_edges(tu, source)

        param_usr = f"{fn_usr}#param:0"
        of_edges = [
            e for e in edges if e["edge_type"] == EDGE_OF_TYPE and e["source_usr"] == param_usr
        ]
        assert len(of_edges) == 1, f"Expected 1 OF_TYPE edge from Parameter, got {len(of_edges)}"
        type_node = next((n for n in nodes if n["usr"] == of_edges[0]["target_usr"]), None)
        assert type_node is not None, "No Type node found at OF_TYPE target"
        assert type_node["label"] == NODE_TYPE, f"Expected Type, got {type_node['label']!r}"
        assert type_node["props"]["spelling"] == "const std::string &", (
            f"Expected spelling 'const std::string &', got {type_node['props']['spelling']!r}"
        )

    def test_parameter_of_type_exactly_one_no_duplicates(self, tmp_path: Path) -> None:
        """Each parameter emits exactly 1 OF_TYPE edge — no duplicates."""
        source = tmp_path / "of_type_dedup.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@multi#I#I"
        params = [
            _make_param_cursor(usr=f"c:multi@p{i}", spelling=f"p{i}", file_name=fname)
            for i in range(3)
        ]
        func = _make_func_cursor(
            usr=fn_usr,
            spelling="multi",
            file_name=fname,
            params=params,
            return_type_spelling="void",
        )
        tu = _make_tu(source, [func])

        _nodes, edges = extract_nodes_and_edges(tu, source)

        for idx in range(3):
            param_usr = f"{fn_usr}#param:{idx}"
            of_edges = [
                e for e in edges if e["edge_type"] == EDGE_OF_TYPE and e["source_usr"] == param_usr
            ]
            assert len(of_edges) == 1, (
                f"Parameter#{idx} must have exactly 1 OF_TYPE edge, got {len(of_edges)}"
            )


# ---------------------------------------------------------------------------
# SC-E-01 — Free function RETURNS
# ---------------------------------------------------------------------------


class TestFunctionReturnsEdge:
    """SC-E-01: Free function has exactly one outgoing RETURNS edge."""

    def test_free_function_returns_int(self, tmp_path: Path) -> None:
        """int compute(int a, int b) → RETURNS edge to Type{spelling="int"}."""
        source = tmp_path / "compute.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@compute#I#I"
        param_a = _make_param_cursor(usr="c:compute@a", spelling="a", file_name=fname)
        param_b = _make_param_cursor(usr="c:compute@b", spelling="b", file_name=fname)
        func = _make_func_cursor(
            usr=fn_usr,
            spelling="compute",
            file_name=fname,
            params=[param_a, param_b],
            return_type_spelling="int",
        )
        tu = _make_tu(source, [func])

        nodes, edges = extract_nodes_and_edges(tu, source)

        ret_edges = [
            e for e in edges if e["edge_type"] == EDGE_RETURNS and e["source_usr"] == fn_usr
        ]
        assert len(ret_edges) == 1, f"Expected 1 RETURNS edge, got {len(ret_edges)}"
        type_node = next((n for n in nodes if n["usr"] == ret_edges[0]["target_usr"]), None)
        assert type_node is not None
        assert type_node["props"]["spelling"] == "int", (
            f"Expected 'int' return type, got {type_node['props']['spelling']!r}"
        )


# ---------------------------------------------------------------------------
# SC-E-02 — Method RETURNS
# ---------------------------------------------------------------------------


class TestMethodReturnsEdge:
    """SC-E-02: CXX_METHOD has exactly one outgoing RETURNS edge."""

    def test_method_returns_int(self, tmp_path: Path) -> None:
        """int getValue() const → RETURNS edge to Type{spelling="int"}."""
        source = tmp_path / "counter.cpp"
        source.write_text("")
        fname = str(source)

        cls_usr = "c:@S@Counter"
        fn_usr = "c:@S@Counter@F@getValue#C"
        method = _make_func_cursor(
            usr=fn_usr,
            spelling="getValue",
            file_name=fname,
            params=[],
            kind_name="CXX_METHOD",
            return_type_spelling="int",
        )
        cls = _make_class_cursor(
            usr=cls_usr, spelling="Counter", file_name=fname, children=[method]
        )
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        ret_edges = [
            e for e in edges if e["edge_type"] == EDGE_RETURNS and e["source_usr"] == fn_usr
        ]
        assert len(ret_edges) == 1, f"Method must have 1 RETURNS edge, got {len(ret_edges)}"
        type_node = next((n for n in nodes if n["usr"] == ret_edges[0]["target_usr"]), None)
        assert type_node is not None
        assert type_node["props"]["spelling"] == "int"


# ---------------------------------------------------------------------------
# SC-E-03 — void return type
# ---------------------------------------------------------------------------


class TestVoidReturnsEdge:
    """SC-E-03: void function has RETURNS edge to Type{spelling="void"}."""

    def test_void_function_returns_void_type(self, tmp_path: Path) -> None:
        source = tmp_path / "reset.cpp"
        source.write_text("")
        fname = str(source)

        fn_usr = "c:@F@reset"
        func = _make_func_cursor(
            usr=fn_usr,
            spelling="reset",
            file_name=fname,
            params=[],
            return_type_spelling="void",
        )
        tu = _make_tu(source, [func])

        nodes, edges = extract_nodes_and_edges(tu, source)

        ret_edges = [
            e for e in edges if e["edge_type"] == EDGE_RETURNS and e["source_usr"] == fn_usr
        ]
        assert len(ret_edges) == 1
        type_node = next((n for n in nodes if n["usr"] == ret_edges[0]["target_usr"]), None)
        assert type_node is not None
        assert type_node["props"]["spelling"] == "void", (
            f"Expected 'void', got {type_node['props']['spelling']!r}"
        )


# ---------------------------------------------------------------------------
# SC-E-04 — Constructor RETURNS void (ADR-26 D5)
# ---------------------------------------------------------------------------


class TestConstructorReturnsEdge:
    """SC-E-04: Constructor has exactly one RETURNS edge; target Type.spelling == "void".

    ADR-26 D5: libclang returns "void" for cursor.result_type.spelling on CONSTRUCTOR
    cursors.  No special case — the natural code path Just Works.
    """

    def test_constructor_returns_void(self, tmp_path: Path) -> None:
        source = tmp_path / "widget_ctor.cpp"
        source.write_text("")
        fname = str(source)

        cls_usr = "c:@S@Widget"
        ctor_usr = "c:@S@Widget@F@Widget#I#I"
        params = [
            _make_param_cursor(usr=f"c:Widget@ctor@p{i}", spelling=name, file_name=fname)
            for i, name in enumerate(["w", "h"])
        ]
        ctor = _make_func_cursor(
            usr=ctor_usr,
            spelling="Widget",
            file_name=fname,
            params=params,
            kind_name="CONSTRUCTOR",
            return_type_spelling="void",  # ADR-26 D5: libclang gives "void" for ctors
        )
        cls = _make_class_cursor(usr=cls_usr, spelling="Widget", file_name=fname, children=[ctor])
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        ret_edges = [
            e for e in edges if e["edge_type"] == EDGE_RETURNS and e["source_usr"] == ctor_usr
        ]
        assert len(ret_edges) == 1, (
            f"Constructor must have exactly 1 RETURNS edge (ADR-26 D5), got {len(ret_edges)}"
        )
        type_node = next((n for n in nodes if n["usr"] == ret_edges[0]["target_usr"]), None)
        assert type_node is not None, "No Type node at RETURNS target for constructor"
        spelling = type_node["props"]["spelling"]
        assert spelling == "void", (
            f"Constructor RETURNS must be void per ADR-26 D5, got {spelling!r}"
        )


# ---------------------------------------------------------------------------
# SC-E-05 — Destructor RETURNS void (ADR-26 D5)
# ---------------------------------------------------------------------------


class TestDestructorReturnsEdge:
    """SC-E-05: Destructor has exactly one RETURNS edge; target Type.spelling == "void".

    ADR-26 D5: libclang returns "void" for cursor.result_type.spelling on DESTRUCTOR
    cursors.  No special case — same natural code path.
    """

    def test_destructor_returns_void(self, tmp_path: Path) -> None:
        source = tmp_path / "widget_dtor_returns.cpp"
        source.write_text("")
        fname = str(source)

        cls_usr = "c:@S@Widget"
        dtor_usr = "c:@S@Widget@F@~Widget#"
        dtor = _make_func_cursor(
            usr=dtor_usr,
            spelling="~Widget",
            file_name=fname,
            params=[],
            kind_name="DESTRUCTOR",
            return_type_spelling="void",  # ADR-26 D5: libclang gives "void" for dtors
        )
        cls = _make_class_cursor(usr=cls_usr, spelling="Widget", file_name=fname, children=[dtor])
        tu = _make_tu(source, [cls])

        nodes, edges = extract_nodes_and_edges(tu, source)

        ret_edges = [
            e for e in edges if e["edge_type"] == EDGE_RETURNS and e["source_usr"] == dtor_usr
        ]
        assert len(ret_edges) == 1, (
            f"Destructor must have exactly 1 RETURNS edge (ADR-26 D5), got {len(ret_edges)}"
        )
        type_node = next((n for n in nodes if n["usr"] == ret_edges[0]["target_usr"]), None)
        assert type_node is not None, "No Type node at RETURNS target for destructor"
        assert type_node["props"]["spelling"] == "void", (
            f"Destructor RETURNS must be void per ADR-26 D5, got {type_node['props']['spelling']!r}"
        )
