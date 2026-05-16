"""Entry point for ``python -m cpp_mcp``.

Delegates to cpp_mcp.server.app:main() (FastMCP stdio transport, S2+).
"""

from __future__ import annotations

from cpp_mcp.server.app import main

if __name__ == "__main__":
    raise SystemExit(main())
