"""cpp_get_definition — navigate to the canonical definition of a C++ symbol.

Given a file path and source position (line, col), resolve the cursor at that
location and return the canonical definition location (file, line, col, USR).

Handles:
  - Macro expansion sites (libclang may return the macro definition or None).
  - Forward declarations with no reachable definition → definition_found=False.
  - All standard error codes via raised domain exceptions (caught by wrap_tool).

Response shape (success):
  {
    "definition_found": bool,
    "file": str | None,          # absolute path
    "line": int | None,
    "col": int | None,
    "usr": str,
    "flags_source": "compilation_db" | "default",
    "request_id": str,
  }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.cursor import cursor_at
from cpp_mcp.core.error_envelope import InvalidArgumentError, wrap_tool
from cpp_mcp.core.path_guard import validate_path


async def _get_definition_impl(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Core logic for cpp_get_definition; raises domain exceptions on error."""
    # --- Path validation ---
    resolved_file = validate_path(file_path, allowed_roots, kind="file")

    resolved_build: Path | None = None
    if build_path is not None:
        resolved_build = validate_path(build_path, allowed_roots, kind="dir")

    # --- Resolve compiler flags ---
    flags, flags_source = resolve_flags(resolved_file, resolved_build, default_flags)

    # --- Parse the TU (cached) ---
    tu, cache_hit = await session.parse(resolved_file, resolved_build, flags)

    # --- Get cursor at position ---
    cursor = cursor_at(tu, resolved_file, line, col)

    # --- Resolve definition ---
    definition = cursor.get_definition()

    if definition is None or not definition.location.file:
        return {
            "definition_found": False,
            "file": None,
            "line": None,
            "col": None,
            "usr": cursor.get_usr() or "",
            "flags_source": flags_source,
            "cache_hit": cache_hit,
            "request_id": request_id,
        }

    def_loc = definition.location
    return {
        "definition_found": True,
        "file": str(def_loc.file.name),
        "line": def_loc.line,
        "col": def_loc.column,
        "usr": definition.get_usr() or "",
        "flags_source": flags_source,
        "cache_hit": cache_hit,
        "request_id": request_id,
    }


def make_get_definition_tool(
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
) -> Any:
    """Factory: return a cpp_get_definition callable bound to *session* and config.

    The returned function is decorated with ``wrap_tool`` and is suitable for
    registration with the MCP server.

    Args:
        allowed_roots: Tuple of allowed root directory strings (from config).
        default_flags: Default compiler flags (from config).
        session: ``ClangSession`` instance providing the async ``parse`` method.

    Returns:
        An async callable ``cpp_get_definition(file_path, line, col,
        build_path=None) -> dict``.
    """
    import asyncio
    import uuid

    @wrap_tool("cpp_get_definition")
    def cpp_get_definition(
        file_path: str,
        line: int,
        col: int,
        build_path: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(line, int) or not isinstance(col, int):
            raise InvalidArgumentError("line and col must be integers")
        request_id = uuid.uuid4().hex
        return asyncio.get_event_loop().run_until_complete(
            _get_definition_impl(
                file_path=file_path,
                line=line,
                col=col,
                build_path=build_path,
                allowed_roots=allowed_roots,
                default_flags=default_flags,
                session=session,
                request_id=request_id,
            )
        )

    return cpp_get_definition


async def get_definition(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Async entry point used directly by BDD tests and MCP server app.

    Raises domain exceptions; caller is responsible for wrapping with
    ``wrap_tool`` or catching exceptions manually.
    """
    return await _get_definition_impl(
        file_path=file_path,
        line=line,
        col=col,
        build_path=build_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )
