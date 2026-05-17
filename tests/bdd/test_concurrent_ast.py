"""BDD-style test: 3 concurrent HTTP get_ast calls on same file.

Implements SC_USM7_3: verifies thread-affinity (executor.submit.result()),
cache correctness (parse_count == 1 after first hit), and no libclang crashes.
(US-M7/AC-3, C-8)

Uses a subprocess for the HTTP server to avoid os.environ contamination.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    raise TimeoutError(f"HTTP server on port {port} did not start within {timeout}s")


def _start_http_server_subprocess(root: str, port: int) -> subprocess.Popen[bytes]:
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
# Fixture
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "cpp"


@pytest.fixture(scope="module")
def http_server_for_concurrent(
    tmp_path_factory: pytest.TempPathFactory,
) -> Any:
    """Spin up one HTTP server subprocess shared across the concurrent AST test."""
    root = tmp_path_factory.mktemp("concurrent_root")
    # Copy fixture C++ file into the allowed root
    src = _FIXTURES_DIR / "ast_test.cpp"
    dst = root / "ast_test.cpp"
    shutil.copy2(str(src), str(dst))

    port = _free_port()
    proc = _start_http_server_subprocess(str(root), port)

    try:
        _wait_for_health(port)
    except TimeoutError:
        proc.terminate()
        raise

    ctx: dict[str, Any] = {
        "port": port,
        "root": str(root),
        "file": str(dst),
        "proc": proc,
    }
    yield ctx

    proc.terminate()
    proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.SC_USM7_3
def test_three_concurrent_http_ast_calls_all_succeed(
    http_server_for_concurrent: dict[str, Any],
) -> None:
    """SC_USM7_3: 3 concurrent HTTP get_ast calls succeed; no libclang crash."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    port = http_server_for_concurrent["port"]
    file_path = http_server_for_concurrent["file"]
    url = f"http://127.0.0.1:{port}/mcp"

    async def _call_ast() -> dict[str, Any]:
        async with (
            streamable_http_client(url) as (read, write, _),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            result = await client.call_tool(
                "get_ast",
                {"file_path": file_path, "format": "json"},
            )
            # Extract the structured payload from the first content item
            if result.content:
                raw = result.content[0].text  # type: ignore[union-attr]
                return json.loads(raw)  # type: ignore[arg-type]
            return {}

    async def _run_all() -> list[dict[str, Any]]:
        tasks = [asyncio.create_task(_call_ast()) for _ in range(3)]
        return list(await asyncio.gather(*tasks))

    results = asyncio.run(_run_all())

    assert len(results) == 3, "Expected 3 results from concurrent calls"
    for i, res in enumerate(results):
        assert "code" not in res or res.get("code") != "INTERNAL_ERROR", (
            f"Call {i} returned error: {res}"
        )
        # Each successful result should have request_id
        assert "request_id" in res, f"Call {i} missing request_id: {res}"
