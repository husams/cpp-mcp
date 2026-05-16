"""cursor_at: obtain the libclang cursor at a given (line, col) in a TranslationUnit.

Raises InvalidPositionError when:
  - line or col is <= 0 (1-based positions expected by libclang)
  - line exceeds the number of lines in the file
  - col exceeds the length of the given line
  - The resolved cursor kind is INVALID_FILE or the cursor is null
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpp_mcp.core.error_envelope import InvalidPositionError


def _count_lines(file_path: Path) -> int:
    """Count the number of lines in *file_path*."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise InvalidPositionError(f"Cannot read file to validate position: {exc}") from exc
    return len(text.splitlines()) or 1


def _line_length(file_path: Path, line: int) -> int:
    """Return the character length of *line* (1-based) in *file_path*."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise InvalidPositionError(f"Cannot read file to validate position: {exc}") from exc
    lines = text.splitlines()
    if line < 1 or line > len(lines):
        return 0
    return len(lines[line - 1])


def cursor_at(tu: Any, file_path: Path, line: int, col: int) -> Any:
    """Return the libclang cursor at (*line*, *col*) within *tu*.

    Args:
        tu: A ``clang.cindex.TranslationUnit``.
        file_path: Absolute path to the C++ source file (used for position validation).
        line: 1-based line number.
        col: 1-based column number.

    Returns:
        The ``clang.cindex.Cursor`` at the given location.

    Raises:
        InvalidPositionError: line/col is out of range, or libclang returns a
            null/TRANSLATION_UNIT cursor indicating no meaningful symbol there.
    """
    import clang.cindex as ci

    # --- Range checks (1-based) ---
    if line < 1 or col < 1:
        raise InvalidPositionError(f"line and col must be >= 1; got line={line}, col={col}")

    total_lines = _count_lines(file_path)
    if line > total_lines:
        raise InvalidPositionError(f"line {line} is beyond end of file ({total_lines} lines)")

    line_len = _line_length(file_path, line)
    if col > line_len + 1:
        # Allow col == line_len + 1 (one past end of line) for robustness with
        # trailing-newline conventions; anything further is invalid.
        raise InvalidPositionError(f"col {col} is beyond end of line {line} (length {line_len})")

    # --- Ask libclang for the cursor at this location ---
    src_file = tu.get_file(str(file_path))
    if src_file is None:
        raise InvalidPositionError(
            f"libclang cannot find file {file_path!s} in the TranslationUnit"
        )

    location = tu.get_location(str(file_path), (line, col))
    cursor = ci.Cursor.from_location(tu, location)

    if cursor is None:
        raise InvalidPositionError(f"No cursor found at {file_path}:{line}:{col}")

    # A TRANSLATION_UNIT cursor or INVALID_FILE means there is no meaningful
    # symbol at this position (e.g. whitespace, comment, or empty line).
    if cursor.kind in (
        ci.CursorKind.TRANSLATION_UNIT,
        ci.CursorKind.INVALID_FILE,
    ):
        raise InvalidPositionError(
            f"No symbol at {file_path}:{line}:{col} (cursor kind: {cursor.kind})"
        )

    return cursor
