"""BDD step implementations for transport_http feature (Story S6 / US-M2).

Starts the HTTP transport as a child subprocess using mcp.run(transport="http", ...),
waits for /health to respond, then exercises MCP initialization and tools/list
over the streamable HTTP transport.  Using a subprocess rather than a thread
avoids os.environ contamination of other tests.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


def _wait_for_health(port: int, timeout: float = 15.0) -> None:
    """Poll GET /health until it returns 200 or *timeout* expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    raise TimeoutError(f"HTTP server on port {port} did not start within {timeout}s")


def _start_http_server_subprocess(root: str, port: int) -> subprocess.Popen[bytes]:
    """Start FastMCP HTTP server as a child subprocess."""
    env = {
        **os.environ,
        "CPP_MCP_ALLOWED_ROOTS": root,
        "CPP_MCP_TRANSPORT": "http",
        "CPP_MCP_HTTP_BIND": "127.0.0.1",
        "CPP_MCP_HTTP_PORT": str(port),
    }
    return subprocess.Popen(
        [sys.executable, "-m", "cpp_mcp"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("the server is started in http mode on a free port")
def start_http_server(tmp_path: Path, ctx: dict[str, Any]) -> None:
    """Start the HTTP transport as a subprocess and wait for readiness."""
    root = tmp_path / "projects"
    root.mkdir()
    port = _free_port()
    ctx["port"] = port
    ctx["allowed_root"] = str(root)

    proc = _start_http_server_subprocess(str(root), port)
    ctx["server_proc"] = proc

    # Wait until the server is actually accepting connections.
    try:
        _wait_for_health(port)
    except TimeoutError:
        proc.terminate()
        raise


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("an MCP client initializes over the HTTP transport")
def client_http_initialize(ctx: dict[str, Any]) -> None:
    """Connect with the MCP streamable-HTTP client and run initialize + list_tools."""
    import asyncio

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
    # Terminate the server after use
    proc: subprocess.Popen[bytes] = ctx.get("server_proc")  # type: ignore[assignment]
    if proc is not None:
        proc.terminate()


@when('an HTTP GET request is sent to "/health"')
def client_http_health(ctx: dict[str, Any]) -> None:
    """Send a GET /health request and store the response."""
    port = ctx["port"]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
        ctx["health_status"] = resp.status
        ctx["health_body"] = resp.read().decode()
    # Terminate the server after use
    proc: subprocess.Popen[bytes] = ctx.get("server_proc")  # type: ignore[assignment]
    if proc is not None:
        proc.terminate()


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
        "get_definition",
        "get_references",
        "get_type_info",
        "get_ast",
        "get_header_info",
        "get_preprocessor_state",
        "ingest_code",
    }
    actual = set(ctx.get("tools", []))
    missing = expected - actual
    assert not missing, f"HTTP transport missing tools: {missing}. Got: {actual}"


@then("the health response status is 200")
def assert_health_status_200(ctx: dict[str, Any]) -> None:
    assert ctx.get("health_status") == 200, (
        f"Expected health status 200, got {ctx.get('health_status')}"
    )


@then('the health response body is "OK"')
def assert_health_body_ok(ctx: dict[str, Any]) -> None:
    assert ctx.get("health_body") == "OK", (
        f"Expected health body 'OK', got {ctx.get('health_body')!r}"
    )
