"""Path guard: validate caller-supplied paths against configured allowed roots.

ADR-3: allowed roots are a colon-separated list from CPP_MCP_ALLOWED_ROOTS.
ADR-4: resolve-then-check symlink policy.

Validation order per ADR-4:
  1. Reject if literal ``..`` segments appear in the raw input.
  2. Compute realpath (abspath + follow all symlinks).
  3. Reject if realpath is not under any allowed root (PATH_VIOLATION).
  4. Reject if path does not exist (FILE_NOT_FOUND).
  5. Reject if kind mismatch (INVALID_ARGUMENT: build_path is a file, not a dir).
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from cpp_mcp.core.error_envelope import (
    InvalidArgumentError,
    PathViolationError,
)


def _has_dotdot(raw: str) -> bool:
    """Return True iff any component of *raw* is the literal ``..`` segment."""
    return ".." in PurePath(raw).parts


def _under_any_root(resolved: str, allowed_roots: tuple[str, ...]) -> bool:
    """Return True iff *resolved* is equal to or inside one of *allowed_roots*."""
    for root in allowed_roots:
        try:
            common = os.path.commonpath([resolved, root])
        except ValueError:
            # Different drives on Windows — never matches.
            continue
        if common == root:
            return True
    return False


def validate_path(
    raw: str,
    allowed_roots: tuple[str, ...],
    kind: str = "file",
) -> Path:
    """Validate *raw* and return its resolved ``pathlib.Path``.

    Args:
        raw: Caller-supplied path string (may be relative, contain symlinks, etc.).
        allowed_roots: Tuple of absolute directory strings from config.
        kind: ``"file"`` or ``"dir"``.  When ``"dir"``, raises
            :exc:`InvalidArgumentError` if the resolved path is a regular file.

    Raises:
        PathViolationError: ``..`` literal detected, or resolved path is outside
            all allowed roots.
        FileNotFoundError: Resolved path does not exist on disk.
        InvalidArgumentError: *kind* is ``"dir"`` but path resolves to a file.

    Returns:
        Resolved absolute ``pathlib.Path`` (safe to hand to libclang / open).
    """
    if not raw:
        raise PathViolationError("Empty path is not allowed.")

    # Step 1 — reject literal .. segments before any syscall.
    if _has_dotdot(raw):
        raise PathViolationError(f"Path contains '..' traversal segment: {raw!r}")

    # Step 2 — compute abspath then follow all symlinks.
    resolved = os.path.realpath(os.path.abspath(raw))

    # Step 3 — check inclusion in any allowed root.
    if not _under_any_root(resolved, allowed_roots):
        raise PathViolationError(f"Path {raw!r} resolves outside the configured allowed roots.")

    # Step 4 — existence check (FILE_NOT_FOUND).
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Path does not exist: {raw!r}")

    resolved_path = Path(resolved)

    # Step 5 — kind check.
    if kind == "dir" and resolved_path.is_file():
        raise InvalidArgumentError(f"Expected a directory but got a regular file: {raw!r}")

    return resolved_path
