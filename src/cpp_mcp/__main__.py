"""Entry point for ``python -m cpp_mcp``.

Dispatches to stdio or HTTP transport based on ``--transport`` flag (ADR-10).

Usage:
    python -m cpp_mcp                         # stdio (default)
    python -m cpp_mcp --transport stdio
    python -m cpp_mcp --transport http
    python -m cpp_mcp --transport http --port 8765 --host 127.0.0.1
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cpp_mcp",
        description="C++ Semantic Analysis MCP Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use: 'stdio' (default) or 'http'.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="TCP port for HTTP transport (default: 8000).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address for HTTP transport (default: 127.0.0.1).",
    )
    return parser


def main() -> None:
    """Synchronous entry point: parse args and dispatch to the chosen transport."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = _build_parser()
    args = parser.parse_args()

    if args.transport == "http":
        from cpp_mcp.server.http_transport import run_http

        asyncio.run(run_http(host=args.host, port=args.port))
    else:
        from cpp_mcp.server.stdio_transport import _run_stdio

        asyncio.run(_run_stdio())


main()
