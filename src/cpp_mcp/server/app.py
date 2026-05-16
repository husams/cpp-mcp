"""MCP Server application: tool registration and dispatch.

Creates a ``mcp.server.Server`` instance, registers the 6 navigation/structural
tools from Stories 5 & 6, and exposes ``build_app()`` for use by transport
entry points (stdio, HTTP).

Tool registration uses the low-level Server API:
  - ``@server.list_tools()``   — returns the Tool catalogue.
  - ``@server.call_tool()``    — dispatches to the correct handler by name.

Every tool handler is an async callable wrapped by ``error_envelope.wrap_tool``
so that all domain exceptions are caught and returned as structured error
envelopes rather than raw MCP error responses.

A single ``ClangSession`` is created once per ``build_app()`` call and shared
across all tools (single libclang worker thread, shared TU cache — ADR-2).
"""

from __future__ import annotations

import uuid
from typing import Any

import mcp.types as types
from mcp.server import Server

from cpp_mcp.core.clang_session import ClangSession
from cpp_mcp.core.error_envelope import wrap_tool
from cpp_mcp.server.config import ServerConfig
from cpp_mcp.server.schemas import (
    CPP_EXPORT_TO_GRAPHDB_SCHEMA,
    CPP_GET_AST_SCHEMA,
    CPP_GET_DEFINITION_SCHEMA,
    CPP_GET_HEADER_INFO_SCHEMA,
    CPP_GET_PREPROCESSOR_STATE_SCHEMA,
    CPP_GET_REFERENCES_SCHEMA,
    CPP_GET_TYPE_INFO_SCHEMA,
)

# Tool metadata catalogue (name, description, schema).
_TOOL_SPECS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "cpp_get_definition",
        "Navigate to the canonical definition of a C++ symbol at a given source position.",
        CPP_GET_DEFINITION_SCHEMA,
    ),
    (
        "cpp_get_references",
        "Find all usages of a C++ symbol within the current translation unit.",
        CPP_GET_REFERENCES_SCHEMA,
    ),
    (
        "cpp_get_type_info",
        "Retrieve type details (size, alignment, qualifiers, canonical form) for a C++ symbol.",
        CPP_GET_TYPE_INFO_SCHEMA,
    ),
    (
        "cpp_get_ast",
        "Return an annotated AST subtree in JSON or graph format for a C++ source file.",
        CPP_GET_AST_SCHEMA,
    ),
    (
        "cpp_get_header_info",
        "Inspect the include graph and exported symbols for a C++ header or source file.",
        CPP_GET_HEADER_INFO_SCHEMA,
    ),
    (
        "cpp_get_preprocessor_state",
        "Retrieve active macro definitions and evaluated preprocessor conditional branch state.",
        CPP_GET_PREPROCESSOR_STATE_SCHEMA,
    ),
    (
        "cpp_export_to_graphdb",
        "Export C++ symbols and relationships from a file or directory to a graph database.",
        CPP_EXPORT_TO_GRAPHDB_SCHEMA,
    ),
]


def build_app(config: ServerConfig) -> tuple[Server, ClangSession]:
    """Construct and return a fully-configured MCP ``Server`` and its ``ClangSession``.

    Args:
        config: Parsed :class:`ServerConfig` (from ``server.config.load_config``).

    Returns:
        ``(server, session)`` — the server is ready to run; the session must be
        kept alive for the lifetime of the server.
    """
    server = Server("cpp-mcp")
    session = ClangSession(capacity=config.cache_capacity)

    allowed_roots = config.allowed_roots
    default_flags = config.default_flags
    ast_max_nodes = config.ast_max_nodes
    ast_max_bytes = config.ast_max_bytes

    # ------------------------------------------------------------------
    # Import tool implementations
    # ------------------------------------------------------------------
    from cpp_mcp.tools.export_to_graphdb import cpp_export_to_graphdb
    from cpp_mcp.tools.get_ast import cpp_get_ast
    from cpp_mcp.tools.get_definition import get_definition
    from cpp_mcp.tools.get_header_info import cpp_get_header_info
    from cpp_mcp.tools.get_preprocessor_state import cpp_get_preprocessor_state
    from cpp_mcp.tools.get_references import get_references
    from cpp_mcp.tools.get_type_info import get_type_info

    # ------------------------------------------------------------------
    # Build async handlers wrapped with error envelopes
    # ------------------------------------------------------------------

    @wrap_tool("cpp_get_definition")
    async def _handle_get_definition(
        file_path: str,
        line: int,
        col: int,
        build_path: str | None = None,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        return await get_definition(
            file_path=file_path,
            line=line,
            col=col,
            build_path=build_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            request_id=request_id,
        )

    @wrap_tool("cpp_get_references")
    async def _handle_get_references(
        file_path: str,
        line: int,
        col: int,
        build_path: str | None = None,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        return await get_references(
            file_path=file_path,
            line=line,
            col=col,
            build_path=build_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            request_id=request_id,
        )

    @wrap_tool("cpp_get_type_info")
    async def _handle_get_type_info(
        file_path: str,
        line: int,
        col: int,
        build_path: str | None = None,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        return await get_type_info(
            file_path=file_path,
            line=line,
            col=col,
            build_path=build_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            request_id=request_id,
        )

    @wrap_tool("cpp_get_ast")
    async def _handle_get_ast(
        file_path: str,
        build_path: str | None = None,
        format: str = "json",
        depth: int = 3,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        return await cpp_get_ast(
            file_path=file_path,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            build_path=build_path,
            format=format,
            depth=depth,
            start_line=start_line,
            end_line=end_line,
            max_nodes=ast_max_nodes,
            max_bytes=ast_max_bytes,
        )

    @wrap_tool("cpp_get_header_info")
    async def _handle_get_header_info(
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

    @wrap_tool("cpp_get_preprocessor_state")
    async def _handle_get_preprocessor_state(
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

    @wrap_tool("cpp_export_to_graphdb")
    async def _handle_export_to_graphdb(
        file_path_or_dir: str,
        build_path: str,
        db_uri: str,
        recursive: bool = False,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        return await cpp_export_to_graphdb(
            file_path_or_dir=file_path_or_dir,
            build_path=build_path,
            db_uri=db_uri,
            allowed_roots=allowed_roots,
            default_flags=default_flags,
            session=session,
            request_id=request_id,
            recursive=recursive,
        )

    _HANDLERS: dict[str, Any] = {
        "cpp_get_definition": _handle_get_definition,
        "cpp_get_references": _handle_get_references,
        "cpp_get_type_info": _handle_get_type_info,
        "cpp_get_ast": _handle_get_ast,
        "cpp_get_header_info": _handle_get_header_info,
        "cpp_get_preprocessor_state": _handle_get_preprocessor_state,
        "cpp_export_to_graphdb": _handle_export_to_graphdb,
    }

    # ------------------------------------------------------------------
    # list_tools handler
    # ------------------------------------------------------------------

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=desc,
                inputSchema=schema,
            )
            for name, desc, schema in _TOOL_SPECS
        ]

    # ------------------------------------------------------------------
    # call_tool handler
    # ------------------------------------------------------------------

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        handler = _HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name!r}")
        return await handler(**arguments)

    return server, session
