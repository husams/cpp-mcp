"""Stdio transport entry point for the C++ MCP server.

This module is the ``main`` callable for both:
  - ``python -m cpp_mcp``   (via ``src/cpp_mcp/__main__.py``)
  - ``cpp-mcp``             (via ``[project.scripts]`` in pyproject.toml)

It loads configuration from environment variables, builds the MCP server,
and runs it over stdin/stdout using the official MCP SDK stdio transport.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from mcp.server.stdio import stdio_server

from cpp_mcp.core.error_envelope import ConfigError
from cpp_mcp.server.app import build_app
from cpp_mcp.server.config import load_config

logger = logging.getLogger(__name__)


async def _run_stdio() -> None:
    """Load config, build server, and run the stdio transport loop."""
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    server, _session = build_app(config)

    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


def main() -> None:
    """Synchronous entry point for ``cpp-mcp`` console script."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
