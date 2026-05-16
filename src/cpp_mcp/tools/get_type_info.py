"""cpp_get_type_info — retrieve type details for a C++ symbol at a source position.

Resolves the cursor type including:
  - ``auto``-typed variables (canonical type resolves the concrete type).
  - Template instantiations (display_type includes template arguments).
  - Incomplete types (size/alignment returned as None — not an error).

Response shape (success):
  {
    "display_type": str,         # spelling as written (e.g. "auto", "int *")
    "canonical_type": str,       # fully resolved type (e.g. "float", "int *")
    "size_bytes": int | None,    # None for incomplete types
    "alignment_bytes": int | None,
    "is_pod": bool,
    "is_const": bool,
    "is_reference": bool,
    "is_pointer": bool,
    "flags_source": "compilation_db" | "default",
    "request_id": str,
  }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.cursor import cursor_at
from cpp_mcp.core.path_guard import validate_path

# Sentinel for "size undefined" returned by libclang for incomplete types.
_INVALID_SIZE: int = -1


def _safe_size(value: int) -> int | None:
    """Return *value* if it indicates a valid size, else None."""
    return value if value > 0 else None


async def _get_type_info_impl(
    file_path: str,
    line: int,
    col: int,
    build_path: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
) -> dict[str, Any]:
    """Core logic for cpp_get_type_info; raises domain exceptions on error."""
    import clang.cindex as ci

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

    # --- Extract type information ---
    typ = cursor.type
    canonical = typ.get_canonical()

    display_type = typ.spelling
    canonical_type = canonical.spelling

    # Size/alignment: libclang returns -1 for incomplete types.
    raw_size = typ.get_size()
    raw_align = typ.get_align()

    size_bytes = _safe_size(raw_size)
    alignment_bytes = _safe_size(raw_align)

    is_const = typ.is_const_qualified()
    is_reference = (
        typ.kind == ci.TypeKind.LVALUEREFERENCE or typ.kind == ci.TypeKind.RVALUEREFERENCE
    )
    is_pointer = typ.kind == ci.TypeKind.POINTER

    # POD check: use canonical type's isPODType if available, fall back to False.
    try:
        is_pod: bool = bool(canonical.is_pod())
    except Exception:
        is_pod = False

    return {
        "display_type": display_type,
        "canonical_type": canonical_type,
        "size_bytes": size_bytes,
        "alignment_bytes": alignment_bytes,
        "is_pod": is_pod,
        "is_const": is_const,
        "is_reference": is_reference,
        "is_pointer": is_pointer,
        "flags_source": flags_source,
        "cache_hit": cache_hit,
        "request_id": request_id,
    }


async def get_type_info(
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
    return await _get_type_info_impl(
        file_path=file_path,
        line=line,
        col=col,
        build_path=build_path,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
    )
