"""get_ast tool: return a hierarchical or graph-format annotated AST subtree.

S3: converted to sync def + @mcp.tool + Depends DI (ADR-3, ADR-7).
US-4 / ADR-5 (node + byte budget truncation), ADR-9 (PARSE_ERROR threshold).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp.dependencies import Depends
from pydantic import Field

from cpp_mcp.core.ast_walker import (
    has_fatal_diagnostics,
    has_zero_ast_nodes,
    walk_graph,
    walk_json,
)
from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.deps import (
    get_allowed_roots,
    get_ast_max_bytes,
    get_ast_max_nodes,
    get_default_flags,
    get_session,
)
from cpp_mcp.core.error_envelope import (
    FatalParseError,
    InvalidRangeError,
    wrap_tool,
)
from cpp_mcp.core.path_guard import validate_path

_TOOL_NAME = "get_ast"

_DEFAULT_DEPTH = 3
_DEFAULT_MAX_NODES = 5000
_DEFAULT_MAX_BYTES = 1_048_576


def _do_get_ast(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    build_path: str | None,
    format: str,
    depth: int,
    start_line: int | None,
    end_line: int | None,
    max_nodes: int,
    max_bytes: int,
) -> dict[str, Any]:
    """Blocking libclang work; MUST be executed on the single worker thread."""
    if start_line is not None and end_line is not None and start_line > end_line:
        raise InvalidRangeError(
            f"start_line ({start_line}) must not be greater than end_line ({end_line})"
        )

    validated_file = validate_path(file_path, allowed_roots, kind="file")

    validated_build: Path | None = None
    if build_path is not None:
        validated_build = validate_path(build_path, allowed_roots, kind="dir")

    flags, flags_source = resolve_flags(validated_file, validated_build, default_flags)
    tu, cache_hit = session._get_or_parse_sync(validated_file, validated_build, flags)

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


def get_ast(
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
    """Sync entry point used directly by BDD/unit tests.

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
        Dict with AST result or raises domain exception.
    """
    return _do_get_ast(
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


def _register(mcp: Any) -> None:
    """Register get_ast against *mcp*. Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="get_ast",
        description=(
            "Return an annotated AST subtree in JSON or graph format for a C++ source file."
        ),
    )
    @wrap_tool(_TOOL_NAME)
    def get_ast_tool(
        file_path: Annotated[str, "Absolute path to the C++ source file."],
        build_path: Annotated[
            str | None,
            "Optional path to the build directory containing compile_commands.json.",
        ] = None,
        format: Annotated[
            Literal["json", "graph"],
            Field(
                description="Output format: 'json' (hierarchical tree) or 'graph' (nodes+edges)."
            ),
        ] = "json",
        depth: Annotated[
            int,
            Field(ge=1, description="Maximum nesting depth for JSON format (default 3)."),
        ] = _DEFAULT_DEPTH,
        start_line: Annotated[
            int | None,
            "First line of line-range filter (1-based, inclusive).",
        ] = None,
        end_line: Annotated[
            int | None,
            "Last line of line-range filter (1-based, inclusive).",
        ] = None,
        *,
        session: Any = Depends(get_session),
        allowed_roots: tuple[str, ...] = Depends(get_allowed_roots),
        default_flags: tuple[str, ...] = Depends(get_default_flags),
        ast_max_nodes: int = Depends(get_ast_max_nodes),
        ast_max_bytes: int = Depends(get_ast_max_bytes),
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        result: dict[str, Any] = session.executor.submit(
            _do_get_ast,
            file_path,
            allowed_roots,
            default_flags,
            session,
            build_path,
            format,
            depth,
            start_line,
            end_line,
            ast_max_nodes,
            ast_max_bytes,
        ).result()
        result["request_id"] = request_id
        return result
