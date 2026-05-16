"""AST walker: depth/range-filtered cursor traversal with size budgets.

ADR-5: dual node-count + byte-budget truncation.
  - CPP_MCP_AST_MAX_NODES (default 5000): stops DFS after this many nodes.
  - CPP_MCP_AST_MAX_BYTES (default 1 MiB): stops when estimated serialized size
    exceeds this limit.

Two output formats:
  - "json"  — hierarchical tree of node dicts with a "children" list.
  - "graph" — flat {nodes: [...], edges: [...]} with CHILD, TYPE_REF, CALL edges.

Per-node truncation (depth cap) is orthogonal to the global budget truncation:
  - A node carries truncated=true when its children were cut by the depth limit.
  - The top-level response carries truncated=true when the global budget fired.

Only cursors whose extent overlaps [start_line, end_line] (inclusive) are
included when line-range filtering is active.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Node serialisation helpers
# ---------------------------------------------------------------------------

_EDGE_TYPE_CHILD = "CHILD"
_EDGE_TYPE_TYPE_REF = "TYPE_REF"
_EDGE_TYPE_CALL = "CALL"

# CursorKind names that denote a type-reference relationship.
_TYPE_REF_KINDS: frozenset[str] = frozenset(
    {
        "TYPE_REF",
        "TEMPLATE_REF",
        "NAMESPACE_REF",
        "OVERLOADED_DECL_REF",
    }
)

# CursorKind names that denote a call relationship.
_CALL_KINDS: frozenset[str] = frozenset(
    {
        "CALL_EXPR",
        "CXX_METHOD",  # virtual dispatch
    }
)


def _storage_class_name(cursor: Any) -> str:
    """Return a human-readable storage class string for *cursor*."""
    try:
        sc = cursor.storage_class
        # clang.cindex.StorageClass is an enumeration-like object with a .name attr.
        return sc.name if hasattr(sc, "name") else str(sc)
    except Exception:
        return "NONE"


def _cursor_to_node(cursor: Any, node_id: int) -> dict[str, Any]:
    """Build a flat node dict from *cursor* (no children key yet)."""
    ext = cursor.extent
    try:
        kind_name = cursor.kind.name
    except Exception:
        kind_name = "UNKNOWN"

    try:
        type_spelling = cursor.type.spelling if cursor.type is not None else ""
    except Exception:
        type_spelling = ""

    try:
        usr = cursor.get_usr() or ""
    except Exception:
        usr = ""

    try:
        spelling = cursor.spelling or ""
    except Exception:
        spelling = ""

    start = ext.start if ext else None
    end = ext.end if ext else None

    return {
        "id": node_id,
        "kind": kind_name,
        "spelling": spelling,
        "usr": usr,
        "type": type_spelling,
        "storage_class": _storage_class_name(cursor),
        "start_line": start.line if start else 0,
        "start_col": start.column if start else 0,
        "end_line": end.line if end else 0,
        "end_col": end.column if end else 0,
    }


def _overlaps_range(cursor: Any, start_line: int | None, end_line: int | None) -> bool:
    """Return True if cursor extent overlaps [start_line, end_line]."""
    if start_line is None and end_line is None:
        return True
    ext = cursor.extent
    if not ext:
        return True
    c_start = ext.start.line if ext.start else 0
    c_end = ext.end.line if ext.end else 0
    lo = start_line if start_line is not None else 0
    hi = end_line if end_line is not None else 2**31
    # Overlap: cursor range overlaps [lo, hi]
    return c_start <= hi and c_end >= lo


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


class _Budget:
    """Tracks nodes emitted and estimated bytes; signals stop when capped."""

    def __init__(self, max_nodes: int, max_bytes: int) -> None:
        self.max_nodes = max_nodes
        self.max_bytes = max_bytes
        self.nodes_emitted = 0
        self.bytes_estimate = 0
        self.truncated = False
        self.truncation_reason: str | None = None

    def charge(self, node: dict[str, Any]) -> bool:
        """Charge the budget for *node*. Return False if budget is exhausted."""
        if self.truncated:
            return False
        self.nodes_emitted += 1
        # Cheap byte estimate: serialise just the scalar fields (no children key).
        self.bytes_estimate += len(json.dumps(node))
        if self.nodes_emitted >= self.max_nodes:
            self.truncated = True
            self.truncation_reason = "max_nodes"
            return True  # charged OK — this node is included, but DFS stops after it
        if self.bytes_estimate >= self.max_bytes:
            self.truncated = True
            self.truncation_reason = "max_bytes"
            return True
        return True

    @property
    def exhausted(self) -> bool:
        return self.truncated and self.nodes_emitted > 0


# ---------------------------------------------------------------------------
# JSON format walker
# ---------------------------------------------------------------------------


def _walk_json(
    cursor: Any,
    depth: int,
    max_depth: int,
    start_line: int | None,
    end_line: int | None,
    budget: _Budget,
    node_counter: list[int],
) -> dict[str, Any] | None:
    """Recursive DFS producing a JSON tree node.

    Returns None when the budget was already exhausted before this node.
    """
    if budget.exhausted:
        return None
    if not _overlaps_range(cursor, start_line, end_line):
        return None

    node_counter[0] += 1
    node = _cursor_to_node(cursor, node_counter[0])

    if not budget.charge(node):
        return None

    if depth >= max_depth:
        # Depth truncation: check if there are children to omit.
        children_exist = any(True for _ in cursor.get_children())
        if children_exist:
            node["truncated"] = True
        node["children"] = []
        return node

    children: list[dict[str, Any]] = []
    for child in cursor.get_children():
        if budget.exhausted:
            break
        child_node = _walk_json(
            child, depth + 1, max_depth, start_line, end_line, budget, node_counter
        )
        if child_node is not None:
            children.append(child_node)

    node["children"] = children
    return node


def walk_json(
    tu: Any,
    max_depth: int,
    start_line: int | None,
    end_line: int | None,
    max_nodes: int,
    max_bytes: int,
) -> dict[str, Any]:
    """Walk *tu*'s cursor tree and return a JSON-format AST dict.

    Returns a dict with keys:
      - root: the root node tree (or None if empty)
      - truncated: bool
      - truncation_reason: str | None
      - nodes_emitted: int
      - nodes_omitted_estimate: int | None
      - parse_errors: list of diagnostic dicts
    """
    budget = _Budget(max_nodes, max_bytes)
    node_counter = [0]
    root_cursor = tu.cursor

    root_node = _walk_json(root_cursor, 0, max_depth, start_line, end_line, budget, node_counter)

    parse_errors = _collect_diagnostics(tu)

    result: dict[str, Any] = {
        "root": root_node,
        "truncated": budget.truncated,
        "truncation_reason": budget.truncation_reason,
        "nodes_emitted": budget.nodes_emitted,
        "nodes_omitted_estimate": None,
        "parse_errors": parse_errors,
    }
    return result


# ---------------------------------------------------------------------------
# Graph format walker
# ---------------------------------------------------------------------------


def _walk_graph(
    cursor: Any,
    parent_id: int | None,
    start_line: int | None,
    end_line: int | None,
    budget: _Budget,
    node_counter: list[int],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> int | None:
    """Recursive DFS building flat node/edge lists for graph format.

    Returns the node id that was assigned, or None if not emitted.
    """
    if budget.exhausted:
        return None
    if not _overlaps_range(cursor, start_line, end_line):
        return None

    node_counter[0] += 1
    current_id = node_counter[0]
    node = _cursor_to_node(cursor, current_id)

    if not budget.charge(node):
        return None

    nodes.append(node)

    # Add edge from parent.
    if parent_id is not None:
        try:
            kind_name = cursor.kind.name
        except Exception:
            kind_name = ""

        if kind_name in _TYPE_REF_KINDS:
            edge_type = _EDGE_TYPE_TYPE_REF
        elif kind_name in _CALL_KINDS:
            edge_type = _EDGE_TYPE_CALL
        else:
            edge_type = _EDGE_TYPE_CHILD

        edges.append(
            {
                "source_id": parent_id,
                "target_id": current_id,
                "edge_type": edge_type,
            }
        )

    if budget.exhausted:
        return current_id

    for child in cursor.get_children():
        if budget.exhausted:
            break
        _walk_graph(
            child,
            current_id,
            start_line,
            end_line,
            budget,
            node_counter,
            nodes,
            edges,
        )

    return current_id


def walk_graph(
    tu: Any,
    start_line: int | None,
    end_line: int | None,
    max_nodes: int,
    max_bytes: int,
) -> dict[str, Any]:
    """Walk *tu*'s cursor tree and return a graph-format AST dict.

    Returns a dict with keys:
      - nodes: list of node dicts (flat)
      - edges: list of edge dicts (only for emitted nodes — no dangling refs)
      - truncated: bool
      - truncation_reason: str | None
      - nodes_emitted: int
      - nodes_omitted_estimate: int | None
      - parse_errors: list of diagnostic dicts
    """
    budget = _Budget(max_nodes, max_bytes)
    node_counter = [0]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    _walk_graph(tu.cursor, None, start_line, end_line, budget, node_counter, nodes, edges)

    parse_errors = _collect_diagnostics(tu)

    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": budget.truncated,
        "truncation_reason": budget.truncation_reason,
        "nodes_emitted": budget.nodes_emitted,
        "nodes_omitted_estimate": None,
        "parse_errors": parse_errors,
    }


# ---------------------------------------------------------------------------
# Diagnostic collection
# ---------------------------------------------------------------------------


def _collect_diagnostics(tu: Any) -> list[dict[str, Any]]:
    """Collect libclang diagnostics from *tu* into a list of dicts."""
    result: list[dict[str, Any]] = []
    try:
        for diag in tu.diagnostics:
            loc = diag.location
            result.append(
                {
                    "severity": _severity_name(diag.severity),
                    "message": diag.spelling,
                    "file": loc.file.name if loc.file else None,
                    "line": loc.line,
                    "col": loc.column,
                }
            )
    except Exception:
        pass
    return result


def _severity_name(severity: Any) -> str:
    """Map a libclang Diagnostic.severity integer to a human-readable name."""
    # clang.cindex.Diagnostic severity constants.
    _MAP = {0: "NOTE", 1: "WARNING", 2: "WARNING", 3: "ERROR", 4: "FATAL"}
    try:
        return _MAP.get(int(severity), str(severity))
    except Exception:
        return str(severity)


# ---------------------------------------------------------------------------
# PARSE_ERROR detection (ADR-9)
# ---------------------------------------------------------------------------


def has_zero_ast_nodes(tu: Any) -> bool:
    """Return True iff the TU cursor has no children (zero AST output)."""
    try:
        return not any(True for _ in tu.cursor.get_children())
    except Exception:
        return True


def has_fatal_diagnostics(tu: Any) -> bool:
    """Return True iff *tu* has at least one Fatal-severity diagnostic."""
    try:
        for diag in tu.diagnostics:
            # clang.cindex.Diagnostic.Fatal == 4
            if int(diag.severity) >= 4:
                return True
    except Exception:
        pass
    return False
