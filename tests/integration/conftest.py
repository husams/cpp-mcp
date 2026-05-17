"""Integration-specific fixtures.

Provides daemon lifecycle fixtures for IndraDB live end-to-end tests (S6).
The session-scoped ``mcp_client`` fixture is defined in tests/conftest.py and is
available here automatically.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uri(uri: str) -> tuple[str, int]:
    """Return (host, port) from an IndraDB URI such as grpc://127.0.0.1:27615."""
    from urllib.parse import urlparse

    parsed = urlparse(uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 27615
    return host, port


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to host:port succeeds within *timeout* seconds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    """Block until host:port is accepting connections or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port, timeout=0.5):
            return
        time.sleep(0.2)
    raise TimeoutError(f"IndraDB daemon did not open {host}:{port} within {timeout}s")


def _wipe(client: object) -> None:
    """Delete all vertices (and their incident edges) from the IndraDB daemon."""
    import indradb

    client.delete(indradb.AllVertexQuery())  # type: ignore[attr-defined]
    client.delete(indradb.AllEdgeQuery())  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def indradb_uri() -> str:
    """Return the IndraDB URI from the environment, or skip.

    SC-V4-2-01: when INDRADB_TEST_URI is unset, every test that depends on
    this fixture is skipped with a clear message.
    """
    uri = os.getenv("INDRADB_TEST_URI")
    if not uri:
        pytest.skip("INDRADB_TEST_URI is required for @indradb tests")
    return uri  # type: ignore[return-value]  # pytest.skip raises


@pytest.fixture(scope="session")
def indradb_daemon(indradb_uri: str):  # type: ignore[return]
    """Ensure an IndraDB memory daemon is reachable, autostaring if requested.

    SC-V4-2-02: when INDRADB_AUTOSTART != '1' and the daemon is not reachable,
    skips rather than failing.

    Environment variables:
        INDRADB_AUTOSTART: set to '1' to spawn ``indradb-server memory``
            automatically.  Any other value (or unset) means the fixture
            probes the port and skips if unreachable.
        INDRADB_TEST_URI: gRPC URI such as ``grpc://127.0.0.1:27615``.

    Yields the URI string so dependent fixtures can pass it on.
    """
    host, port = _parse_uri(indradb_uri)
    autostart = os.getenv("INDRADB_AUTOSTART") == "1"
    proc: subprocess.Popen[bytes] | None = None

    if autostart:
        proc = subprocess.Popen(
            ["indradb-server", "memory"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_port(host, port, timeout=10.0)
        except TimeoutError:
            proc.terminate()
            proc.wait(timeout=5)
            pytest.fail(
                f"indradb-server started but {host}:{port} did not become reachable "
                "within 10 seconds.  Check that indradb-server is functional."
            )
    else:
        if not _port_open(host, port, timeout=2.0):
            pytest.skip(
                f"No IndraDB daemon on {host}:{port} and INDRADB_AUTOSTART != '1'.  "
                "Start the daemon manually (indradb-server memory) or set "
                "INDRADB_AUTOSTART=1."
            )

    try:
        yield indradb_uri
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=5)


@pytest.fixture
def fresh_indradb(indradb_daemon: str):  # type: ignore[return]
    """Per-test fixture that provides a URI to a freshly wiped IndraDB daemon.

    Deletes all vertices and edges before each test so that exact count
    assertions (SC-V4-2-03) and idempotency checks (SC-V4-2-04) start from a
    known-empty state.

    Yields the URI string (same as indradb_daemon).
    """
    import indradb

    host, port = _parse_uri(indradb_daemon)
    client = indradb.Client(host=f"{host}:{port}")
    _wipe(client)
    yield indradb_daemon
