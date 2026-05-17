"""Real IndraDB end-to-end tests for query_graphdb.

Covers:
  AC-Q3-1 — all_vertices query returns 99 vertices after ingest_code on os.cc
  AC-Q3-2 — all_edges query returns 180 edges; vertex_with_type returns 21 Function rows
  AC-Q3-4 — row_limit=50 on all_vertices yields stats.truncated==True, len(rows)==50

Environment:
    INDRADB_TEST_URI    gRPC URI, e.g. grpc://127.0.0.1:27615 (required; else skip)
    INDRADB_AUTOSTART   set to '1' to spawn indradb-server memory automatically
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixture paths (same as test_indradb_e2e.py)
# ---------------------------------------------------------------------------

_OS_CC = "test-repo/fmt/src/os.cc"
_BUILD_PATH = "test-repo/fmt/build"

# ---------------------------------------------------------------------------
# Pinned counts (2026-05-17 live run against test-repo/fmt/src/os.cc)
# ---------------------------------------------------------------------------

_EXPECTED_VERTICES: int = 99
_EXPECTED_EDGES: int = 180
_EXPECTED_FUNCTION_VERTICES: int = 21

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ingest(mcp_client: Any, db_uri: str) -> None:
    """Run ingest_code and assert no error envelope is returned."""
    result = await mcp_client.call_tool(
        "ingest_code",
        {
            "file_path_or_dir": _OS_CC,
            "build_path": _BUILD_PATH,
            "db_uri": db_uri,
        },
    )
    assert result.data is not None, f"ingest_code returned no data: {result!r}"
    data: dict[str, Any] = result.data  # type: ignore[assignment]
    assert "code" not in data, (
        f"ingest_code returned error: code={data.get('code')!r}  message={data.get('message')!r}"
    )


async def _query(
    mcp_client: Any,
    db_uri: str,
    verb: str,
    args: dict[str, Any] | None = None,
    row_limit: int = 500,
) -> dict[str, Any]:
    """Call query_graphdb and return the success payload dict."""
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
    data: dict[str, Any] = result.data  # type: ignore[assignment]
    assert "code" not in data, (
        f"query_graphdb returned error: code={data.get('code')!r}  message={data.get('message')!r}"
    )
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_1_all_vertices_pinned_count(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-1: all_vertices returns exactly 99 vertices after ingest of os.cc."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(mcp_client, fresh_indradb, "all_vertices")

    rows: list[dict[str, Any]] = data["rows"]
    stats: dict[str, Any] = data["stats"]

    assert stats["rows_returned"] == _EXPECTED_VERTICES, (
        f"stats.rows_returned={stats['rows_returned']} but pinned={_EXPECTED_VERTICES}"
    )
    assert len(rows) == _EXPECTED_VERTICES, f"len(rows)={len(rows)} but pinned={_EXPECTED_VERTICES}"
    assert stats["truncated"] is False, "Expected truncated==False with row_limit=500"
    assert stats["backend"] == "indradb"
    assert "request_id" in data
    assert len(data["request_id"]) == 32  # UUID4 hex


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_2_all_edges_pinned_count(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-2: all_edges returns exactly 180 edges after ingest of os.cc."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(mcp_client, fresh_indradb, "all_edges")

    stats: dict[str, Any] = data["stats"]

    assert stats["rows_returned"] == _EXPECTED_EDGES, (
        f"stats.rows_returned={stats['rows_returned']} but pinned={_EXPECTED_EDGES}"
    )
    assert stats["truncated"] is False
    assert stats["backend"] == "indradb"


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_2_vertex_with_type_function(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-2: vertex_with_type{'t':'Function'} returns exactly 21 rows."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(
        mcp_client,
        fresh_indradb,
        "vertex_with_type",
        args={"t": "Function"},
    )

    rows: list[dict[str, Any]] = data["rows"]
    stats: dict[str, Any] = data["stats"]

    assert len(rows) == _EXPECTED_FUNCTION_VERTICES, (
        f"Expected {_EXPECTED_FUNCTION_VERTICES} Function vertices, got {len(rows)}"
    )
    assert stats["rows_returned"] == _EXPECTED_FUNCTION_VERTICES
    assert stats["truncated"] is False

    # Each row must carry the coerced shape: id, t, properties
    for row in rows:
        assert row.get("t") == "Function", f"Unexpected vertex type in row: {row}"
        assert "id" in row
        assert "properties" in row


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_4_row_limit_truncation(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-4: row_limit=50 on all_vertices yields truncated==True and len(rows)==50."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(mcp_client, fresh_indradb, "all_vertices", row_limit=50)

    rows: list[dict[str, Any]] = data["rows"]
    stats: dict[str, Any] = data["stats"]

    assert len(rows) == 50, f"Expected 50 rows (row_limit), got {len(rows)}"
    assert stats["rows_returned"] == 50
    assert stats["truncated"] is True, "Expected truncated==True because 99 vertices > row_limit=50"
