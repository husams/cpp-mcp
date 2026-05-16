"""cpp_get_type_info — retrieve type details for a C++ symbol at a source position.

S3: converted to sync def + @mcp.tool + Depends DI (ADR-3, ADR-7).

Response shape (success):
  {
    "display_type": str,
    "canonical_type": str,
    "size_bytes": int | None,
    "alignment_bytes": int | None,
    "is_pod": bool,
    "is_const": bool,
    "is_reference": bool,
    "is_pointer": bool,
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
from cpp_mcp.core.error_envelope import wrap_tool
from cpp_mcp.core.path_guard import validate_path

# Sentinel for "size undefined" returned by libclang for incomplete types.
_INVALID_SIZE: int = -1


def _safe_size(value: int) -> int | None:
    """Return *value* if it indicates a valid size, else None."""
    return value if value > 0 else None


def _do_get_type_info(
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
    import clang.cindex as ci

    resolved_file = validate_path(file_path, allowed_roots, kind="file")

    resolved_build: Path | None = None
    if build_path is not None:
        resolved_build = validate_path(build_path, allowed_roots, kind="dir")

    flags, flags_source = resolve_flags(resolved_file, resolved_build, default_flags)
    tu, cache_hit = session._get_or_parse_sync(resolved_file, resolved_build, flags)
    cursor = cursor_at(tu, resolved_file, line, col)

    typ = cursor.type
    canonical = typ.get_canonical()

    display_type = typ.spelling
    canonical_type = canonical.spelling

    raw_size = typ.get_size()
    raw_align = typ.get_align()

    size_bytes = _safe_size(raw_size)
    alignment_bytes = _safe_size(raw_align)

    is_const = typ.is_const_qualified()
    is_reference = (
        typ.kind == ci.TypeKind.LVALUEREFERENCE or typ.kind == ci.TypeKind.RVALUEREFERENCE
    )
    is_pointer = typ.kind == ci.TypeKind.POINTER

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


def get_type_info(
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
    return _do_get_type_info(
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
    """Register cpp_get_type_info against *mcp*. Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="cpp_get_type_info",
        description=(
            "Retrieve type details (size, alignment, qualifiers, canonical form) for a C++ symbol."
        ),
    )
    @wrap_tool("cpp_get_type_info")
    def cpp_get_type_info(
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
            _do_get_type_info,
            file_path,
            line,
            col,
            build_path,
            allowed_roots,
            default_flags,
            session,
            request_id,
        ).result()
