"""FastMCP singleton registry.

ADR-3 (v2): Tool modules import ``mcp`` from this module so that @mcp.tool
decorator side-effects register each tool against the single FastMCP instance
created by ``build_server()`` in ``server/app.py``.

Usage in tool modules::

    from cpp_mcp.server._registry import mcp

``build_server()`` in app.py sets ``_registry.mcp`` before importing tool
modules, ensuring all @mcp.tool decorators register against the same instance.
"""

from __future__ import annotations

from fastmcp import FastMCP

# Module-level singleton.  ``build_server()`` in app.py sets this attribute
# before importing the tool modules (which causes @mcp.tool decorators to fire).
# Tests call ``build_server()`` to get a fresh instance; they do NOT import
# this module's ``mcp`` directly.
mcp: FastMCP | None = None
