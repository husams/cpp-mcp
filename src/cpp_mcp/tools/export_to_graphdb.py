"""cpp_export_to_graphdb MCP tool implementation.

Validation order (per ADR-7 / scenarios.md):
  1. INVALID_ARGUMENT — missing or empty db_uri / build_path.
  2. PATH_VIOLATION   — path traversal in file_path_or_dir or build_path.
  3. FILE_NOT_FOUND   — path does not exist after validation.
  4. DB_UNREACHABLE   — driver.connect() fails.
  5. Per-file work    — parse + export; partial failures recorded in errors[].
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from cpp_mcp.core.clang_session import ClangSession
from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    InvalidArgumentError,
)
from cpp_mcp.core.path_guard import validate_path
from cpp_mcp.graphdb.exporter import collect_cpp_files, export_file
from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

logger = logging.getLogger(__name__)

_TOOL_NAME = "cpp_export_to_graphdb"


async def cpp_export_to_graphdb(
    *,
    file_path_or_dir: str,
    build_path: str | None,
    db_uri: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: ClangSession,
    request_id: str,
    recursive: bool = False,
) -> dict[str, Any]:
    """Export C++ symbols from *file_path_or_dir* to a graph database.

    Args:
        file_path_or_dir: Absolute path to a C++ file or directory.
        build_path: Absolute path to the build directory (required for this tool).
        db_uri: Bolt URI for the graph database (required).
        allowed_roots: Tuple of allowed root directories.
        default_flags: Default compiler flags tuple.
        session: Shared :class:`ClangSession`.
        request_id: UUID hex string for log correlation.
        recursive: If True, recurse into sub-directories.

    Returns:
        Success payload: ``{files_processed, nodes_written, edges_written, errors}``.

    Raises:
        :exc:`InvalidArgumentError`: Missing / empty ``db_uri`` or ``build_path``.
        :exc:`PathViolationError`: Path traversal detected.
        :exc:`FileNotFoundError`: Path does not exist.
        :exc:`DBUnreachableError`: Cannot connect to the graph database.
    """
    # ------------------------------------------------------------------
    # 1. INVALID_ARGUMENT — argument presence / emptiness checks
    # ------------------------------------------------------------------
    if not db_uri:
        raise InvalidArgumentError(
            "db_uri is required and must be a non-empty string for cpp_export_to_graphdb."
        )

    if not build_path:
        raise InvalidArgumentError(
            "build_path is required and must be a non-empty string for cpp_export_to_graphdb."
        )

    # ------------------------------------------------------------------
    # 2. PATH_VIOLATION — validate paths before any I/O or DB connection
    # ------------------------------------------------------------------
    # Validate build_path as a directory (raises PathViolationError or
    # FileNotFoundError or InvalidArgumentError if it's a regular file).
    validated_build = validate_path(build_path, allowed_roots, kind="dir")

    # file_path_or_dir can be either a file or a directory; validate without
    # kind enforcement (path_guard existence + root check is sufficient here).
    validated_input = validate_path(file_path_or_dir, allowed_roots, kind="file")
    # If it's a directory the above will succeed only if it exists and is in
    # the allowed root — we don't care about the file/dir distinction until
    # we call collect_cpp_files, which handles both.
    # (path_guard kind="file" allows directories through because is_file() is
    # False for dirs and the kind check only rejects files when kind="dir".)

    # ------------------------------------------------------------------
    # 3. FILE_NOT_FOUND — already handled by validate_path's existence check
    #    (raises FileNotFoundError if the path does not exist).
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 4. DB_UNREACHABLE — connect before parsing any files
    # ------------------------------------------------------------------
    driver = Neo4jDriver()
    try:
        await asyncio.get_running_loop().run_in_executor(None, lambda: driver.connect(db_uri))
    except DBUnreachableError:
        raise
    except Exception as exc:
        raise DBUnreachableError(f"Cannot reach graph database at {db_uri!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # 5. Per-file export (partial failure aggregation per US-7/AC-5)
    # ------------------------------------------------------------------
    cpp_files = collect_cpp_files(validated_input, recursive=recursive)

    total_nodes = 0
    total_edges = 0
    errors: list[dict[str, Any]] = []
    files_processed = 0

    for cpp_file in cpp_files:
        try:
            flags, _source = resolve_flags(
                file_path=cpp_file,
                build_path=validated_build,
                default_flags=default_flags,
            )
            tu, _hit = await session.parse(cpp_file, validated_build, flags)

            loop = asyncio.get_running_loop()

            def _do_export(
                f: Any = cpp_file,
                t: Any = tu,
            ) -> dict[str, Any]:
                return export_file(f, t, driver)

            result = await loop.run_in_executor(None, _do_export)
            total_nodes += result["nodes_written"]
            total_edges += result["edges_written"]
            files_processed += 1
        except Exception as exc:
            logger.warning("Export failed for %s: %r", cpp_file, exc)
            errors.append(
                {
                    "file": str(cpp_file),
                    "code": type(exc).__name__,
                    "message": str(exc),
                }
            )

    # Always close the driver.
    with contextlib.suppress(Exception):
        await asyncio.get_running_loop().run_in_executor(None, driver.close)

    return {
        "files_processed": files_processed,
        "nodes_written": total_nodes,
        "edges_written": total_edges,
        "errors": errors,
        "request_id": request_id,
    }
