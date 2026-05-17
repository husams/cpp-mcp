"""Live IndraDB regression tests for three broken query_graphdb verbs (v6 post-ship).

Bug report:
  pipe — PipeQuery(direction) is wrong; real API needs PipeQuery(inner, direction).
  vertex_with_property_equal — VertexWithPropertyValueQuery arg '_name' causes NameError on assign.
  edge_with_property_equal — value must be a protobuf Json object, not a plain Python str.

Tests are marked xfail(strict=True) so they PASS today by failing as expected
and will FAIL LOUDLY (xpass) once the production bug is fixed — signalling readiness.

Environment:
    INDRADB_TEST_URI    gRPC URI, e.g. grpc://127.0.0.1:27615 (required; else skip)
    INDRADB_AUTOSTART   set to '1' to spawn indradb-server memory automatically

Usage:
    INDRADB_AUTOSTART=1 uv run pytest tests/integration/test_query_graphdb_live_indradb.py -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FMT_CC = "test-repo/fmt/src/fmt-c.cc"
_BUILD_PATH = "test-repo/fmt/build"

# The daemon URI used by the ingest driver uses the indradb:// scheme.
_INDRADB_DAEMON_URI = "indradb://127.0.0.1:27615"

# ---------------------------------------------------------------------------
# Local fixture helpers (not wiping the graph — shared-state tolerance)
# ---------------------------------------------------------------------------


def _parse_uri(uri: str) -> tuple[str, int]:
    from urllib.parse import urlparse

    parsed = urlparse(uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 27615
    return host, port


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port, timeout=0.5):
            return
        time.sleep(0.2)
    raise TimeoutError(f"IndraDB daemon did not open {host}:{port} within {timeout}s")


# ---------------------------------------------------------------------------
# Session-scoped daemon fixture (no wipe — tolerates shared graph state)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_indradb_uri() -> str:
    """Return the IndraDB URI, auto-starting the daemon when INDRADB_AUTOSTART=1.

    Unlike the ``fresh_indradb`` fixture in conftest, this fixture does NOT
    wipe the database.  Tests using it must tolerate pre-existing graph state.

    Skips if no URI is configured and autostart is off.
    """
    uri = os.getenv("INDRADB_TEST_URI", _INDRADB_DAEMON_URI)
    host, port = _parse_uri(uri)
    autostart = os.getenv("INDRADB_AUTOSTART") == "1"

    if autostart and not _port_open(host, port, timeout=1.0):
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
                "within 10 seconds."
            )
        # The daemon was started by us; store the proc reference in the
        # mutable container so finalizer cleanup can reach it if needed.
        _autostart_state["proc"] = proc
    elif not _port_open(host, port, timeout=2.0):
        pytest.skip(
            f"No IndraDB daemon on {host}:{port} and INDRADB_AUTOSTART != '1'. "
            "Start the daemon manually or set INDRADB_AUTOSTART=1."
        )

    return uri


_autostart_state: dict[str, Any] = {}  # holds optional proc started by autostart


# ---------------------------------------------------------------------------
# Ingest helper — idempotent (re-ingesting the same file just upserts)
# ---------------------------------------------------------------------------


async def _ingest_fmt_cc(mcp_client: Any, db_uri: str) -> None:
    """Ingest fmt-c.cc via the production ingest_code MCP tool."""
    result = await mcp_client.call_tool(
        "ingest_code",
        {
            "file_path_or_dir": _FMT_CC,
            "build_path": _BUILD_PATH,
            "db_uri": db_uri,
        },
    )
    assert result.data is not None, f"ingest_code returned no data: {result!r}"
    data: dict[str, Any] = result.data  # type: ignore[assignment]
    assert "code" not in data, (
        f"ingest_code returned error: code={data.get('code')!r}  message={data.get('message')!r}"
    )


# ---------------------------------------------------------------------------
# Query helper — calls query_graphdb MCP tool
# ---------------------------------------------------------------------------


async def _query(
    mcp_client: Any,
    db_uri: str,
    verb: str,
    args: dict[str, Any] | None = None,
    row_limit: int = 500,
) -> dict[str, Any]:
    """Call query_graphdb and return the raw payload dict (may contain 'code' on error)."""
    query_str = json.dumps({"query": verb, "args": args or {}})
    result = await mcp_client.call_tool(
        "query_graphdb",
        {
            "db_uri": db_uri,
            "query": query_str,
            "row_limit": row_limit,
        },
    )
    assert result.data is not None, f"query_graphdb returned no data: {result!r}"
    return result.data  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Positive control — vertex_with_type (known-working verb)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_vertex_with_type_against_live_indradb(
    mcp_client: Any,
    live_indradb_uri: str,
) -> None:
    """Positive control: vertex_with_type returns Function rows after ingesting fmt-c.cc.

    This test proves the live_indradb_uri fixture and ingest pipeline are sound.
    At least one Function vertex must exist; the exact count tolerates shared
    graph state from prior ingests.
    """
    await _ingest_fmt_cc(mcp_client, live_indradb_uri)

    data = await _query(
        mcp_client,
        live_indradb_uri,
        "vertex_with_type",
        args={"t": "Function"},
    )

    # Must be a success-shape response — no 'code' key.
    assert "code" not in data, (
        f"vertex_with_type returned error envelope: code={data.get('code')!r}  "
        f"message={data.get('message')!r}"
    )

    rows: list[dict[str, Any]] = data["rows"]
    stats: dict[str, Any] = data["stats"]

    assert len(rows) >= 1, "Expected at least one Function vertex after ingesting fmt-c.cc"
    assert stats["backend"] == "indradb"
    assert "request_id" in data
    assert len(data["request_id"]) == 32  # UUID4 hex

    for row in rows:
        assert row.get("t") == "Function", f"Unexpected vertex type in row: {row}"
        assert "id" in row
        assert "properties" in row


# ---------------------------------------------------------------------------
# Bug #1 — pipe verb
#
# Root cause: executor calls indradb.PipeQuery(direction) but the real API
# requires PipeQuery(inner, direction) where inner is the wrapped query.
# TypeError: PipeQuery.__init__() missing 1 required positional argument: 'direction'
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_pipe_against_live_indradb(
    mcp_client: Any,
    live_indradb_uri: str,
) -> None:
    """xfail-strict: pipe verb returns INTERNAL_ERROR due to wrong PipeQuery construction.

    Precondition: fmt-c.cc is ingested so at least one Function vertex exists.
    We pick any vertex and pipe outbound from it.  A working implementation
    should return a success-shape response even if 0 neighbours exist.
    """
    await _ingest_fmt_cc(mcp_client, live_indradb_uri)

    # Grab a vertex ID from the working verb to use as pipe source.
    vt_data = await _query(
        mcp_client,
        live_indradb_uri,
        "vertex_with_type",
        args={"t": "Function"},
        row_limit=1,
    )
    assert "code" not in vt_data, f"Precondition failed: {vt_data}"
    rows: list[dict[str, Any]] = vt_data["rows"]
    assert rows, "Precondition: at least one Function vertex expected"

    vertex_id = rows[0]["id"]

    # This call exercises the broken PipeQuery construction path.
    data = await _query(
        mcp_client,
        live_indradb_uri,
        "pipe",
        args={"vertex_id": vertex_id, "direction": "outbound"},
    )

    # Expected success shape — will xfail because the bug fires first.
    assert "code" not in data, (
        f"pipe returned error: code={data.get('code')!r}  message={data.get('message')!r}"
    )
    assert "rows" in data
    assert "stats" in data
    assert data["stats"]["backend"] == "indradb"


# ---------------------------------------------------------------------------
# Bug #2 — vertex_with_property_equal verb
#
# Root cause: indradb.VertexWithPropertyValueQuery.__init__ has arg named
# '_name' but the body assigns 'self._name = name' — NameError at call time.
# The executor at line ~370 passes positional args which trigger this bug.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_vertex_with_property_equal_against_live_indradb(
    mcp_client: Any,
    live_indradb_uri: str,
) -> None:
    """xfail-strict: vertex_with_property_equal returns INTERNAL_ERROR due to NameError.

    Uses name='spelling' and value='fmt_c' — a value expected after ingesting
    fmt-c.cc (the file vertex's spelling property).  The bug fires before any
    graph traversal so the exact value does not matter.
    """
    await _ingest_fmt_cc(mcp_client, live_indradb_uri)

    data = await _query(
        mcp_client,
        live_indradb_uri,
        "vertex_with_property_equal",
        args={"name": "spelling", "value": "fmt_c"},
    )

    # Expected success shape — will xfail because the bug fires first.
    assert "code" not in data, (
        f"vertex_with_property_equal returned error: code={data.get('code')!r}  "
        f"message={data.get('message')!r}"
    )
    assert "rows" in data
    assert "stats" in data
    assert data["stats"]["backend"] == "indradb"


# ---------------------------------------------------------------------------
# Bug #3 — edge_with_property_equal verb
#
# Root cause: indradb.EdgeWithPropertyValueQuery.to_message() expects value
# to be an indradb protobuf Json object, not a plain Python str.
# TypeError: Parameter to MergeFrom() must be instance of same class:
#   expected indradb_pb2.Json got str.  for field EdgeWithPropertyValueQuery.value
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_edge_with_property_equal_against_live_indradb(
    mcp_client: Any,
    live_indradb_uri: str,
) -> None:
    """xfail-strict: edge_with_property_equal returns INTERNAL_ERROR due to Json type mismatch.

    DEFINES/REFERENCES edges carry no edge-level properties, so any name/value
    pair will match zero rows — but the bug fires during query construction,
    before any graph traversal, so the value is irrelevant.
    """
    await _ingest_fmt_cc(mcp_client, live_indradb_uri)

    data = await _query(
        mcp_client,
        live_indradb_uri,
        "edge_with_property_equal",
        args={"name": "weight", "value": "heavy"},
    )

    # Expected success shape (0 rows, but no error) — will xfail due to the bug.
    assert "code" not in data, (
        f"edge_with_property_equal returned error: code={data.get('code')!r}  "
        f"message={data.get('message')!r}"
    )
    assert "rows" in data
    assert "stats" in data
    assert data["stats"]["backend"] == "indradb"
