"""P5 — Function signature properties (SC-F-01..SC-F-12).

Covers ADR-26 D7 (signature = cursor.displayname), D10 (capability matrix),
D11 (is_noexcept semantics), design §2.4, §2.7.

Properties tested:
  - signature   : str  (cursor.displayname per ADR-26 D7)
  - is_constexpr: bool (token-scan; is_constexpr absent on pinned libclang)
  - is_noexcept : bool (exception_specification_kind; D11)
  - is_deleted  : bool (cursor.is_deleted_method())
  - is_defaulted: bool (cursor.is_default_method())
  - cv_qualifiers: str ("" | "const" | "volatile" | "const volatile")
  - ref_qualifier: str ("" | "&" | "&&")

DEFERRED: is_template (S3), is_virtual, is_override (S4).

All fixtures use MagicMock; real libclang is not required.

Libclang fallback notes (F-6 in ADR-26):
  - ExceptionSpecificationKind.NOEXCEPT_FALSE is absent on the pinned libclang.
    COMPUTED_NOEXCEPT covers both noexcept(true) and noexcept(false) at the enum level.
    Test cases use BASIC_NOEXCEPT (plain `noexcept`) and DYNAMIC_NONE (`throw()`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_FUNCTION

# ---------------------------------------------------------------------------
# Helpers to build fake cursors
# ---------------------------------------------------------------------------


def _make_token(spelling: str) -> Any:
    tok = MagicMock()
    tok.spelling = spelling
    return tok


def _make_func_cursor(
    *,
    usr: str,
    spelling: str,
    file_name: str,
    displayname: str = "",
    kind_name: str = "FUNCTION_DECL",
    tokens: list[str] | None = None,
    is_const_method: bool = False,
    is_deleted_method: bool = False,
    is_default_method: bool = False,
    exception_spec_kind: str | None = None,
    ref_qualifier_name: str = "NONE",
    has_is_constexpr: bool = False,
) -> Any:
    """Build a fake function cursor with explicit control over every P5 probe.

    Parameters
    ----------
    usr, spelling, file_name:
        Basic cursor identity fields.
    displayname:
        Returned by cursor.displayname (ADR-26 D7). Defaults to *spelling*.
    kind_name:
        CursorKind name (FUNCTION_DECL, CXX_METHOD, CONSTRUCTOR, DESTRUCTOR, …).
    tokens:
        List of token spellings for cursor.get_tokens(). Used by:
          - is_constexpr token-scan (look for "constexpr")
          - _method_has_volatile_qualifier (look for "volatile" after close-paren)
        If None, get_tokens() returns [].
    is_const_method, is_deleted_method, is_default_method:
        Return values for the corresponding cursor methods.
    exception_spec_kind:
        Name of the ExceptionSpecificationKind enum value to set on
        cursor.exception_specification_kind (e.g. "BASIC_NOEXCEPT", "NONE").
        If None, the attribute is absent (AttributeError) so is_noexcept→False.
    ref_qualifier_name:
        Name of the RefQualifierKind enum value (NONE, LVALUE, RVALUE).
    has_is_constexpr:
        If True, cursor.is_constexpr is a callable that returns False (tests
        the native path falling through to token-scan). Not set by default
        (absent on pinned libclang).
    """
    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.displayname = displayname or spelling
    cursor.is_definition.return_value = False
    cursor.type.spelling = "void (...)"
    cursor.location.file = MagicMock()
    cursor.location.file.name = file_name
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = []
    cursor.get_arguments.return_value = []
    cursor.referenced = None

    # result_type (for RETURNS edge — not focus of P5, but must not error)
    cursor.result_type = MagicMock()
    cursor.result_type.spelling = "void"
    cursor.result_type.kind = MagicMock()
    cursor.result_type.kind.name = "VOID"
    cursor.result_type.is_const_qualified.return_value = False
    cursor.result_type.is_volatile_qualified.return_value = False
    cursor.result_type.get_pointee.return_value = None

    # --- P5 probes ---
    cursor.is_const_method.return_value = is_const_method
    cursor.is_deleted_method.return_value = is_deleted_method
    cursor.is_default_method.return_value = is_default_method

    # is_constexpr: absent on pinned libclang by default
    if has_is_constexpr:
        cursor.is_constexpr.return_value = False  # callable but returns False
    else:
        del cursor.is_constexpr  # simulate absent attribute

    # exception_specification_kind: absent when not set → is_noexcept stays False
    if exception_spec_kind is not None:
        try:
            from clang.cindex import ExceptionSpecificationKind  # type: ignore[import-untyped]

            cursor.exception_specification_kind = getattr(
                ExceptionSpecificationKind, exception_spec_kind
            )
        except (ImportError, AttributeError):
            cursor.exception_specification_kind = MagicMock()
            cursor.exception_specification_kind.__eq__ = lambda self, other: False
    else:
        del cursor.exception_specification_kind

    # ref_qualifier: cursor.type.get_ref_qualifier()
    try:
        from clang.cindex import RefQualifierKind  # type: ignore[import-untyped]

        cursor.type.get_ref_qualifier.return_value = getattr(RefQualifierKind, ref_qualifier_name)
    except (ImportError, AttributeError):
        cursor.type.get_ref_qualifier.return_value = None

    # tokens for constexpr / volatile scan
    cursor.get_tokens.return_value = [_make_token(t) for t in (tokens or [])]

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


def _extract_function_node(
    file_path: Path,
    cursor: Any,
) -> dict[str, Any] | None:
    """Run extract_nodes_and_edges and return the Function node matching *cursor*."""
    tu = _make_tu(file_path, [cursor])
    nodes, _edges = extract_nodes_and_edges(tu, file_path)
    for node in nodes:
        if node["label"] == NODE_FUNCTION and node["usr"] == cursor.get_usr():
            return node
    return None


# ---------------------------------------------------------------------------
# SC-F-01 — Every Function node has all seven required signature properties
# ---------------------------------------------------------------------------


class TestAllPropertiesPresent:
    """SC-F-01: every Function node has all required S2 signature properties."""

    from typing import ClassVar

    REQUIRED_PROPS: ClassVar[set[str]] = {
        "signature",
        "is_constexpr",
        "is_noexcept",
        "is_deleted",
        "is_defaulted",
        "cv_qualifiers",
        "ref_qualifier",
    }

    def test_all_props_present_free_function(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@add",
            spelling="add",
            displayname="add(int, int)",
            file_name=str(file_path),
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None, "Function node must be created"
        for prop in self.REQUIRED_PROPS:
            assert prop in node["props"], f"Missing property: {prop}"

    def test_prop_types(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@add",
            spelling="add",
            displayname="add(int, int)",
            file_name=str(file_path),
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        props = node["props"]
        assert isinstance(props["signature"], str), "signature must be str"
        assert isinstance(props["is_constexpr"], bool), "is_constexpr must be bool"
        assert isinstance(props["is_noexcept"], bool), "is_noexcept must be bool"
        assert isinstance(props["is_deleted"], bool), "is_deleted must be bool"
        assert isinstance(props["is_defaulted"], bool), "is_defaulted must be bool"
        assert isinstance(props["cv_qualifiers"], str), "cv_qualifiers must be str"
        assert isinstance(props["ref_qualifier"], str), "ref_qualifier must be str"


# ---------------------------------------------------------------------------
# SC-F-01-sig — signature = cursor.displayname (ADR-26 D7)
# ---------------------------------------------------------------------------


class TestSignatureFormat:
    """SC-F-01-sig: signature == cursor.displayname (ADR-26 D7)."""

    def test_displayname_used_as_signature(self, tmp_path: Path) -> None:
        """ADR-26 D7: signature is cursor.displayname, not cursor.spelling."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        displayname = "foo(int, const std::string &)"
        cursor = _make_func_cursor(
            usr="c:@F@foo",
            spelling="foo",
            displayname=displayname,
            file_name=str(file_path),
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["signature"] == displayname, (
            "signature must equal cursor.displayname per ADR-26 D7"
        )

    def test_displayname_without_return_type(self, tmp_path: Path) -> None:
        """displayname omits return type per ADR-26 D7 (documented trade-off)."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@bar",
            spelling="bar",
            displayname="bar(double)",  # no return type in displayname
            file_name=str(file_path),
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["signature"] == "bar(double)"


# ---------------------------------------------------------------------------
# SC-F-02 — Free function: cv_qualifiers="" and ref_qualifier=""
# ---------------------------------------------------------------------------


class TestFreeFunctionQualifiers:
    """SC-F-02: free function has empty cv_qualifiers and ref_qualifier."""

    def test_free_function_has_empty_qualifiers(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@compute",
            spelling="compute",
            file_name=str(file_path),
            is_const_method=False,
            tokens=["void", "compute", "(", "int", "x", ")"],
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["cv_qualifiers"] == "", "Free function must have empty cv_qualifiers"
        assert node["props"]["ref_qualifier"] == "", "Free function must have empty ref_qualifier"


# ---------------------------------------------------------------------------
# SC-F-03 — const method: cv_qualifiers="const"
# ---------------------------------------------------------------------------


class TestConstMethod:
    """SC-F-03: const method → cv_qualifiers="const"."""

    def test_const_method_cv_qualifiers(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@Foo@F@getValue#",
            spelling="getValue",
            file_name=str(file_path),
            kind_name="CXX_METHOD",
            is_const_method=True,
            # tokens: no "volatile" after close-paren
            tokens=["int", "getValue", "(", ")", "const"],
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["cv_qualifiers"] == "const"


# ---------------------------------------------------------------------------
# SC-F-04 — volatile method: cv_qualifiers="volatile" (ADR-26 F-7)
# ---------------------------------------------------------------------------


class TestVolatileMethod:
    """SC-F-04: volatile method → cv_qualifiers="volatile".

    ADR-26 F-7 follow-up: includes both single-line and multi-line token forms.
    The multi-line form has "volatile" appearing on a separate logical token after
    the `)` — same treatment.
    """

    def test_volatile_method_single_line(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@Foo@F@poll#",
            spelling="poll",
            file_name=str(file_path),
            kind_name="CXX_METHOD",
            is_const_method=False,
            tokens=["void", "poll", "(", ")", "volatile", ";"],
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["cv_qualifiers"] == "volatile"

    def test_volatile_method_multiline(self, tmp_path: Path) -> None:
        """volatile appearing as a separate token (newline formatting)."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        # Token list from a multiline spelling like:
        #   void poll()
        #       volatile;
        # Tokenizer still yields "volatile" as a separate token after ")".
        cursor = _make_func_cursor(
            usr="c:@S@Foo@F@poll2#",
            spelling="poll2",
            file_name=str(file_path),
            kind_name="CXX_METHOD",
            is_const_method=False,
            tokens=["void", "poll2", "(", ")", "volatile", ";"],
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["cv_qualifiers"] == "volatile"

    def test_volatile_in_param_list_not_counted(self, tmp_path: Path) -> None:
        """volatile inside the parameter list must NOT contribute to cv_qualifiers."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        # Tokens for: void f(volatile int * p);
        # "volatile" appears before ")", so it must NOT be detected by the scan.
        cursor = _make_func_cursor(
            usr="c:@F@f",
            spelling="f",
            file_name=str(file_path),
            kind_name="FUNCTION_DECL",
            is_const_method=False,
            tokens=["void", "f", "(", "volatile", "int", "*", "p", ")", ";"],
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["cv_qualifiers"] == ""


# ---------------------------------------------------------------------------
# SC-F-05 — const volatile method: cv_qualifiers="const volatile"
# ---------------------------------------------------------------------------


class TestConstVolatileMethod:
    """SC-F-05: const volatile method → cv_qualifiers="const volatile"."""

    def test_const_volatile_method(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@Foo@F@inspect#",
            spelling="inspect",
            file_name=str(file_path),
            kind_name="CXX_METHOD",
            is_const_method=True,
            tokens=["int", "inspect", "(", ")", "const", "volatile", ";"],
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["cv_qualifiers"] == "const volatile"


# ---------------------------------------------------------------------------
# SC-F-06 — deleted function: is_deleted=True, is_defaulted=False
# ---------------------------------------------------------------------------


class TestDeletedFunction:
    """SC-F-06: deleted function (EC-9)."""

    def test_deleted_is_deleted_true(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@NoCopy@F@NoCopy#&1",
            spelling="NoCopy",
            file_name=str(file_path),
            kind_name="CONSTRUCTOR",
            is_deleted_method=True,
            is_default_method=False,
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_deleted"] is True
        assert node["props"]["is_defaulted"] is False


# ---------------------------------------------------------------------------
# SC-F-07 — defaulted function: is_defaulted=True, is_deleted=False
# ---------------------------------------------------------------------------


class TestDefaultedFunction:
    """SC-F-07: defaulted function (EC-10)."""

    def test_defaulted_is_defaulted_true(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@Widget@F@Widget#",
            spelling="Widget",
            file_name=str(file_path),
            kind_name="CONSTRUCTOR",
            is_deleted_method=False,
            is_default_method=True,
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_defaulted"] is True
        assert node["props"]["is_deleted"] is False


# ---------------------------------------------------------------------------
# SC-F-08 — constexpr function: is_constexpr=True (token-scan)
# ---------------------------------------------------------------------------


class TestConstexprFunction:
    """SC-F-08: constexpr function (ADR-26 D10; token-scan fallback).

    ``cursor.is_constexpr`` is absent on the pinned libclang; token-scan fires.
    """

    def test_constexpr_token_scan(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@square",
            spelling="square",
            file_name=str(file_path),
            # Token stream for: constexpr int square(int x) { return x * x; }
            tokens=[
                "constexpr",
                "int",
                "square",
                "(",
                "int",
                "x",
                ")",
                "{",
                "return",
                "x",
                "*",
                "x",
                ";",
                "}",
            ],
            has_is_constexpr=False,  # absent on pinned libclang
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_constexpr"] is True

    def test_non_constexpr_is_false(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@regular",
            spelling="regular",
            file_name=str(file_path),
            tokens=["int", "regular", "(", "int", "x", ")"],
            has_is_constexpr=False,
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_constexpr"] is False


# ---------------------------------------------------------------------------
# SC-F-09 — noexcept function: is_noexcept=True (ADR-26 D11)
# ---------------------------------------------------------------------------


class TestNoexceptFunction:
    """SC-F-09: noexcept semantics per ADR-26 D11.

    is_noexcept=True iff exception_specification_kind in
    {BASIC_NOEXCEPT, COMPUTED_NOEXCEPT, DYNAMIC_NONE}.
    """

    def test_basic_noexcept_is_true(self, tmp_path: Path) -> None:
        """Plain ``noexcept`` → BASIC_NOEXCEPT → is_noexcept=True."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@safeReset",
            spelling="safeReset",
            file_name=str(file_path),
            exception_spec_kind="BASIC_NOEXCEPT",
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_noexcept"] is True

    def test_dynamic_none_throw_empty_is_true(self, tmp_path: Path) -> None:
        """``throw()`` (C++03 legacy) → DYNAMIC_NONE → is_noexcept=True."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@legacyFn",
            spelling="legacyFn",
            file_name=str(file_path),
            exception_spec_kind="DYNAMIC_NONE",
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_noexcept"] is True

    def test_no_spec_is_false(self, tmp_path: Path) -> None:
        """No exception spec → is_noexcept=False."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@ordinary",
            spelling="ordinary",
            file_name=str(file_path),
            exception_spec_kind=None,  # attribute absent
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_noexcept"] is False

    def test_none_kind_is_false(self, tmp_path: Path) -> None:
        """ExceptionSpecificationKind.NONE → is_noexcept=False."""
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@noSpec",
            spelling="noSpec",
            file_name=str(file_path),
            exception_spec_kind="NONE",
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_noexcept"] is False


# ---------------------------------------------------------------------------
# SC-F-10 — lvalue ref-qualifier: ref_qualifier="&" (EC-7)
# ---------------------------------------------------------------------------


class TestLvalueRefQualifier:
    """SC-F-10: lvalue ref-qualifier (&) → ref_qualifier="&"."""

    def test_lvalue_ref_qualifier(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@Builder@F@build#&",
            spelling="build",
            file_name=str(file_path),
            kind_name="CXX_METHOD",
            ref_qualifier_name="LVALUE",
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["ref_qualifier"] == "&"


# ---------------------------------------------------------------------------
# SC-F-11 — rvalue ref-qualifier: ref_qualifier="&&" (EC-8)
# ---------------------------------------------------------------------------


class TestRvalueRefQualifier:
    """SC-F-11: rvalue ref-qualifier (&&) → ref_qualifier="&&"."""

    def test_rvalue_ref_qualifier(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@S@Builder@F@build#&&",
            spelling="build",
            file_name=str(file_path),
            kind_name="CXX_METHOD",
            ref_qualifier_name="RVALUE",
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["ref_qualifier"] == "&&"


# ---------------------------------------------------------------------------
# SC-F-12 — Regular function: is_deleted=False, is_defaulted=False
# ---------------------------------------------------------------------------


class TestRegularFunction:
    """SC-F-12: regular function has is_deleted=False and is_defaulted=False."""

    def test_regular_function_flags_false(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@F@normalFunction",
            spelling="normalFunction",
            file_name=str(file_path),
            is_deleted_method=False,
            is_default_method=False,
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert node["props"]["is_deleted"] is False
        assert node["props"]["is_defaulted"] is False


# ---------------------------------------------------------------------------
# Additional: FUNCTION_TEMPLATE also gets signature props
# ---------------------------------------------------------------------------


class TestFunctionTemplateGetsProps:
    """Function templates are in _FUNCTION_CURSOR_KINDS and must receive P5 props."""

    def test_function_template_has_signature_props(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a.cpp"
        file_path.touch()
        cursor = _make_func_cursor(
            usr="c:@FT@myMax",
            spelling="myMax",
            displayname="myMax(T, T)",
            file_name=str(file_path),
            kind_name="FUNCTION_TEMPLATE",
            is_const_method=False,
            is_deleted_method=False,
            is_default_method=False,
        )
        node = _extract_function_node(file_path, cursor)
        assert node is not None
        assert "signature" in node["props"]
        assert "is_constexpr" in node["props"]
        assert "cv_qualifiers" in node["props"]


# ---------------------------------------------------------------------------
# Additional: CXX_METHOD with no qualifiers has empty cv_qualifiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind_name",
    ["FUNCTION_DECL", "CXX_METHOD", "CONSTRUCTOR", "DESTRUCTOR"],
)
def test_all_function_kinds_have_required_props(kind_name: str, tmp_path: Path) -> None:
    """All _FUNCTION_CURSOR_KINDS emit P5 properties."""
    file_path = tmp_path / "a.cpp"
    file_path.touch()
    cursor = _make_func_cursor(
        usr=f"c:@F@fn_{kind_name}",
        spelling=f"fn_{kind_name}",
        file_name=str(file_path),
        kind_name=kind_name,
        is_const_method=False,
        is_deleted_method=False,
        is_default_method=False,
    )
    node = _extract_function_node(file_path, cursor)
    assert node is not None, f"{kind_name} must produce a Function node"
    props = node["props"]
    for key in (
        "signature",
        "is_constexpr",
        "is_noexcept",
        "is_deleted",
        "is_defaulted",
        "cv_qualifiers",
        "ref_qualifier",
    ):
        assert key in props, f"{kind_name} Function node missing property: {key}"
