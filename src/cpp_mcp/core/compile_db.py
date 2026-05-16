"""Compile-database resolution: extract per-file compiler flags from a build directory.

ADR-9 behavior summary:
  - build_path is None               → silent fallback to default_flags, source="default"
  - build_path is an existing file   → raise InvalidArgumentError (not PATH_VIOLATION; ADR-9)
  - build_path directory has no / malformed compile_commands.json
                                     → log WARN, silent fallback to default_flags, source="default"
  - file_path not listed in DB       → silent fallback to default_flags, source="default"
  - file_path listed in DB           → return DB flags (minus compiler binary),
                                       source="compilation_db"

validate_path(build_path, kind="dir") is the caller's responsibility at the tool layer
(Stories 5-7) where allowed_roots are available. resolve_flags is a pure function that
receives an already-resolved Path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from cpp_mcp.core.error_envelope import InvalidArgumentError

logger = logging.getLogger(__name__)

# Sentinel: libclang inserts '--' in the argument list to separate driver args from the
# filename when it cannot find the file in the compilation database (synthetic fallback).
# A real DB hit does NOT contain '--' in its argument list.
_SYNTHETIC_SEPARATOR = "--"


def _load_compile_db(build_path: Path) -> Any:
    """Load a CompilationDatabase from *build_path*; return None on any loading failure.

    Catches both CompilationDatabaseError (missing/malformed JSON) and any other
    unexpected exception so the caller always gets a clean None-or-DB result.
    """
    try:
        # Import lazily so modules that never call resolve_flags don't trigger the
        # libclang load (which may fail if libclang.dylib is absent on the host).
        import clang.cindex as ci

        return ci.CompilationDatabase.fromDirectory(str(build_path))
    except Exception as exc:
        # CompilationDatabaseError is the documented exception; we also catch the broad
        # base in case the libclang binding raises something unexpected (e.g. on newer
        # Xcode versions).
        logger.warning(
            "compile_db: failed to load CompilationDatabase from %s: %s",
            build_path,
            exc,
        )
        return None


def _extract_flags(db: Any, file_path: Path) -> tuple[str, ...] | None:
    """Return compiler flags for *file_path* from *db*, or None if not in the DB.

    libclang's getCompileCommands returns a synthetic entry (with '--' separator)
    for files not present in the DB, so we detect that case and return None.
    """
    compile_commands = db.getCompileCommands(str(file_path))
    if compile_commands is None:
        return None

    entries = list(compile_commands)
    if not entries:
        return None

    cmd = entries[0]
    args: list[str] = list(cmd.arguments)

    # Detect synthetic (file-not-in-DB) fallback: libclang inserts '--' before filename.
    if _SYNTHETIC_SEPARATOR in args:
        return None

    # Real DB hit: args = [compiler_binary, ...flags..., filename]
    # Drop the first arg (compiler binary) and the last arg (the source filename).
    if len(args) < 2:  # pragma: no cover — defensive; shouldn't happen for real entries
        return ()
    return tuple(args[1:-1])


def resolve_flags(
    file_path: Path,
    build_path: Path | None,
    default_flags: tuple[str, ...],
) -> tuple[tuple[str, ...], Literal["compilation_db", "default"]]:
    """Resolve compiler flags for *file_path* from the compilation database.

    Args:
        file_path: Resolved absolute path to the C++ source file being analysed.
        build_path: Resolved absolute path to the build directory that should
            contain ``compile_commands.json``, or ``None`` to skip DB lookup.
        default_flags: Fallback flags used when the DB is absent, malformed,
            or does not list *file_path*.

    Returns:
        A 2-tuple ``(flags, source)`` where *flags* is a tuple of compiler flag
        strings and *source* is ``"compilation_db"`` or ``"default"``.

    Raises:
        InvalidArgumentError: *build_path* is a non-None path that exists on
            disk as a regular file rather than a directory (ADR-9 / OQ-NEW-1).
    """
    # --- Fast path: no build_path supplied ---
    if build_path is None:
        return default_flags, "default"

    # --- Guard: build_path must not be a regular file ---
    if build_path.is_file():
        raise InvalidArgumentError("build_path must be a directory; got a regular file")

    # --- Attempt to load the compilation database ---
    db = _load_compile_db(build_path)
    if db is None:
        # Loading failed (missing or malformed compile_commands.json): silent fallback.
        return default_flags, "default"

    # --- Look up the file in the DB ---
    flags = _extract_flags(db, file_path)
    if flags is None:
        logger.debug(
            "compile_db: %s not found in DB at %s; using default flags",
            file_path,
            build_path,
        )
        return default_flags, "default"

    return flags, "compilation_db"
