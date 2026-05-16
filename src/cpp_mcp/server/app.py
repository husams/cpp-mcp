"""MCP server application: FastMCP build_server() + main() entrypoint.

S3: All 7 tools registered via @mcp.tool in their respective tool modules.
The legacy shims are removed; tests now use build_server() directly.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from cpp_mcp.core.clang_session import ClangSession
from cpp_mcp.core.deps import AppLifespanContext
from cpp_mcp.core.error_envelope import ConfigError, _sanitize_message
from cpp_mcp.server.config import _warn_if_non_loopback, load_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppLifespanContext]:
    """FastMCP lifespan: construct ClangSession, yield context, tear down cleanly.

    ADR-7 (v2): ClangSession is owned by the lifespan so it is created once
    per process and shut down on exit (EC-4 — executor drains in-flight work).
    US-M6/AC-5 — ConfigError raised here propagates out of mcp.run() and is
    caught by main().
    """
    cfg = load_config()  # raises ConfigError -> caught by main()
    session = ClangSession(capacity=cfg.cache_capacity)
    try:
        yield AppLifespanContext(
            session=session,
            allowed_roots=cfg.allowed_roots,
            default_flags=cfg.default_flags,
            ast_max_nodes=cfg.ast_max_nodes,
            ast_max_bytes=cfg.ast_max_bytes,
        )
    finally:
        await session.aclose()


# ---------------------------------------------------------------------------
# build_server
# ---------------------------------------------------------------------------


def build_server() -> FastMCP:
    """Construct and return a FastMCP instance with all 7 tools registered.

    Importing the tool modules inside this function causes the @mcp.tool
    decorator side-effects to fire against the instance assigned to
    ``cpp_mcp.server._registry.mcp``.
    """
    import cpp_mcp.server._registry as _registry

    mcp: FastMCP = FastMCP(
        "cpp-mcp",
        instructions=None,
        lifespan=app_lifespan,
        mask_error_details=True,
    )
    _registry.mcp = mcp

    # Import tool modules to trigger @mcp.tool registration.
    # Each module's _register(mcp) function wires the tool against this instance.
    from cpp_mcp.tools import (
        export_to_graphdb,
        get_ast,
        get_definition,
        get_header_info,
        get_preprocessor_state,
        get_references,
        get_type_info,
    )

    get_definition._register(mcp)
    get_references._register(mcp)
    get_type_info._register(mcp)
    get_ast._register(mcp)
    get_header_info._register(mcp)
    get_preprocessor_state._register(mcp)
    export_to_graphdb._register(mcp)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> PlainTextResponse:
        """Liveness probe endpoint for HTTP transport (ADR-5, US-M2/AC-4)."""
        return PlainTextResponse("OK")

    return mcp


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    """Synchronous entry point for the ``cpp-mcp`` console script.

    Configures stderr logging first, then runs the FastMCP stdio transport.
    Returns 0 on clean exit, 1 on ConfigError.
    """
    logging.basicConfig(
        level=os.environ.get("CPP_MCP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        mcp = build_server()
        cfg = load_config()
        if cfg.transport == "http":
            _warn_if_non_loopback(cfg.http_bind)
            mcp.run(
                transport="http",
                host=cfg.http_bind,
                port=cfg.http_port,
                path="/mcp",
                show_banner=False,
            )
        else:
            mcp.run(show_banner=False)  # stdio default
        return 0
    except ConfigError as exc:
        print(_sanitize_message(str(exc), ()), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
