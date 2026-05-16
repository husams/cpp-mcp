"""cpp_get_header_info tool: inspect include graph and exported symbols.

US-5 / ADR-1 (OQ-6: orphaned = no symbol from include used in current TU).
Uses tu.get_includes() for transitive include resolution (no extra parse options needed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.error_envelope import wrap_tool
from cpp_mcp.core.path_guard import validate_path

_TOOL_NAME = "cpp_get_header_info"


def _cursor_kind_name(cursor: Any) -> str:
    try:
        name: str = cursor.kind.name
        return name
    except Exception:
        return "UNKNOWN"


# CursorKind names considered "public exported symbols" (API surface).
_EXPORTED_KINDS: frozenset[str] = frozenset(
    {
        "FUNCTION_DECL",
        "CXX_METHOD",
        "CONSTRUCTOR",
        "DESTRUCTOR",
        "STRUCT_DECL",
        "CLASS_DECL",
        "CLASS_TEMPLATE",
        "FUNCTION_TEMPLATE",
        "TYPEDEF_DECL",
        "TYPE_ALIAS_DECL",
        "NAMESPACE",
        "VAR_DECL",
        "ENUM_DECL",
    }
)


def _collect_exported_symbols(tu: Any) -> list[dict[str, Any]]:
    """Collect top-level non-system symbols from *tu*'s cursor."""
    symbols: list[dict[str, Any]] = []

    def _visit(cursor: Any) -> None:
        try:
            loc = cursor.location
            if not loc.file:
                return  # built-in / system
            kind_name = _cursor_kind_name(cursor)
            if kind_name not in _EXPORTED_KINDS:
                return
            # Only include cursors in the main file or included headers.
            try:
                usr = cursor.get_usr() or ""
            except Exception:
                usr = ""

            try:
                sig = cursor.displayname or cursor.spelling or ""
            except Exception:
                sig = ""

            symbols.append(
                {
                    "kind": kind_name,
                    "name": cursor.spelling or "",
                    "usr": usr,
                    "signature": sig,
                    "file": loc.file.name if loc.file else None,
                    "line": loc.line,
                }
            )
        except Exception:
            pass
        for child in cursor.get_children():
            _visit(child)

    _visit(tu.cursor)
    return symbols


def _collect_usrs_in_main_file(tu: Any, main_file: str) -> frozenset[str]:
    """Collect all USRs referenced in the main translation unit file."""
    usrs: set[str] = set()

    def _visit(cursor: Any) -> None:
        try:
            loc = cursor.location
            if loc.file and loc.file.name == main_file:
                try:
                    ref = cursor.referenced
                    if ref is not None:
                        usr = ref.get_usr()
                        if usr:
                            usrs.add(usr)
                except Exception:
                    pass
        except Exception:
            pass
        for child in cursor.get_children():
            _visit(child)

    _visit(tu.cursor)
    return frozenset(usrs)


def _collect_usrs_in_file(tu: Any, file_name: str) -> frozenset[str]:
    """Collect all USRs *defined or declared* in *file_name*."""
    usrs: set[str] = set()

    def _visit(cursor: Any) -> None:
        try:
            loc = cursor.location
            if loc.file and loc.file.name == file_name:
                try:
                    usr = cursor.get_usr()
                    if usr:
                        usrs.add(usr)
                except Exception:
                    pass
        except Exception:
            pass
        for child in cursor.get_children():
            _visit(child)

    _visit(tu.cursor)
    return frozenset(usrs)


async def cpp_get_header_info(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    build_path: str | None = None,
) -> dict[str, Any]:
    """Retrieve include graph and exported symbols for a C++ header or source file.

    Args:
        file_path: Path to the C++ file (must be within allowed_roots).
        allowed_roots: Tuple of allowed root directories (from config).
        default_flags: Compiler flags to use when no compile_commands.json found.
        session: ClangSession instance for parsing.
        build_path: Optional path to a build directory with compile_commands.json.

    Returns:
        Dict with include info, exported symbols, missing/orphaned includes.
    """
    validated_file = validate_path(file_path, allowed_roots, kind="file")

    validated_build: Path | None = None
    if build_path is not None:
        validated_build = validate_path(build_path, allowed_roots, kind="dir")

    flags, flags_source = resolve_flags(validated_file, validated_build, default_flags)

    tu, cache_hit = await session.parse(validated_file, validated_build, flags)

    main_file_str = str(validated_file)

    # --- Collect includes via tu.get_includes() ---
    direct_includes: list[str] = []
    transitive_includes: list[str] = []
    missing_includes: list[str] = []

    try:
        all_includes = list(tu.get_includes())
    except Exception:
        all_includes = []

    seen_transitive: set[str] = set()
    for inc in all_includes:
        try:
            include_file = inc.include.name if inc.include else None
        except Exception:
            include_file = None

        if include_file is None:
            # Unresolved include — collect from diagnostics below.
            continue

        if inc.depth == 1 and include_file not in direct_includes:
            direct_includes.append(include_file)

        if include_file not in seen_transitive:
            seen_transitive.add(include_file)
            transitive_includes.append(include_file)

    # Missing includes: pick up from diagnostics (file-not-found messages).
    for diag in tu.diagnostics:
        msg = diag.spelling or ""
        if "file not found" in msg.lower() or "no such file" in msg.lower():
            # Extract the include name from the message.
            # Common format: "'foo.h' file not found"
            import re

            m = re.search(r"['\"]([^'\"]+)['\"]", msg)
            if m:
                inc_name = m.group(1)
                if inc_name not in missing_includes:
                    missing_includes.append(inc_name)

    # Orphaned includes (ADR-1 / OQ-6): direct includes with no symbols used
    # in the main file's cursor tree.
    referenced_usrs = _collect_usrs_in_main_file(tu, main_file_str)
    orphaned_includes: list[str] = []
    for inc_path in direct_includes:
        defined_usrs = _collect_usrs_in_file(tu, inc_path)
        if defined_usrs and not defined_usrs.intersection(referenced_usrs):
            orphaned_includes.append(inc_path)

    # Exported symbols.
    exported_symbols = _collect_exported_symbols(tu)

    return {
        "direct_includes": direct_includes,
        "transitive_includes": transitive_includes,
        "exported_symbols": exported_symbols,
        "missing_includes": missing_includes,
        "orphaned_includes": orphaned_includes,
        "flags_source": flags_source,
        "cache_hit": cache_hit,
    }


def make_cpp_get_header_info(
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
) -> Any:
    """Return a wrap_tool-decorated callable bound to runtime config."""

    @wrap_tool(_TOOL_NAME)
    async def _tool(
        file_path: str,
        build_path: str | None = None,
    ) -> dict[str, Any]:
        return await cpp_get_header_info(
            file_path=file_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            build_path=build_path,
        )

    return _tool
