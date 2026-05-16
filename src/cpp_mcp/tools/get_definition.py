"""cpp_get_definition — navigate to the canonical definition of a C++ symbol.

S3: converted to sync def + @mcp.tool + Depends DI (ADR-3, ADR-7).

Given a file path and source position (line, col), resolve the cursor at that
location and return the canonical definition location (file, line, col, USR).

Response shape (success):
  {
    "definition_found": bool,
    "file": str | None,
    "line": int | None,
    "col": int | None,
    "usr": str,
    "flags_source": "compilation_db" | "default",
    "cache_hit": bool,
    "request_id": str,
  }
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastmcp.dependencies import Depends

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.cursor import cursor_at
from cpp_mcp.core.deps import get_allowed_roots, get_default_flags, get_session
from cpp_mcp.core.error_envelope import InvalidArgumentError, wrap_tool
from cpp_mcp.core.path_guard import validate_path


def _do_get_definition(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Blocking libclang work; MUST be executed on the single worker thread."""
    resolved_file = validate_path(file_path, allowed_roots, kind="file")

    resolved_build: Path | None = None
    if build_path is not None:
        resolved_build = validate_path(build_path, allowed_roots, kind="dir")

    flags, flags_source = resolve_flags(resolved_file, resolved_build, default_flags)
    tu, cache_hit = session._get_or_parse_sync(resolved_file, resolved_build, flags)
    cursor = cursor_at(tu, resolved_file, line, col)
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


def get_definition(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Sync entry point used directly by BDD/unit tests.

    Raises domain exceptions; caller is responsible for wrapping with
    ``wrap_tool`` or catching exceptions manually.
    """
    return _do_get_definition(
        file_path=file_path,
        line=line,
        col=col,
        build_path=build_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )


def _register(mcp: Any) -> None:
    """Register cpp_get_definition against *mcp*. Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="cpp_get_definition",
        description=(
            "Navigate to the canonical definition of a C++ symbol at a given source position."
        ),
    )
    @wrap_tool("cpp_get_definition")
    def cpp_get_definition(
        file_path: Annotated[str, "Absolute path to the C++ source file."],
        line: Annotated[int, "1-based line number of the symbol."],
        col: Annotated[int, "1-based column number of the symbol."],
        build_path: Annotated[
            str | None,
            "Optional path to the build directory containing compile_commands.json.",
        ] = None,
        *,
        session: Any = Depends(get_session),
        allowed_roots: tuple[str, ...] = Depends(get_allowed_roots),
        default_flags: tuple[str, ...] = Depends(get_default_flags),
    ) -> dict[str, Any]:
        if not isinstance(line, int) or not isinstance(col, int):
            raise InvalidArgumentError("line and col must be integers")
        request_id = uuid.uuid4().hex
        return session.executor.submit(  # type: ignore[no-any-return]
            _do_get_definition,
            file_path,
            line,
            col,
            build_path,
            allowed_roots,
            default_flags,
            session,
            request_id,
        ).result()
