"""cpp_get_references — find all usages of a C++ symbol in the current TU.

Scope per ADR-1/OQ-3: single TU only for v1. Walks the TU AST to collect
cursors whose referenced USR matches the target symbol's USR.

Response shape (success):
  {
    "usr": str,
    "references": [
      { "file": str, "line": int, "col": int, "context_snippet": str },
      ...
    ],
    "truncated": bool,
    "omitted_count": int,
    "flags_source": "compilation_db" | "default",
    "request_id": str,
  }

Empty references list is a valid (non-error) result (US-2/AC-2).
Large reference lists may be truncated with ``truncated=True`` and
``omitted_count`` > 0 (US-2/AC-7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.cursor import cursor_at
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

        # Skip the declaration/definition itself.
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


async def _get_references_impl(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Core logic for cpp_get_references; raises domain exceptions on error."""
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
    target_usr = cursor.get_usr() or ""

    # --- Collect references ---
    all_refs = _collect_references(tu, target_usr)

    # --- Truncation ---
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


async def get_references(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Async entry point used directly by BDD tests and MCP server app."""
    return await _get_references_impl(
        file_path=file_path,
        line=line,
        col=col,
        build_path=build_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )
