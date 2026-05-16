"""cpp_get_preprocessor_state tool: retrieve macro definitions and conditional state.

US-6 / ADR-1 (OQ-7: include transitive macros, tag each with defined_at.file).

Requires PARSE_DETAILED_PROCESSING_RECORD so that macro-definition cursors appear
in the TU. This is achieved by passing options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
to ClangSession.parse (Story 6 deviation — adds optional `options` param to session.parse).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.error_envelope import wrap_tool
from cpp_mcp.core.path_guard import validate_path

_TOOL_NAME = "cpp_get_preprocessor_state"

# TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD == 1
_PARSE_DETAILED = 1


def _collect_macros(tu: Any) -> list[dict[str, Any]]:
    """Walk *tu*'s cursor for MACRO_DEFINITION cursors.

    Returns list of {name, value, defined_at: {file, line} | None}.
    Command-line (-D) macros have no file location, so defined_at=None.
    """
    macros: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _visit(cursor: Any) -> None:
        try:
            kind_name = cursor.kind.name
        except Exception:
            kind_name = ""

        if kind_name == "MACRO_DEFINITION":
            try:
                name = cursor.spelling or ""
            except Exception:
                name = ""

            if name and name not in seen:
                seen.add(name)
                loc = cursor.location
                if loc.file:
                    defined_at: dict[str, Any] | None = {
                        "file": loc.file.name,
                        "line": loc.line,
                    }
                else:
                    # Defined via -D flag or built-in; no source location.
                    defined_at = None

                # Try to get macro body/value via token traversal.
                value = _extract_macro_value(cursor)
                macros.append(
                    {
                        "name": name,
                        "value": value,
                        "defined_at": defined_at,
                    }
                )

        for child in cursor.get_children():
            _visit(child)

    _visit(tu.cursor)
    return macros


def _extract_macro_value(cursor: Any) -> str:
    """Extract the macro replacement text from a MACRO_DEFINITION cursor.

    Tokenises the cursor's extent and returns everything after the macro name.
    Returns empty string on any error.
    """
    try:
        tokens = list(cursor.get_tokens())
        # tokens[0] is the macro name; everything after is the value.
        if len(tokens) <= 1:
            return ""
        return " ".join(t.spelling for t in tokens[1:])
    except Exception:
        return ""


def _collect_conditionals(tu: Any) -> list[dict[str, Any]]:
    """Collect preprocessor conditional directives from *tu*'s cursor.

    Looks for MACRO_INSTANTIATION cursors whose spelling matches #ifdef/#ifndef/#if.
    In practice, libclang does not expose conditional AST nodes directly as cursors.
    We approximate by scanning diagnostics and token streams for conditional markers.

    This implementation uses a token-level scan of the main file to locate #ifdef,
    #ifndef, and #if directives and determines their evaluated result by checking
    whether the enclosed cursors exist in the TU.
    """
    # Walk the cursor tree looking for INCLUSION_DIRECTIVE and other preprocessor marks.
    # For conditionals we build a lightweight list from cursor traversal.
    conditionals: list[dict[str, Any]] = []
    seen_lines: set[int] = set()

    def _visit(cursor: Any) -> None:
        try:
            kind_name = cursor.kind.name
        except Exception:
            kind_name = ""

        # MACRO_INSTANTIATION cursors appear at conditional-check sites.
        if kind_name in ("MACRO_INSTANTIATION",):
            try:
                loc = cursor.location
                if loc.file and loc.line not in seen_lines:
                    seen_lines.add(loc.line)
                    name = cursor.spelling or ""
                    conditionals.append(
                        {
                            "directive": "#ifdef",
                            "condition": name,
                            "evaluated_result": True,
                            "start_line": loc.line,
                            "end_line": loc.line,
                        }
                    )
            except Exception:
                pass

        for child in cursor.get_children():
            _visit(child)

    # Better approach: use token-level scan if possible.
    try:
        conditionals = _scan_conditionals_via_tokens(tu)
    except Exception:
        _visit(tu.cursor)

    return conditionals


def _scan_conditionals_via_tokens(tu: Any) -> list[dict[str, Any]]:
    """Scan TU tokens for #ifdef / #ifndef / #if / #endif directives.

    Determines evaluated_result by whether the corresponding block produced
    any cursors in the TU (heuristic: if the block is active, libclang will
    have parsed its contents and produced AST nodes).

    This is an approximation — libclang does not directly expose branch results.
    """
    import re

    conditionals: list[dict[str, Any]] = []

    try:
        # Get the main file content to scan.
        main_file = tu.spelling
        with open(main_file, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return conditionals

    # Build a set of lines that have AST cursors (indicating the line was parsed
    # = the branch was taken).
    active_lines: set[int] = set()

    def _collect_lines(cursor: Any) -> None:
        try:
            loc = cursor.location
            if loc.file and loc.file.name == main_file:
                active_lines.add(loc.line)
        except Exception:
            pass
        for child in cursor.get_children():
            _collect_lines(child)

    _collect_lines(tu.cursor)

    # Stack of open conditionals.
    stack: list[dict[str, Any]] = []
    ifdef_re = re.compile(r"^\s*#\s*(ifdef|ifndef|if|elif|else|endif)\b(.*)", re.IGNORECASE)

    for lineno, line_text in enumerate(lines, start=1):
        m = ifdef_re.match(line_text)
        if not m:
            continue
        directive_word = m.group(1).lower()
        condition = m.group(2).strip()

        if directive_word in ("ifdef", "ifndef", "if"):
            entry: dict[str, Any] = {
                "directive": f"#{directive_word}",
                "condition": condition,
                "evaluated_result": None,  # determined at #endif
                "start_line": lineno,
                "end_line": None,
            }
            stack.append(entry)
        elif directive_word in ("elif", "else"):
            if stack:
                prev = stack[-1]
                if prev["evaluated_result"] is None:
                    # Determine if previous branch was taken: any cursor in [prev_start, lineno-1]
                    prev_start = prev["start_line"] + 1
                    branch_active = any(prev_start <= al < lineno for al in active_lines)
                    prev["evaluated_result"] = branch_active
                    completed = dict(prev)
                    completed["end_line"] = lineno - 1
                    conditionals.append(completed)

                new_entry: dict[str, Any] = {
                    "directive": f"#{directive_word}",
                    "condition": condition,
                    "evaluated_result": None,
                    "start_line": lineno,
                    "end_line": None,
                }
                stack[-1] = new_entry
        elif directive_word == "endif":
            if stack:
                top = stack.pop()
                if top["evaluated_result"] is None:
                    prev_start = top["start_line"] + 1
                    branch_active = any(prev_start <= al <= lineno for al in active_lines)
                    top["evaluated_result"] = branch_active
                top["end_line"] = lineno
                conditionals.append(top)

    # Any unclosed conditionals.
    for entry in stack:
        if entry["evaluated_result"] is None:
            entry["evaluated_result"] = False
        if entry["end_line"] is None:
            entry["end_line"] = len(lines)
        conditionals.append(entry)

    return conditionals


async def cpp_get_preprocessor_state(
    file_path: str,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    build_path: str | None = None,
) -> dict[str, Any]:
    """Retrieve active macro definitions and evaluated conditional branch state.

    Args:
        file_path: Path to the C++ file (must be within allowed_roots).
        allowed_roots: Tuple of allowed root directories (from config).
        default_flags: Compiler flags to use when no compile_commands.json found.
        session: ClangSession instance for parsing.
        build_path: Optional path to a build directory with compile_commands.json.

    Returns:
        Dict with macros and conditionals lists.
    """
    validated_file = validate_path(file_path, allowed_roots, kind="file")

    validated_build: Path | None = None
    if build_path is not None:
        validated_build = validate_path(build_path, allowed_roots, kind="dir")

    flags, flags_source = resolve_flags(validated_file, validated_build, default_flags)

    # PARSE_DETAILED_PROCESSING_RECORD is required to expose macro-definition cursors.
    tu, cache_hit = await session.parse(
        validated_file, validated_build, flags, options=_PARSE_DETAILED
    )

    macros = _collect_macros(tu)
    conditionals = _collect_conditionals(tu)

    return {
        "macros": macros,
        "conditionals": conditionals,
        "flags_source": flags_source,
        "cache_hit": cache_hit,
    }


def make_cpp_get_preprocessor_state(
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
        return await cpp_get_preprocessor_state(
            file_path=file_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            build_path=build_path,
        )

    return _tool
