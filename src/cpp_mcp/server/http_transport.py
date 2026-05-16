"""HTTP transport entry point for the C++ MCP server (ADR-10, US-14/AC-2).

Exposes the same MCP tool surface as the stdio transport over HTTP using:
  - POST /mcp  — MCP JSON-RPC over StreamableHTTP (stateless mode).
  - GET  /healthz — server health and TU-cache statistics.

Bind address defaults to 127.0.0.1 (loopback-only, no auth in v1).
If CPP_MCP_HTTP_BIND is set to a non-loopback address the server logs a
warning and prints to stderr per ADR-10.

Usage (from __main__.py):
    asyncio.run(run_http(host="127.0.0.1", port=8000))
"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from cpp_mcp.core.clang_session import ClangSession
from cpp_mcp.core.error_envelope import ConfigError
from cpp_mcp.server.app import build_app
from cpp_mcp.server.config import load_config

logger = logging.getLogger(__name__)

_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1", "localhost"}
_VERSION = "0.1.0"


def _warn_non_loopback(host: str) -> None:
    """Emit a warning when binding to a non-loopback address (ADR-10)."""
    msg = (
        f"HTTP bound to non-loopback address {host!r} without auth; "
        "do not expose to untrusted networks"
    )
    logger.warning(msg)
    print(msg, file=sys.stderr)


def _build_starlette_app(server: Any, session: ClangSession) -> Starlette:
    """Construct a Starlette ASGI application wrapping the MCP server.

    Uses StreamableHTTPSessionManager in stateless mode so every request gets a
    fresh transport instance — consistent with the stateless-build-context design
    (ADR-2) and avoids session-tracking machinery that is unnecessary for a
    single-client loopback deployment.
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
    )

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        await manager.handle_request(scope, receive, send)

    async def healthz(request: Request) -> JSONResponse:
        stats = session.cache_stats()
        return JSONResponse(
            {
                "status": "ok",
                "cache_size": stats.get("cache_size", 0),
                "cache_capacity": stats.get("cache_capacity", 0),
                "cache_hit_rate": stats.get("cache_hit_rate", 0.0),
                "version": _VERSION,
            }
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    return Starlette(
        routes=[
            Mount("/mcp", app=handle_mcp),
            Route("/healthz", healthz, methods=["GET"]),
        ],
        lifespan=lifespan,
    )


async def run_http(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Load config, build server, and serve over HTTP.

    Args:
        host: Bind address. Defaults to ``127.0.0.1``.
        port: TCP port to listen on. Defaults to 8000.
    """
    if host not in _LOOPBACK_ADDRESSES:
        _warn_non_loopback(host)

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    server, session = build_app(config)
    app = _build_starlette_app(server, session)

    uv_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        lifespan="on",
    )
    await uvicorn.Server(uv_config).serve()
