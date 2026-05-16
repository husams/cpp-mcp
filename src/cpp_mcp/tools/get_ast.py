"""cpp_get_ast tool: return a hierarchical or graph-format annotated AST subtree.

US-4 / ADR-5 (node + byte budget truncation), ADR-9 (PARSE_ERROR threshold).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cpp_mcp.core.ast_walker import (
    has_fatal_diagnostics,
    has_zero_ast_nodes,
    walk_graph,
    walk_json,
)
from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.error_envelope import (
    FatalParseError,
    InvalidRangeError,
    wrap_tool,
)
from cpp_mcp.core.path_guard import validate_path

_TOOL_NAME = "cpp_get_ast"

_DEFAULT_DEPTH = 3
_DEFAULT_MAX_NODES = 5000
_DEFAULT_MAX_BYTES = 1_048_576


def _run(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    build_path: str | None = None,
    format: str = "json",
    depth: int = _DEFAULT_DEPTH,
    start_line: int | None = None,
    end_line: int | None = None,
    max_nodes: int = _DEFAULT_MAX_NODES,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Core implementation (synchronous); called by the async wrapper below."""

    # --- Validate inputs ---
    if start_line is not None and end_line is not None and start_line > end_line:
        raise InvalidRangeError(
            f"start_line ({start_line}) must not be greater than end_line ({end_line})"
        )

    validated_file = validate_path(file_path, allowed_roots, kind="file")

    validated_build: Path | None = None
    if build_path is not None:
        validated_build = validate_path(build_path, allowed_roots, kind="dir")

    # --- Resolve flags ---
    flags, flags_source = resolve_flags(validated_file, validated_build, default_flags)

    # --- Parse TU (run synchronously inside the async tool; caller must ensure
    #     this is dispatched on the clang worker thread via session.parse) ---
    tu, _cache_hit = asyncio.get_event_loop().run_until_complete(
        session.parse(validated_file, validated_build, flags)
    )

    # --- PARSE_ERROR detection (ADR-9) ---
    if has_zero_ast_nodes(tu) and has_fatal_diagnostics(tu):
        raise FatalParseError(
            f"libclang produced zero AST nodes with fatal diagnostics for {file_path!r}"
        )

    # --- Walk the AST ---
    fmt = (format or "json").lower()
    if fmt == "graph":
        walk_result = walk_graph(tu, start_line, end_line, max_nodes, max_bytes)
    else:
        walk_result = walk_json(tu, depth, start_line, end_line, max_nodes, max_bytes)

    return {
        **walk_result,
        "flags_source": flags_source,
    }


async def cpp_get_ast(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    build_path: str | None = None,
    format: str = "json",
    depth: int = _DEFAULT_DEPTH,
    start_line: int | None = None,
    end_line: int | None = None,
    max_nodes: int = _DEFAULT_MAX_NODES,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Retrieve an annotated AST subtree for a C++ source file.

    Args:
        file_path: Path to the C++ source file (must be within allowed_roots).
        allowed_roots: Tuple of allowed root directories (from config).
        default_flags: Compiler flags to use when no compile_commands.json found.
        session: ClangSession instance for parsing.
        build_path: Optional path to a build directory with compile_commands.json.
        format: Output format — "json" (hierarchical) or "graph" (flat nodes+edges).
        depth: Maximum nesting depth for JSON format (default 3).
        start_line: First line of range filter (1-based, inclusive).
        end_line: Last line of range filter (1-based, inclusive).
        max_nodes: Node-count budget (ADR-5).
        max_bytes: Byte budget (ADR-5).

    Returns:
        Dict with AST result or error envelope.
    """
    # Validate range before any I/O.
    if start_line is not None and end_line is not None and start_line > end_line:
        raise InvalidRangeError(
            f"start_line ({start_line}) must not be greater than end_line ({end_line})"
        )

    validated_file = validate_path(file_path, allowed_roots, kind="file")

    validated_build: Path | None = None
    if build_path is not None:
        validated_build = validate_path(build_path, allowed_roots, kind="dir")

    flags, flags_source = resolve_flags(validated_file, validated_build, default_flags)

    tu, cache_hit = await session.parse(validated_file, validated_build, flags)

    if has_zero_ast_nodes(tu) and has_fatal_diagnostics(tu):
        raise FatalParseError(
            f"libclang produced zero AST nodes with fatal diagnostics for {file_path!r}"
        )

    fmt = (format or "json").lower()
    if fmt == "graph":
        walk_result = walk_graph(tu, start_line, end_line, max_nodes, max_bytes)
    else:
        walk_result = walk_json(tu, depth, start_line, end_line, max_nodes, max_bytes)

    return {
        **walk_result,
        "flags_source": flags_source,
        "cache_hit": cache_hit,
    }


def make_cpp_get_ast(
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    max_nodes: int = _DEFAULT_MAX_NODES,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> Any:
    """Return a wrap_tool-decorated callable bound to runtime config.

    Usage::

        get_ast = make_cpp_get_ast(config.allowed_roots, config.default_flags, session)
    """

    @wrap_tool(_TOOL_NAME)
    async def _tool(
        file_path: str,
        build_path: str | None = None,
        format: str = "json",
        depth: int = _DEFAULT_DEPTH,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        return await cpp_get_ast(
            file_path=file_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            build_path=build_path,
            format=format,
            depth=depth,
            start_line=start_line,
            end_line=end_line,
            max_nodes=max_nodes,
            max_bytes=max_bytes,
        )

    return _tool
