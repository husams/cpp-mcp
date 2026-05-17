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
  VAR_DECL /
    FIELD_DECL /
    PARM_DECL          → Variable
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

import logging
from pathlib import Path
from typing import Any

from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord
from cpp_mcp.graphdb.schema import (
    EDGE_CALLS,
    EDGE_DECLARES,
    EDGE_DEFINES,
    EDGE_INCLUDES,
    EDGE_INHERITS,
    EDGE_MEMBER_OF,
    EDGE_REFERENCES,
    NODE_CLASS,
    NODE_FILE,
    NODE_FUNCTION,
    NODE_MACRO,
    NODE_NAMESPACE,
    NODE_TYPE_ALIAS,
    NODE_VARIABLE,
)

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
    "VAR_DECL": NODE_VARIABLE,
    "FIELD_DECL": NODE_VARIABLE,
    "PARM_DECL": NODE_VARIABLE,
    "MACRO_DEFINITION": NODE_MACRO,
    "TYPEDEF_DECL": NODE_TYPE_ALIAS,
    "TYPE_ALIAS_DECL": NODE_TYPE_ALIAS,
    "TYPE_ALIAS_TEMPLATE_DECL": NODE_TYPE_ALIAS,
}

# CursorKind names whose children are MEMBER_OF the parent class/struct.
_MEMBER_PARENT_KINDS: frozenset[str] = frozenset({"CLASS_DECL", "STRUCT_DECL", "CLASS_TEMPLATE"})

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
                            props={"path": inc_path, "spelling": inc_path},
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

    node_type = _KIND_TO_NODE_TYPE.get(kind)
    usr = _safe_usr(cursor)
    spelling = _safe_spelling(cursor)

    if node_type and usr:
        if usr not in seen_usrs:
            seen_usrs.add(usr)
            try:
                type_spelling = cursor.type.spelling if cursor.type else ""
            except Exception:
                type_spelling = ""

            nodes.append(
                NodeRecord(
                    label=node_type,
                    usr=usr,
                    props={
                        "spelling": spelling,
                        "type": type_spelling,
                        "file": loc_file,
                        "line": loc_line,
                        "col": loc_col,
                    },
                )
            )

        # ------------------------------------------------------------------
        # Edge: parent → this symbol
        # ------------------------------------------------------------------
        if parent_usr:
            # MEMBER_OF for fields / params inside a class/struct
            if parent_kind in _MEMBER_PARENT_KINDS and kind in (
                "FIELD_DECL",
                "CXX_METHOD",
                "CONSTRUCTOR",
                "DESTRUCTOR",
            ):
                edges.append(
                    EdgeRecord(
                        source_usr=usr,
                        target_usr=parent_usr,
                        edge_type=EDGE_MEMBER_OF,
                        props={},
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
            props={"path": str(file_path), "spelling": file_path.name},
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
