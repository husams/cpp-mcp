"""ingest_code MCP tool implementation (v5 rename; previously export_to_graphdb).

S3: converted to sync def + @mcp.tool + Depends DI (ADR-3, ADR-7).

Validation order (per ADR-7, ADR-12, US-G3 / scenarios.md):
  1. INVALID_ARGUMENT — missing or empty db_uri / build_path.
  2. INVALID_ARGUMENT — unknown URI scheme (via select_driver, before path checks).
  3. PATH_VIOLATION   — path traversal in file_path_or_dir or build_path.
  4. FILE_NOT_FOUND   — path does not exist after validation.
  5. DEPENDENCY_MISSING / DB_UNREACHABLE — driver.connect() fails.
  6. Per-file work    — parse + export; partial failures recorded in errors[].
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from typing import Annotated, Any

from fastmcp.dependencies import Depends

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.deps import get_allowed_roots, get_default_flags, get_session
from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    InvalidArgumentError,
    wrap_tool,
)
from cpp_mcp.core.path_guard import validate_path
from cpp_mcp.graphdb import select_driver
from cpp_mcp.graphdb.exporter import collect_cpp_files, export_file

logger = logging.getLogger(__name__)

_TOOL_NAME = "ingest_code"


def _do_ingest_code(
    *,
    file_path_or_dir: str,
    build_path: str | None,
    db_uri: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
    recursive: bool = False,
) -> dict[str, Any]:
    """Blocking export work; MUST be executed on the single worker thread.

    Args:
        file_path_or_dir: Absolute path to a C++ file or directory.
        build_path: Absolute path to the build directory (required).
        db_uri: Bolt URI for the graph database (required).
        allowed_roots: Tuple of allowed root directories.
        default_flags: Default compiler flags tuple.
        session: Shared :class:`ClangSession`.
        request_id: UUID hex string for log correlation.
        recursive: If True, recurse into sub-directories.

    Returns:
        Success payload: ``{files_processed, nodes_written, edges_written,
        nodes_attempted, edges_attempted, errors}``.

        ``nodes_written`` / ``edges_written`` count only records that were
        **actually created** (inserts).  ``nodes_attempted`` / ``edges_attempted``
        reflect the total batch sizes sent to the driver (ADR-17).

    Raises:
        :exc:`InvalidArgumentError`: Missing / empty ``db_uri`` or ``build_path``,
            or unrecognised URI scheme.
        :exc:`PathViolationError`: Path traversal detected.
        :exc:`FileNotFoundError`: Path does not exist.
        :exc:`DependencyMissingError`: Required driver package not installed.
        :exc:`DBUnreachableError`: Cannot connect to the graph database.
    """
    # 1. INVALID_ARGUMENT — empty / missing inputs.
    if not db_uri:
        raise InvalidArgumentError(
            "db_uri is required and must be a non-empty string for ingest_code."
        )
    if not build_path:
        raise InvalidArgumentError(
            "build_path is required and must be a non-empty string for ingest_code."
        )

    # 2. INVALID_ARGUMENT — unknown URI scheme (must precede path checks per ADR-12).
    driver = select_driver(db_uri)

    # 3. PATH_VIOLATION
    validated_build = validate_path(build_path, allowed_roots, kind="dir")
    validated_input = validate_path(file_path_or_dir, allowed_roots, kind="file")

    # 5. DEPENDENCY_MISSING / DB_UNREACHABLE
    try:
        driver.connect(db_uri)
    except (DependencyMissingError, DBUnreachableError):
        raise
    except Exception as exc:
        raise DBUnreachableError(f"Cannot reach graph database at {db_uri!r}: {exc}") from exc

    # 5. Per-file export
    cpp_files = collect_cpp_files(validated_input, recursive=recursive)

    total_nodes = 0
    total_edges = 0
    total_nodes_attempted = 0
    total_edges_attempted = 0
    errors: list[dict[str, Any]] = []
    files_processed = 0

    for cpp_file in cpp_files:
        try:
            flags, _source = resolve_flags(
                file_path=cpp_file,
                build_path=validated_build,
                default_flags=default_flags,
            )
            tu, _hit = session._get_or_parse_sync(cpp_file, validated_build, flags)
            result = export_file(cpp_file, tu, driver)
            total_nodes += result["nodes_written"]
            total_edges += result["edges_written"]
            total_nodes_attempted += result["nodes_attempted"]
            total_edges_attempted += result["edges_attempted"]
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

    with contextlib.suppress(Exception):
        driver.close()

    return {
        "files_processed": files_processed,
        "nodes_written": total_nodes,
        "edges_written": total_edges,
        "nodes_attempted": total_nodes_attempted,
        "edges_attempted": total_edges_attempted,
        "errors": errors,
        "request_id": request_id,
    }


def ingest_code(
    *,
    file_path_or_dir: str,
    build_path: str | None,
    db_uri: str | None,
    allowed_roots: tuple[str, ...],
    default_flags: tuple[str, ...],
    session: Any,
    request_id: str,
    recursive: bool = False,
) -> dict[str, Any]:
    """Sync entry point used directly by unit tests.

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
        Success payload: ``{files_processed, nodes_written, edges_written,
        nodes_attempted, edges_attempted, errors}`` (ADR-17).
    """
    return _do_ingest_code(
        file_path_or_dir=file_path_or_dir,
        build_path=build_path,
        db_uri=db_uri,
        allowed_roots=allowed_roots,
        default_flags=default_flags,
        session=session,
        request_id=request_id,
        recursive=recursive,
    )


def _register(mcp: Any) -> None:
    """Register ingest_code against *mcp*. Called by build_server()."""

    @mcp.tool(  # type: ignore[untyped-decorator]
        name="ingest_code",
        description=(
            "Export C++ symbols and relationships from a file or directory to a graph database."
        ),
    )
    @wrap_tool(_TOOL_NAME)
    def ingest_code_tool(
        file_path_or_dir: Annotated[
            str,
            "Absolute path to a C++ source file or directory to export.",
        ],
        build_path: Annotated[
            str,
            "Absolute path to the build directory containing compile_commands.json."
            " Required for graph export.",
        ],
        db_uri: Annotated[
            str,
            "Bolt URI for the target graph database (e.g. 'bolt://localhost:7687').",
        ],
        recursive: Annotated[
            bool,
            "If true and file_path_or_dir is a directory, recurse into sub-directories.",
        ] = False,
        *,
        session: Any = Depends(get_session),
        allowed_roots: tuple[str, ...] = Depends(get_allowed_roots),
        default_flags: tuple[str, ...] = Depends(get_default_flags),
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        return session.executor.submit(  # type: ignore[no-any-return]
            _do_ingest_code,
            file_path_or_dir=file_path_or_dir,
            build_path=build_path,
            db_uri=db_uri,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            request_id=request_id,
            recursive=recursive,
        ).result()
