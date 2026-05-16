"""BDD step implementations for transport_http feature (Story 7b / US-14).

Spins up the HTTP transport in-process on a free port using uvicorn's
programmatic API, waits for /healthz to respond, then exercises MCP
initialization and tools/list over the streamable HTTP client.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

scenarios("features/transport_http.feature")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Bind to port 0 and return the assigned ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_healthz(port: int, timeout: float = 10.0) -> None:
    """Poll GET /healthz until it returns 200 or *timeout* expires."""
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    raise TimeoutError(f"HTTP server on port {port} did not start within {timeout}s")


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("the server is started in http mode on a free port")
def start_http_server(tmp_path: Path, ctx: dict[str, Any]) -> None:
    """Start the HTTP transport in a background thread and wait for readiness."""
    root = tmp_path / "projects"
    root.mkdir()
    port = _free_port()
    ctx["port"] = port
    ctx["allowed_root"] = str(root)

    env = {**os.environ, "CPP_MCP_ALLOWED_ROOTS": str(root)}

    def _run() -> None:
        # Patch os.environ so load_config() picks up the allowed root.
        old_env = dict(os.environ)
        os.environ.update(env)
        try:
            from cpp_mcp.server.http_transport import run_http

            asyncio.run(run_http(host="127.0.0.1", port=port))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    thread = threading.Thread(target=_run, daemon=True, name="http-server")
    thread.start()
    ctx["server_thread"] = thread

    # Wait until the server is actually accepting connections.
    _wait_for_healthz(port)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("an MCP client initializes over the HTTP transport")
def client_http_initialize(ctx: dict[str, Any]) -> None:
    """Connect with the MCP streamable-HTTP client and run initialize + list_tools."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    port = ctx["port"]
    url = f"http://127.0.0.1:{port}/mcp"

    async def _run() -> None:
        async with (
            streamable_http_client(url) as (read, write, _),
            ClientSession(read, write) as client,
        ):
            init_result = await client.initialize()
            ctx["init_result"] = init_result
            tools_result = await client.list_tools()
            ctx["tools"] = [t.name for t in tools_result.tools]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("the initialize response is valid")
def assert_http_init_ok(ctx: dict[str, Any]) -> None:
    assert "init_result" in ctx, "HTTP initialize was not called or failed"
    assert ctx["init_result"] is not None


@then("the HTTP server exposes all 7 tools")
def assert_http_all_tools(ctx: dict[str, Any]) -> None:
    expected = {
        "cpp_get_definition",
        "cpp_get_references",
        "cpp_get_type_info",
        "cpp_get_ast",
        "cpp_get_header_info",
        "cpp_get_preprocessor_state",
        "cpp_export_to_graphdb",
    }
    actual = set(ctx.get("tools", []))
    missing = expected - actual
    assert not missing, f"HTTP transport missing tools: {missing}. Got: {actual}"
