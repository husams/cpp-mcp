"""cpp_get_references — find all usages of a C++ symbol in the current TU.

S3: converted to sync def + @mcp.tool + Depends DI (ADR-3, ADR-7).

Response shape (success):
  {
    "usr": str,
    "references": [{"file": str, "line": int, "col": int, "context_snippet": str}, ...],
    "truncated": bool,
    "omitted_count": int,
    "flags_source": "compilation_db" | "default",
    "cache_hit": bool,
    "request_id": str,
  }

Empty references list is a valid (non-error) result (US-2/AC-2).
Large reference lists may be truncated with ``truncated=True`` (US-2/AC-7).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastmcp.dependencies import Depends

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.cursor import cursor_at
from cpp_mcp.core.deps import get_allowed_roots, get_default_flags, get_session
from cpp_mcp.core.error_envelope import wrap_tool
from cpp_mcp.core.path_guard import validate_path

# Maximum number of reference entries to return without truncation.
_MAX_REFERENCES = 1000


def _context_snippet(tu: Any, file: Any, line: int) -> str:
    """Return a one-line context snippet from *file* at *line*."""
    if file is None:
        return ""
    try:
        path = Path(file.name)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if 1 <= line <= len(lines):
            return lines[line - 1].strip()
    except OSError:
        pass
    return ""


def _collect_references(tu: Any, target_usr: str) -> list[dict[str, Any]]:
    """Walk *tu* AST and collect all cursors referencing *target_usr*."""
    results: list[dict[str, Any]] = []
    seen_locations: set[tuple[str, int, int]] = set()

    for cursor in tu.cursor.walk_preorder():
        if not cursor.location.file:
            continue
        if cursor.get_usr() == target_usr:
            continue
        ref = cursor.referenced
        if ref is None:
            continue
        if ref.get_usr() != target_usr:
            continue
        loc = cursor.location
        key = (loc.file.name, loc.line, loc.column)
        if key in seen_locations:
            continue
        seen_locations.add(key)
        results.append(
            {
                "file": loc.file.name,
                "line": loc.line,
                "col": loc.column,
                "context_snippet": _context_snippet(tu, loc.file, loc.line),
            }
        )

    return results


def _do_get_references(
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
    target_usr = cursor.get_usr() or ""

    all_refs = _collect_references(tu, target_usr)
    truncated = len(all_refs) > _MAX_REFERENCES
    omitted_count = max(0, len(all_refs) - _MAX_REFERENCES)
    references = all_refs[:_MAX_REFERENCES]

    return {
        "usr": target_usr,
        "references": references,
        "truncated": truncated,
        "omitted_count": omitted_count,
        "flags_source": flags_source,
        "cache_hit": cache_hit,
        "request_id": request_id,
    }


def get_references(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Sync entry point used directly by BDD/unit tests."""
    return _do_get_references(
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
    """Register cpp_get_references against *mcp*. Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="cpp_get_references",
        description="Find all usages of a C++ symbol within the current translation unit.",
    )
    @wrap_tool("cpp_get_references")
    def cpp_get_references(
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
        request_id = uuid.uuid4().hex
        return session.executor.submit(  # type: ignore[no-any-return]
            _do_get_references,
            file_path,
            line,
            col,
            build_path,
            allowed_roots,
            default_flags,
            session,
            request_id,
        ).result()
