"""GraphDB exporter: per-file TU walk → node/edge batches → driver upsert.

Architecture
------------
``export_file`` parses one C++ file, extracts ``NodeRecord`` / ``EdgeRecord``
batches from the libclang cursor tree, and calls the driver's upsert methods
inside per-file atomicity (per ADR-7 / US-7/AC-5):

  - Each file = one logical transaction boundary.
  - If a file fails (parse error, driver write error) the error is recorded
    in the ``errors`` list; previously-committed files stay committed (partial
    success per US-7/AC-5 — no all-or-nothing rollback).

``export_directory`` walks a directory and calls ``export_file`` for each
file whose extension is in the supported C++ extension set.

Supported extensions: ``.cpp``, ``.h``, ``.hpp``, ``.cc``, ``.cxx``.

Node extraction
---------------
Cursor kinds are mapped to schema node types:

  CursorKind           → NodeType
  ------------------------------------------
  NAMESPACE            → Namespace
  CLASS_DECL /
    STRUCT_DECL        → Class
  FUNCTION_DECL /
    CXX_METHOD /
    CONSTRUCTOR /
    DESTRUCTOR         → Function
  VAR_DECL             → GlobalVariable
  FIELD_DECL           → Field (non-static) or GlobalVariable (static, ADR-25 D7)
  PARM_DECL            → Parameter (ADR-26 D9; handled via get_arguments() loop)
  MACRO_DEFINITION     → Macro
  TYPEDEF_DECL /
    TYPE_ALIAS_DECL    → TypeAlias

A ``File`` node is always created for the source file itself.

Edge extraction
---------------
Edges are inferred during the same traversal:

  - Parent namespace/class  → DEFINES / DECLARES child symbol
  - CLASS_DECL with bases   → INHERITS base class
  - CALL_EXPR               → CALLS callee
  - INCLUSION_DIRECTIVE     → INCLUDES target file
  - FIELD_DECL / PARM_DECL  → MEMBER_OF parent class
  - File → DEFINES top-level symbols
  - DECL_REF_EXPR / MEMBER_REF_EXPR / TYPE_REF → REFERENCES from enclosing
    function/method (or file for top-level use-sites) to the referenced symbol.
    REFERENCES edges that duplicate an already-emitted CALLS edge (same
    source→target pair) are suppressed to avoid double-counting.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from pathlib import Path
from typing import Any

from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord
from cpp_mcp.graphdb.schema import (
    EDGE_CALLS,
    EDGE_DECLARES,
    EDGE_DEFINES,
    EDGE_HAS_PARAM,
    EDGE_INCLUDES,
    EDGE_INHERITS,
    EDGE_MEMBER_OF,
    EDGE_OF_TYPE,
    EDGE_POINTS_TO,
    EDGE_REFERENCES,
    EDGE_REFERS_TO,
    EDGE_RETURNS,
    NODE_CLASS,
    NODE_FIELD,
    NODE_FILE,
    NODE_FUNCTION,
    NODE_GLOBAL_VARIABLE,
    NODE_MACRO,
    NODE_NAMESPACE,
    NODE_PARAMETER,
    NODE_TYPE,
    NODE_TYPE_ALIAS,
)
from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported C++ file extensions
# ---------------------------------------------------------------------------

CPP_EXTENSIONS: frozenset[str] = frozenset({".cpp", ".h", ".hpp", ".cc", ".cxx"})

# ---------------------------------------------------------------------------
# CursorKind name → node type mapping
# ---------------------------------------------------------------------------

_KIND_TO_NODE_TYPE: dict[str, str] = {
    "NAMESPACE": NODE_NAMESPACE,
    "CLASS_DECL": NODE_CLASS,
    "STRUCT_DECL": NODE_CLASS,
    "CLASS_TEMPLATE": NODE_CLASS,
    "FUNCTION_DECL": NODE_FUNCTION,
    "CXX_METHOD": NODE_FUNCTION,
    "CONSTRUCTOR": NODE_FUNCTION,
    "DESTRUCTOR": NODE_FUNCTION,
    "FUNCTION_TEMPLATE": NODE_FUNCTION,
    "VAR_DECL": NODE_GLOBAL_VARIABLE,  # D1: VAR_DECL → GlobalVariable (ADR-25)
    "UNION_DECL": NODE_CLASS,  # ADR-26 D8: UNION_DECL → Class (record_kind="union")
    # "FIELD_DECL" is classified at runtime via _classify_field (D7 static invariant)
    "PARM_DECL": NODE_PARAMETER,  # ADR-26 D9: PARM_DECL → Parameter (S1 transitional complete)
    "MACRO_DEFINITION": NODE_MACRO,
    "TYPEDEF_DECL": NODE_TYPE_ALIAS,
    "TYPE_ALIAS_DECL": NODE_TYPE_ALIAS,
    "TYPE_ALIAS_TEMPLATE_DECL": NODE_TYPE_ALIAS,
}

# CursorKind names whose children are MEMBER_OF the parent class/struct/union.
# UNION_DECL added with ADR-26 D8 (union now maps to NODE_CLASS).
_MEMBER_PARENT_KINDS: frozenset[str] = frozenset(
    {"CLASS_DECL", "STRUCT_DECL", "CLASS_TEMPLATE", "UNION_DECL"}
)

# CursorKind names that represent a symbol use-site (non-call references).
# These do not produce nodes — only REFERENCES edges.
_REFERENCE_CURSOR_KINDS: frozenset[str] = frozenset(
    {"DECL_REF_EXPR", "MEMBER_REF_EXPR", "TYPE_REF"}
)

# CursorKind names that represent function/method definitions.
# Used to track the innermost enclosing function for REFERENCES edge source.
_FUNCTION_CURSOR_KINDS: frozenset[str] = frozenset(
    {"FUNCTION_DECL", "CXX_METHOD", "CONSTRUCTOR", "DESTRUCTOR", "FUNCTION_TEMPLATE"}
)

# ---------------------------------------------------------------------------
# Classifier helpers (ADR-25 D1, D2, D7)
# ---------------------------------------------------------------------------


def _is_static_member(cursor: Any) -> bool:
    """Return True if *cursor* is a static class data member.

    Primary path: ``cursor.is_static_member()`` (libclang ≥ 3.8).
    Fallback (F-3 per ADR-25): ``cursor.storage_class == StorageClass.STATIC``.

    On the pinned libclang used in this project, ``Cursor.is_static_member``
    is NOT available (verified at P2 implementation time — see
    implementation-notes.md §Libclang capability probe). The fallback path
    (StorageClass.STATIC) is therefore always exercised.
    """
    is_static = getattr(cursor, "is_static_member", None)
    if callable(is_static):
        try:
            return bool(is_static())
        except Exception:
            pass
    # Fallback: probe storage_class enum (always exercised on pinned libclang).
    try:
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        return bool(cursor.storage_class == StorageClass.STATIC)
    except Exception:
        return False


def _classify_field(cursor: Any) -> str:
    """Classify a FIELD_DECL cursor to Field or GlobalVariable.

    ADR-25 D7: static class data members are *unconditionally* GlobalVariable.
    If a quirk causes the invariant check to raise, log a warning and
    re-classify to GlobalVariable rather than emitting a Field with is_static.
    """
    try:
        if _is_static_member(cursor):
            return NODE_GLOBAL_VARIABLE
    except Exception:
        logger.warning(
            "_is_static_member raised for cursor %r — re-classifying to GlobalVariable (D7)",
            getattr(cursor, "spelling", "?"),
        )
        return NODE_GLOBAL_VARIABLE
    return NODE_FIELD


def _classify_node(cursor: Any) -> str | None:
    """Return the node-type label for *cursor*, or None if the kind is not schema-relevant.

    FIELD_DECL is resolved at runtime (D7 static-member invariant);
    all other kinds use the static ``_KIND_TO_NODE_TYPE`` table.
    """
    kind = _kind_name(cursor)
    if kind == "FIELD_DECL":
        return _classify_field(cursor)
    return _KIND_TO_NODE_TYPE.get(kind)


# ---------------------------------------------------------------------------
# MEMBER_OF access helper (ADR-25 D4, D5)
# ---------------------------------------------------------------------------

# Parent kinds that default to public access (struct, union per ISO C++).
_PUBLIC_DEFAULT_PARENT_KINDS: frozenset[str] = frozenset({"STRUCT_DECL", "UNION_DECL"})


def _resolve_access(cursor: Any, parent_kind: str | None) -> str:
    """Return the C++ access specifier string for a member cursor.

    Maps ``cursor.access_specifier`` (libclang ``AccessSpecifier`` enum) to
    one of ``"public"``, ``"protected"``, or ``"private"``.

    When libclang returns ``INVALID`` or ``NONE`` (e.g. for implicit specifiers
    or union members — ADR-25 D4, F-4), the default is derived from
    *parent_kind*:

      - ``STRUCT_DECL`` or ``UNION_DECL`` → ``"public"``  (ISO C++ default)
      - ``CLASS_DECL`` or ``CLASS_TEMPLATE`` → ``"private"``  (ISO C++ default)

    If ``cursor.access_specifier`` is unavailable (libclang too old), the
    parent-kind default is applied.
    """
    try:
        from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

        spec = cursor.access_specifier
        if spec == AccessSpecifier.PUBLIC:
            return "public"
        if spec == AccessSpecifier.PROTECTED:
            return "protected"
        if spec == AccessSpecifier.PRIVATE:
            return "private"
        # INVALID or NONE — fall through to parent-kind default.
    except Exception:
        pass

    # Parent-kind default (ADR-25 D4, design §4.4).
    if parent_kind in _PUBLIC_DEFAULT_PARENT_KINDS:
        return "public"
    return "private"


# ---------------------------------------------------------------------------
# Variable / field property helpers (ADR-25 D6, design §4.1-4.3)
# ---------------------------------------------------------------------------


def _var_qualifiers(cursor: Any) -> tuple[bool, bool]:
    """Return ``(is_const, is_constexpr)`` for a variable/field cursor.

    ``is_constexpr`` is read from ``cursor.is_constexpr()`` when available
    (not present on the pinned libclang — see implementation-notes.md §P4).
    Token-scan fallback checks for the ``constexpr`` keyword in the cursor
    extent.  Per design §4.1 and scenario S1-3-SC2, ``is_constexpr`` implies
    ``is_const``.
    """
    try:
        is_const = bool(cursor.type.is_const_qualified())
    except Exception:
        is_const = False

    is_constexpr = False
    method = getattr(cursor, "is_constexpr", None)
    if callable(method):
        try:
            is_constexpr = bool(method())
        except Exception:
            is_constexpr = False

    if not is_constexpr:
        # Token-scan fallback: look for the 'constexpr' keyword in cursor extent.
        try:
            for tok in cursor.get_tokens():
                if tok.spelling == "constexpr":
                    is_constexpr = True
                    break
        except Exception:
            pass

    if is_constexpr:
        is_const = True  # constexpr implies const (S1-3-SC2, design §4.1)

    return is_const, is_constexpr


def _is_storage_static(cursor: Any) -> bool:
    """Return True when *cursor* has explicit STATIC storage class (VAR_DECL).

    Used for the second clause of ``is_static`` on GlobalVariable nodes that
    originate from VAR_DECL (design §4.2, §6).
    """
    try:
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        return bool(cursor.storage_class == StorageClass.STATIC)
    except Exception:
        return False


def _storage_class_value(cursor: Any, node_type: str) -> str:
    """Map *cursor* to the emitted ``storage_class`` string.

    Priority (design §4.3, ADR-25 D6, EC1):

    1. ``NODE_FIELD`` → ``"none"`` unconditionally (D6).
    2. ``thread_local`` detected FIRST (via ``is_thread_local`` attr or token
       scan) → ``"thread_local"`` (libclang has no THREAD_LOCAL enum value;
       confirmed in P2 probe — see implementation-notes.md).
    3. ``cursor.storage_class`` enum → ``"static"`` | ``"extern"`` | ``"none"``
       etc.

    The ``thread_local`` check must precede the enum check so that
    ``extern thread_local`` resolves to ``"thread_local"`` (EC1).
    """
    if node_type == NODE_FIELD:
        return "none"  # D6: non-static Field always gets "none"

    # --- thread_local detection (enum value absent on pinned libclang) ---
    is_tl = getattr(cursor, "is_thread_local", None)
    if callable(is_tl):
        try:
            if bool(is_tl()):
                return "thread_local"
        except Exception:
            pass

    # Token-scan fallback for thread_local (handles extern thread_local, EC1).
    try:
        for tok in cursor.get_tokens():
            if tok.spelling == "thread_local":
                return "thread_local"
    except Exception:
        pass

    # --- StorageClass enum mapping ---
    try:
        from clang.cindex import StorageClass  # type: ignore[import-untyped]

        sc = cursor.storage_class
        if sc == StorageClass.STATIC:
            return "static"
        if sc == StorageClass.EXTERN:
            return "extern"
        if sc == StorageClass.AUTO:
            return "auto"
        if sc == StorageClass.REGISTER:
            return "register"
    except Exception:
        pass

    return "none"


# ---------------------------------------------------------------------------
# Type node helpers (ADR-26 D1-D4)
# ---------------------------------------------------------------------------


def _type_usr(spelling: str) -> str:
    """Return the synthetic USR for a Type node (ADR-26 D1).

    Format: ``type:<sha1_hex_digest_of_spelling_utf8>``

    Using sha1 over the source-form spelling (per ADR-26 D2) gives a
    deterministic, collision-resistant USR that works for builtins (int,
    void), pointer/reference variants, and template instantiations alike.
    The ``type:`` prefix disambiguates from libclang cursor USRs (``c:``),
    file USRs (``file://``), and the synthetic Parameter USR (``#param``).
    """
    return f"type:{hashlib.sha1(spelling.encode('utf-8')).hexdigest()}"


def _type_props(t: Any) -> dict[str, Any]:
    """Return the eight Type node properties for libclang type *t*.

    All probes are individually guarded; a missing capability defaults to
    ``False`` / ``""`` (mirrors S1 ``_var_qualifiers`` pattern, per ADR-26
    D10).  The source-form spelling is used per ADR-26 D2 — do NOT call
    ``t.get_canonical().spelling``.
    """
    props: dict[str, Any] = {
        "spelling": "",
        "is_const": False,
        "is_volatile": False,
        "is_pointer": False,
        "is_reference": False,
        "is_lvalue_reference": False,
        "is_rvalue_reference": False,
        "kind": "",
    }

    with contextlib.suppress(Exception):
        props["spelling"] = t.spelling or ""

    with contextlib.suppress(Exception):
        props["is_const"] = bool(t.is_const_qualified())

    with contextlib.suppress(Exception):
        props["is_volatile"] = bool(t.is_volatile_qualified())

    try:
        from clang.cindex import TypeKind  # type: ignore[import-untyped]

        kind = t.kind
        props["is_pointer"] = kind == TypeKind.POINTER
        props["is_lvalue_reference"] = kind == TypeKind.LVALUEREFERENCE
        props["is_rvalue_reference"] = kind == TypeKind.RVALUEREFERENCE
        props["is_reference"] = props["is_lvalue_reference"] or props["is_rvalue_reference"]
        props["kind"] = kind.name if hasattr(kind, "name") else str(kind)
    except Exception:
        pass

    return props


def _get_or_create_type(
    t: Any,
    nodes: list[NodeRecord],
    edges: list[EdgeRecord],
    seen_usrs: set[str],
) -> str | None:
    """Ensure a Type node exists for libclang type *t*; return its USR.

    Idempotent: re-calling with the same spelling is a no-op (seen_usrs
    guard — ADR-26 D3).  Recursively creates pointee/referent Types and
    emits POINTS_TO / REFERS_TO edges per ADR-26 D4.

    Returns ``None`` when *t* is None or has no usable spelling.
    """
    if t is None:
        return None
    try:
        spelling = t.spelling or ""
    except Exception:
        return None
    if not spelling:
        return None

    usr = _type_usr(spelling)
    if usr in seen_usrs:
        return usr
    seen_usrs.add(usr)
    nodes.append(NodeRecord(label=NODE_TYPE, usr=usr, props=_type_props(t)))

    # ADR-26 D4: recursively create pointee / referent and emit chain edges.
    try:
        from clang.cindex import TypeKind  # type: ignore[import-untyped]

        kind = t.kind
        if kind == TypeKind.POINTER:
            pointee_usr = _get_or_create_type(t.get_pointee(), nodes, edges, seen_usrs)
            if pointee_usr:
                edges.append(
                    EdgeRecord(
                        source_usr=usr,
                        target_usr=pointee_usr,
                        edge_type=EDGE_POINTS_TO,
                        props={},
                    )
                )
        elif kind in (TypeKind.LVALUEREFERENCE, TypeKind.RVALUEREFERENCE):
            # libclang reuses get_pointee() for reference types (confirmed in ADR-26).
            referent_usr = _get_or_create_type(t.get_pointee(), nodes, edges, seen_usrs)
            if referent_usr:
                edges.append(
                    EdgeRecord(
                        source_usr=usr,
                        target_usr=referent_usr,
                        edge_type=EDGE_REFERS_TO,
                        props={},
                    )
                )
    except Exception:
        pass

    return usr


# ---------------------------------------------------------------------------
# Parameter helper (ADR-26 D6, design §2.6)
# ---------------------------------------------------------------------------


def _render_default_value(param_cursor: Any) -> str:
    """Return the source-text spelling of a parameter's default value, or "".

    Strategy (design §2.6): iterate ``param_cursor.get_tokens()``, capture
    tokens after the first ``=`` token up to end of extent, join with single
    spaces, strip surrounding whitespace.

    Multi-token defaults (``= std::string("x")``) are preserved as a single
    string; the property is documented as source-text verbatim.  Returns ``""``
    when no initializer is present (SC-C-04).
    """
    try:
        tokens = list(param_cursor.get_tokens())
    except Exception:
        return ""

    found_eq = False
    parts: list[str] = []
    for tok in tokens:
        try:
            spelling = tok.spelling
        except Exception:
            continue
        if not found_eq:
            if spelling == "=":
                found_eq = True
        else:
            parts.append(spelling)

    return " ".join(parts).strip()


# ---------------------------------------------------------------------------
# Function signature property helpers (ADR-26 D7, D10, D11; design §2.4, §2.7)
# ---------------------------------------------------------------------------


def _method_has_volatile_qualifier(cursor: Any) -> bool:
    """Return True when the method has a ``volatile`` cv-qualifier (design §2.7).

    Strategy: walk the tokens of ``cursor.extent``; track paren depth to find
    the `)` that closes the parameter list; scan tokens *after* that close-paren
    until the first `{`, `;`, `=`, or `->` (trailing return type) — return True
    if ``"volatile"`` appears in that window.

    Mirrors S1's ``_storage_class_value`` token-scan pattern.  Avoids mis-firing
    on ``volatile`` inside the parameter list (e.g. ``void f(volatile int *)``)
    because the scan starts only after the closing `)`.
    """
    try:
        tokens = list(cursor.get_tokens())
    except Exception:
        return False

    # Find the index of the `)` that closes the parameter list (depth-tracked).
    paren_depth = 0
    close_paren_idx = -1
    for i, tok in enumerate(tokens):
        try:
            sp = tok.spelling
        except Exception:
            continue
        if sp == "(":
            paren_depth += 1
        elif sp == ")":
            paren_depth -= 1
            if paren_depth == 0:
                close_paren_idx = i
                break

    if close_paren_idx < 0:
        return False

    # Scan tokens after the closing `)` for "volatile" until a terminator.
    _TERMINATORS = frozenset({"{", ";", "="})
    for tok in tokens[close_paren_idx + 1 :]:
        try:
            sp = tok.spelling
        except Exception:
            continue
        if sp in _TERMINATORS:
            break
        if sp == "->":
            break  # trailing return type starts; stop scanning
        if sp == "volatile":
            return True

    return False


def _emit_function_signature_props(cursor: Any) -> dict[str, Any]:
    """Return the seven S2 signature properties for a Function cursor (ADR-26 D7/D10/D11).

    Properties returned:
      - ``signature``: ``cursor.displayname`` (ADR-26 D7)
      - ``is_constexpr``: token-scan for ``"constexpr"`` (ADR-26 D10 — absent on pinned libclang)
      - ``is_noexcept``: ``exception_specification_kind in {BASIC_NOEXCEPT, COMPUTED_NOEXCEPT,
        DYNAMIC_NONE}`` (ADR-26 D11)
      - ``is_deleted``: ``cursor.is_deleted_method()``
      - ``is_defaulted``: ``cursor.is_default_method()``
      - ``cv_qualifiers``: ``""`` | ``"const"`` | ``"volatile"`` | ``"const volatile"``
      - ``ref_qualifier``: ``""`` | ``"&"`` | ``"&&"``

    DEFERRED (do NOT add here): ``is_template``, ``is_virtual``, ``is_override`` (S3/S4).

    Libclang fallback notes (ADR-26 D10, F-6):
      - ``cursor.is_constexpr`` is **absent** on the pinned libclang; token-scan is always used.
      - ``cursor.is_noexcept`` is **absent**; ``exception_specification_kind`` is used instead.
      - ``ExceptionSpecificationKind.NOEXCEPT_FALSE`` is absent on this libclang version;
        ``COMPUTED_NOEXCEPT`` covers both ``noexcept(true)`` and ``noexcept(false)`` at the
        enum level.  ADR-26 D11 treats ``COMPUTED_NOEXCEPT`` → ``True``; ``noexcept(false)``
        cannot be disambiguated without inspecting the boolean argument expression.
        Documented in implementation-notes.md §Libclang fallbacks.
      - There is no ``is_volatile_method``; ``cv_qualifiers="volatile"`` is detected via
        ``_method_has_volatile_qualifier`` token-scan (ADR-26 D10, F-7).
    """
    props: dict[str, Any] = {
        "signature": "",
        "is_constexpr": False,
        "is_noexcept": False,
        "is_deleted": False,
        "is_defaulted": False,
        "cv_qualifiers": "",
        "ref_qualifier": "",
    }

    # --- signature: cursor.displayname (ADR-26 D7) ---
    with contextlib.suppress(Exception):
        props["signature"] = cursor.displayname or ""

    # --- is_constexpr: token-scan (is_constexpr absent on pinned libclang per ADR-26 D10) ---
    # First, try the native method (future-proofing); fall back to token-scan.
    is_constexpr_method = getattr(cursor, "is_constexpr", None)
    if callable(is_constexpr_method):
        with contextlib.suppress(Exception):
            props["is_constexpr"] = bool(is_constexpr_method())

    if not props["is_constexpr"]:
        try:
            for tok in cursor.get_tokens():
                if tok.spelling == "constexpr":
                    props["is_constexpr"] = True
                    break
        except Exception:
            pass

    # --- is_noexcept: exception_specification_kind (ADR-26 D11) ---
    try:
        from clang.cindex import ExceptionSpecificationKind  # type: ignore[import-untyped]

        _NOEXCEPT_KINDS = frozenset(
            {
                ExceptionSpecificationKind.BASIC_NOEXCEPT,
                ExceptionSpecificationKind.COMPUTED_NOEXCEPT,
                ExceptionSpecificationKind.DYNAMIC_NONE,
            }
        )
        props["is_noexcept"] = cursor.exception_specification_kind in _NOEXCEPT_KINDS
    except Exception:
        pass

    # --- is_deleted: cursor.is_deleted_method() ---
    with contextlib.suppress(Exception):
        is_del = getattr(cursor, "is_deleted_method", None)
        if callable(is_del):
            props["is_deleted"] = bool(is_del())

    # --- is_defaulted: cursor.is_default_method() ---
    with contextlib.suppress(Exception):
        is_def = getattr(cursor, "is_default_method", None)
        if callable(is_def):
            props["is_defaulted"] = bool(is_def())

    # --- cv_qualifiers: "const" | "volatile" | "const volatile" | "" ---
    cv: list[str] = []
    with contextlib.suppress(Exception):
        is_const_m = getattr(cursor, "is_const_method", None)
        if callable(is_const_m) and bool(is_const_m()):
            cv.append("const")
    if _method_has_volatile_qualifier(cursor):
        cv.append("volatile")
    props["cv_qualifiers"] = " ".join(cv)

    # --- ref_qualifier: "" | "&" | "&&" ---
    try:
        from clang.cindex import RefQualifierKind  # type: ignore[import-untyped]

        rq = cursor.type.get_ref_qualifier()
        props["ref_qualifier"] = {
            RefQualifierKind.NONE: "",
            RefQualifierKind.LVALUE: "&",
            RefQualifierKind.RVALUE: "&&",
        }.get(rq, "")
    except Exception:
        pass

    return props


# ---------------------------------------------------------------------------
# Class property helper (ADR-26 D8, D10; design §2.5; S2-G)
# ---------------------------------------------------------------------------


def _emit_class_props(cursor: Any) -> dict[str, Any]:
    """Return S2 class properties for a CLASS_DECL / STRUCT_DECL / UNION_DECL cursor.

    Properties returned:
      - ``is_final``:    True when the class has a ``CXX_FINAL_ATTR`` child (ADR-26 D10).
      - ``is_abstract``: True when ``cursor.is_abstract_record()`` returns True.
        Defaults to False for forward declarations and on libclang capability miss.
      - ``record_kind``: ``"class"`` | ``"struct"`` | ``"union"`` | ``""`` (defensive).
        Derived from ``cursor.kind.name`` (ADR-26 D8).

    DEFERRED (do NOT add here): ``is_template`` (S3).

    All probes are individually guarded and default to ``False`` / ``""`` on
    any exception (mirrors ``_emit_function_signature_props`` pattern).
    """
    props: dict[str, Any] = {
        "is_final": False,
        "is_abstract": False,
        "record_kind": "",
    }

    # --- is_final: walk children for CXX_FINAL_ATTR ---
    with contextlib.suppress(Exception):
        for child in cursor.get_children():
            with contextlib.suppress(Exception):
                if child.kind.name == "CXX_FINAL_ATTR":
                    props["is_final"] = True
                    break

    # --- is_abstract: cursor.is_abstract_record() (present on pinned libclang per ADR-26 D10) ---
    with contextlib.suppress(Exception):
        fn = getattr(cursor, "is_abstract_record", None)
        if callable(fn):
            props["is_abstract"] = bool(fn())

    # --- record_kind: derived from cursor.kind.name (ADR-26 D8) ---
    with contextlib.suppress(Exception):
        _KIND_TO_RECORD: dict[str, str] = {
            "CLASS_DECL": "class",
            "CLASS_TEMPLATE": "class",
            "STRUCT_DECL": "struct",
            "UNION_DECL": "union",
        }
        props["record_kind"] = _KIND_TO_RECORD.get(cursor.kind.name, "")

    return props


# ---------------------------------------------------------------------------
# Per-file extraction helpers
# ---------------------------------------------------------------------------


def _kind_name(cursor: Any) -> str:
    try:
        return str(cursor.kind.name)
    except Exception:
        return ""


def _safe_usr(cursor: Any) -> str:
    try:
        return cursor.get_usr() or ""
    except Exception:
        return ""


def _safe_spelling(cursor: Any) -> str:
    try:
        return cursor.spelling or ""
    except Exception:
        return ""


def _safe_location(cursor: Any) -> tuple[str, int, int]:
    """Return (file_path, line, col) or ("", 0, 0) on failure."""
    try:
        loc = cursor.location
        fname = loc.file.name if loc.file else ""
        return fname, loc.line, loc.column
    except Exception:
        return "", 0, 0


def _file_usr(file_path: Path) -> str:
    """Synthetic USR for a File node (not a libclang cursor)."""
    return f"file://{file_path}"


def _walk_cursor(
    cursor: Any,
    file_path: Path,
    file_usr: str,
    nodes: list[NodeRecord],
    edges: list[EdgeRecord],
    parent_usr: str | None,
    parent_kind: str | None,
    seen_usrs: set[str],
    enclosing_func_usr: str | None = None,
) -> None:
    """Recursive DFS over libclang cursor tree.

    Only emits cursors that originate in *file_path* (avoids re-emitting
    system header nodes on every parsed TU).

    *enclosing_func_usr* tracks the nearest enclosing function/method USR so
    that REFERENCES edges use the function as source rather than the immediate
    structural parent (e.g. a namespace or class).  Falls back to *file_usr*
    for top-level use-sites.
    """
    kind = _kind_name(cursor)

    # ------------------------------------------------------------------
    # P3 (ADR-26 D9): Skip PARM_DECL in generic child recursion.
    # Parameter nodes are emitted by the explicit get_arguments() loop in the
    # parent function block (design §3.2 option (a)).  If generic recursion
    # lands on a PARM_DECL it means the function block has already emitted (or
    # will emit) the Parameter via the synthetic USR; returning here prevents
    # duplicate vertices with the libclang-native PARM_DECL USR.
    # ------------------------------------------------------------------
    if kind == "PARM_DECL":
        return

    # ------------------------------------------------------------------
    # Inclusion directives → INCLUDES edge
    # ------------------------------------------------------------------
    if kind == "INCLUSION_DIRECTIVE":
        try:
            included = cursor.get_included_file()
            if included:
                inc_path = included.name
                inc_usr = f"file://{inc_path}"
                if inc_usr not in seen_usrs:
                    seen_usrs.add(inc_usr)
                    nodes.append(
                        NodeRecord(
                            label=NODE_FILE,
                            usr=inc_usr,
                            props={
                                "path": inc_path,
                                "spelling": inc_path,
                                "schema_version": SCHEMA_VERSION,
                            },
                        )
                    )
                edges.append(
                    EdgeRecord(
                        source_usr=file_usr,
                        target_usr=inc_usr,
                        edge_type=EDGE_INCLUDES,
                        props={},
                    )
                )
        except Exception:
            pass
        return  # do not recurse into include directive children

    # ------------------------------------------------------------------
    # Symbol use-sites → REFERENCES edge (no node created)
    # ------------------------------------------------------------------
    if kind in _REFERENCE_CURSOR_KINDS:
        try:
            ref = cursor.referenced
            if ref is not None:
                target_usr = _safe_usr(ref)
                if target_usr:
                    source_usr = enclosing_func_usr if enclosing_func_usr else file_usr
                    edges.append(
                        EdgeRecord(
                            source_usr=source_usr,
                            target_usr=target_usr,
                            edge_type=EDGE_REFERENCES,
                            props={},
                        )
                    )
        except Exception:
            pass
        # Recurse: nested refs can appear inside type arguments etc.
        for child in cursor.get_children():
            _walk_cursor(
                child,
                file_path,
                file_usr,
                nodes,
                edges,
                parent_usr,
                parent_kind,
                seen_usrs,
                enclosing_func_usr,
            )
        return

    # ------------------------------------------------------------------
    # Filter: only emit symbols that live in *file_path*
    # ------------------------------------------------------------------
    loc_file, loc_line, loc_col = _safe_location(cursor)
    if loc_file and loc_file != str(file_path):
        # Symbol defined in a different file — skip but recurse into children
        # because the TU may mix headers and the main file.
        for child in cursor.get_children():
            _walk_cursor(
                child,
                file_path,
                file_usr,
                nodes,
                edges,
                None,
                None,
                seen_usrs,
                enclosing_func_usr,
            )
        return

    node_type = _classify_node(cursor)
    usr = _safe_usr(cursor)
    spelling = _safe_spelling(cursor)

    if node_type and usr:
        if usr not in seen_usrs:
            seen_usrs.add(usr)
            try:
                type_spelling = cursor.type.spelling if cursor.type else ""
            except Exception:
                type_spelling = ""

            props: dict[str, Any] = {
                "spelling": spelling,
                "type": type_spelling,
                "file": loc_file,
                "line": loc_line,
                "col": loc_col,
            }
            if node_type in (NODE_FIELD, NODE_GLOBAL_VARIABLE):
                # P4: emit the four variable/field properties (design §6, ADR-25 D6).
                is_const, is_constexpr = _var_qualifiers(cursor)
                props["is_const"] = is_const
                props["is_constexpr"] = is_constexpr
                # is_static: True for static class data member (GlobalVariable from
                # FIELD_DECL) OR for VAR_DECL with StorageClass.STATIC (design §4.2).
                props["is_static"] = (
                    node_type == NODE_GLOBAL_VARIABLE and kind == "FIELD_DECL"
                ) or _is_storage_static(cursor)
                props["storage_class"] = _storage_class_value(cursor, node_type)

            # P5 (ADR-26 D7/D10/D11): Function signature properties.
            # DEFERRED (not emitted here): is_template (S3), is_virtual, is_override (S4).
            if node_type == NODE_FUNCTION:
                props.update(_emit_function_signature_props(cursor))

            # P6 (ADR-26 D8/D10): Class qualifier properties.
            # DEFERRED (not emitted here): is_template (S3).
            if node_type == NODE_CLASS:
                props.update(_emit_class_props(cursor))

            nodes.append(
                NodeRecord(
                    label=node_type,
                    usr=usr,
                    props=props,
                )
            )

            # P4 (ADR-26 §3.4): OF_TYPE for Field and GlobalVariable (VAR_DECL + static
            # FIELD_DECL).  Emitted inside seen_usrs guard to avoid duplicate edges on
            # re-encountered cursors (forward decl + definition).  SC-D-02 note: local
            # VAR_DECL is still classified GlobalVariable by ADR-25 D2; the "Variable"
            # label in scenarios is read as "the node emitted for the local VAR_DECL"
            # regardless of label — no reclassification in S2.
            if node_type in (NODE_FIELD, NODE_GLOBAL_VARIABLE):
                with contextlib.suppress(Exception):
                    of_type_usr = _get_or_create_type(cursor.type, nodes, edges, seen_usrs)
                    if of_type_usr:
                        edges.append(
                            EdgeRecord(
                                source_usr=usr,
                                target_usr=of_type_usr,
                                edge_type=EDGE_OF_TYPE,
                                props={},
                            )
                        )

        # ------------------------------------------------------------------
        # Edge: parent → this symbol
        # ------------------------------------------------------------------
        if parent_usr:
            # MEMBER_OF for fields / methods inside a class/struct (ADR-25 D5).
            if parent_kind in _MEMBER_PARENT_KINDS and kind in (
                "FIELD_DECL",
                "CXX_METHOD",
                "CONSTRUCTOR",
                "DESTRUCTOR",
            ):
                access = _resolve_access(cursor, parent_kind)
                edges.append(
                    EdgeRecord(
                        source_usr=usr,
                        target_usr=parent_usr,
                        edge_type=EDGE_MEMBER_OF,
                        props={"access": access},  # D5: access on every MEMBER_OF edge
                    )
                )
            else:
                # DEFINES vs DECLARES: has a body → DEFINES, otherwise DECLARES.
                try:
                    is_definition = cursor.is_definition()
                except Exception:
                    is_definition = False
                edge_type = EDGE_DEFINES if is_definition else EDGE_DECLARES
                edges.append(
                    EdgeRecord(
                        source_usr=parent_usr,
                        target_usr=usr,
                        edge_type=edge_type,
                        props={},
                    )
                )
        else:
            # Top-level: File → symbol
            try:
                is_definition = cursor.is_definition()
            except Exception:
                is_definition = False
            edge_type = EDGE_DEFINES if is_definition else EDGE_DECLARES
            edges.append(
                EdgeRecord(
                    source_usr=file_usr,
                    target_usr=usr,
                    edge_type=edge_type,
                    props={},
                )
            )

        # ------------------------------------------------------------------
        # INHERITS edges for class bases
        # ------------------------------------------------------------------
        if kind in ("CLASS_DECL", "STRUCT_DECL", "CLASS_TEMPLATE"):
            try:
                for base in cursor.get_children():
                    if _kind_name(base) == "CXX_BASE_SPECIFIER":
                        base_def = base.get_definition()
                        if base_def:
                            base_usr = _safe_usr(base_def)
                            if base_usr:
                                edges.append(
                                    EdgeRecord(
                                        source_usr=usr,
                                        target_usr=base_usr,
                                        edge_type=EDGE_INHERITS,
                                        props={},
                                    )
                                )
            except Exception:
                pass

        # ------------------------------------------------------------------
        # CALLS edges for call expressions
        # ------------------------------------------------------------------
        if kind == "CALL_EXPR":
            try:
                callee = cursor.referenced
                if callee:
                    callee_usr = _safe_usr(callee)
                    if callee_usr and parent_usr:
                        edges.append(
                            EdgeRecord(
                                source_usr=parent_usr,
                                target_usr=callee_usr,
                                edge_type=EDGE_CALLS,
                                props={},
                            )
                        )
            except Exception:
                pass

        # Update enclosing_func_usr when entering a function/method body.
        next_enclosing_func = enclosing_func_usr
        if kind in _FUNCTION_CURSOR_KINDS and usr:
            next_enclosing_func = usr

        # P2/P4 (ADR-26 D2, D3, D4, D5): Materialise the return-type Type node
        # and emit the RETURNS edge (P4).  Ctors/dtors both yield "void" from
        # libclang's result_type naturally — no special case needed (ADR-26 D5).
        if kind in _FUNCTION_CURSOR_KINDS and usr:
            with contextlib.suppress(Exception):
                ret_usr = _get_or_create_type(cursor.result_type, nodes, edges, seen_usrs)
                if ret_usr:
                    edges.append(
                        EdgeRecord(
                            source_usr=usr,
                            target_usr=ret_usr,
                            edge_type=EDGE_RETURNS,
                            props={},
                        )
                    )

        # P3/P4 (ADR-26 D6, D9): Emit Parameter nodes + HAS_PARAM + OF_TYPE edges.
        # Uses get_arguments() enumeration for deterministic positional ordering
        # (design §3.2 option (a)).  OF_TYPE from each Parameter to its Type (P4).
        if kind in _FUNCTION_CURSOR_KINDS and usr:
            try:
                for idx, param in enumerate(cursor.get_arguments()):
                    param_usr = f"{usr}#param:{idx}"
                    if param_usr not in seen_usrs:
                        seen_usrs.add(param_usr)
                        param_loc = _safe_location(param)
                        # P4: create the parameter's Type node (and POINTS_TO/REFERS_TO chain).
                        param_type_usr: str | None = None
                        with contextlib.suppress(Exception):
                            param_type_usr = _get_or_create_type(
                                param.type, nodes, edges, seen_usrs
                            )
                        nodes.append(
                            NodeRecord(
                                label=NODE_PARAMETER,
                                usr=param_usr,
                                props={
                                    "spelling": param.spelling or f"<param#{idx}>",
                                    "name": param.spelling or "",
                                    "index": idx,
                                    "default_value": _render_default_value(param),
                                    "file": param_loc[0],
                                    "line": param_loc[1],
                                    "col": param_loc[2],
                                },
                            )
                        )
                        edges.append(
                            EdgeRecord(
                                source_usr=usr,
                                target_usr=param_usr,
                                edge_type=EDGE_HAS_PARAM,
                                props={"index": idx},
                            )
                        )
                        # P4: OF_TYPE from Parameter to its Type.
                        with contextlib.suppress(Exception):
                            if param_type_usr:
                                edges.append(
                                    EdgeRecord(
                                        source_usr=param_usr,
                                        target_usr=param_type_usr,
                                        edge_type=EDGE_OF_TYPE,
                                        props={},
                                    )
                                )
            except Exception:
                pass

        # Recurse with this cursor as the new parent.
        for child in cursor.get_children():
            _walk_cursor(
                child,
                file_path,
                file_usr,
                nodes,
                edges,
                usr,
                kind,
                seen_usrs,
                next_enclosing_func,
            )
    else:
        # Non-schema cursor: recurse but pass parent context through.
        for child in cursor.get_children():
            _walk_cursor(
                child,
                file_path,
                file_usr,
                nodes,
                edges,
                parent_usr,
                parent_kind,
                seen_usrs,
                enclosing_func_usr,
            )


def extract_nodes_and_edges(
    tu: Any,
    file_path: Path,
) -> tuple[list[NodeRecord], list[EdgeRecord]]:
    """Extract all schema-relevant nodes and edges from *tu*.

    Args:
        tu: libclang ``TranslationUnit``.
        file_path: Absolute path to the C++ source file.

    Returns:
        ``(nodes, edges)`` — lists ready to be passed to a ``GraphDriver``.
    """
    f_usr = _file_usr(file_path)
    nodes: list[NodeRecord] = [
        NodeRecord(
            label=NODE_FILE,
            usr=f_usr,
            props={
                "path": str(file_path),
                "spelling": file_path.name,
                "schema_version": SCHEMA_VERSION,
            },
        )
    ]
    edges: list[EdgeRecord] = []
    seen_usrs: set[str] = {f_usr}

    _walk_cursor(
        tu.cursor,
        file_path,
        f_usr,
        nodes,
        edges,
        None,
        None,
        seen_usrs,
    )

    # ------------------------------------------------------------------
    # Dedup: suppress REFERENCES edges that duplicate a CALLS edge.
    # A CALLS edge on (source, target) already implies a reference; emitting
    # both would double-count in the graph.  Build a set of (source, target)
    # pairs covered by CALLS and drop matching REFERENCES edges.
    # ------------------------------------------------------------------
    calls_pairs: set[tuple[str, str]] = {
        (e["source_usr"], e["target_usr"]) for e in edges if e["edge_type"] == EDGE_CALLS
    }
    if calls_pairs:
        edges = [
            e
            for e in edges
            if not (
                e["edge_type"] == EDGE_REFERENCES
                and (e["source_usr"], e["target_usr"]) in calls_pairs
            )
        ]

    return nodes, edges


# ---------------------------------------------------------------------------
# export_file
# ---------------------------------------------------------------------------


def export_file(
    file_path: Path,
    tu: Any,
    driver: GraphDriver,
) -> dict[str, Any]:
    """Export one parsed TU to the graph database.

    Args:
        file_path: Absolute path to the C++ source file.
        tu: Pre-parsed libclang ``TranslationUnit``.
        driver: Connected ``GraphDriver`` instance.

    Returns:
        Dict with ``nodes_written`` and ``edges_written`` counts.

    Raises:
        Any exception from the driver or extraction is propagated to the caller
        (``export_directory`` catches per-file exceptions for partial success).
    """
    nodes, edges = extract_nodes_and_edges(tu, file_path)
    nodes_attempted = len(nodes)
    edges_attempted = len(edges)
    nodes_written = driver.upsert_nodes(nodes)
    edges_written = driver.upsert_edges(edges)
    logger.debug(
        "Exported %s: %d/%d nodes, %d/%d edges",
        file_path.name,
        nodes_written,
        nodes_attempted,
        edges_written,
        edges_attempted,
    )
    return {
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "nodes_attempted": nodes_attempted,
        "edges_attempted": edges_attempted,
    }


# ---------------------------------------------------------------------------
# export_directory
# ---------------------------------------------------------------------------


def collect_cpp_files(path: Path, recursive: bool) -> list[Path]:
    """Return all C++ files under *path* (or *path* itself if a single file).

    Args:
        path: A file or directory.
        recursive: If True, descend into sub-directories.

    Returns:
        List of absolute ``Path`` objects whose suffix is in :data:`CPP_EXTENSIONS`.
    """
    if path.is_file():
        return [path] if path.suffix in CPP_EXTENSIONS else []

    if recursive:
        return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in CPP_EXTENSIONS)
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix in CPP_EXTENSIONS)
