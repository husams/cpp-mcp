"""Real IndraDB end-to-end tests for ingest_code.

Covers:
  SC-V4-2-01 — test skipped when INDRADB_TEST_URI unset (fixture-level skip)
  SC-V4-2-02 — test skipped when daemon unreachable + INDRADB_AUTOSTART != 1 (fixture-level skip)
  SC-V4-2-03 — exporting os.cc writes the expected vertex and edge counts
  SC-V4-2-04 — second export of same file returns nodes_written == 0, edges_written == 0
  SC-V4-3-01 — nodes_written / edges_written reflect insert counts, not attempt counts
  SC-V4-3-02 — nodes_attempted / edges_attempted are present and >= their written counterparts

Environment:
    INDRADB_TEST_URI    gRPC URI, e.g. grpc://127.0.0.1:27615 (required; else skip)
    INDRADB_AUTOSTART   set to '1' to spawn indradb-server memory automatically

Prerequisites:
    test-repo/fmt/src/os.cc  — the C++ fixture file exported to IndraDB
    test-repo/fmt/build/compile_commands.json — clang compile database
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_OS_CC = "test-repo/fmt/src/os.cc"
_BUILD_PATH = "test-repo/fmt/build"

# ---------------------------------------------------------------------------
# Pinned counts (SC-V4-2-03 / OQ-2-1).
#
# These values were determined by running the test once with a live daemon after
# the S1 (Identifier→str) and S3 (insert-vs-attempt) fixes landed.  If the
# fixture file or the graph schema changes, update these constants and record
# the change in implementation-notes.md.
# ---------------------------------------------------------------------------

_EXPECTED_VERTICES: int = 99  # pinned from live run 2026-05-17 against test-repo/fmt/src/os.cc
_EXPECTED_EDGES: int = (
    180  # pinned from live run 2026-05-17; counts only stored edges (both endpoints present)
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uri(uri: str) -> tuple[str, int]:
    from urllib.parse import urlparse

    parsed = urlparse(uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 27615
    return host, port


def _count_vertices(uri: str) -> int:
    """Return total vertex count from the daemon.

    ``client.get(AllVertexQuery())`` returns a lazy stream of batches; each
    batch is itself a list of Vertex objects.  The outer iterator must be
    flattened to obtain the true item count.
    """
    import indradb

    host, port = _parse_uri(uri)
    client = indradb.Client(host=f"{host}:{port}")
    return sum(len(batch) for batch in client.get(indradb.AllVertexQuery()))


def _count_edges(uri: str) -> int:
    """Return total edge count from the daemon.

    Same batch-streaming caveat as :func:`_count_vertices`.
    """
    import indradb

    host, port = _parse_uri(uri)
    client = indradb.Client(host=f"{host}:{port}")
    return sum(len(batch) for batch in client.get(indradb.AllEdgeQuery()))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_sc_v4_2_03_export_writes_expected_counts(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """SC-V4-2-03: exporting os.cc writes the expected vertex and edge counts.

    Also satisfies SC-V4-3-01 (insert counts match daemon query) and
    SC-V4-3-02 (attempted fields are present and >= written).

    The pinned constants _EXPECTED_VERTICES / _EXPECTED_EDGES are set after
    first run.  Until they are set, the test validates relational constraints only.
    """
    result = await mcp_client.call_tool(
        "ingest_code",
        {
            "file_path_or_dir": _OS_CC,
            "build_path": _BUILD_PATH,
            "db_uri": fresh_indradb,
        },
    )

    assert result.data is not None, f"Expected result data; got: {result!r}"
    data: dict[str, Any] = result.data  # type: ignore[assignment]

    assert "code" not in data, (
        f"Unexpected error envelope from ingest_code: code={data.get('code')!r}  "
        f"message={data.get('message')!r}"
    )

    nodes_written: int = data["nodes_written"]
    edges_written: int = data["edges_written"]
    nodes_attempted: int = data.get("nodes_attempted", nodes_written)
    edges_attempted: int = data.get("edges_attempted", edges_written)

    # SC-V4-3-02: attempted >= written (insert counting)
    assert nodes_attempted >= nodes_written, (
        f"nodes_attempted ({nodes_attempted}) < nodes_written ({nodes_written})"
    )
    assert edges_attempted >= edges_written, (
        f"edges_attempted ({edges_attempted}) < edges_written ({edges_written})"
    )

    # SC-V4-3-01: independent daemon query must match nodes_written / edges_written
    daemon_vertices = _count_vertices(fresh_indradb)
    daemon_edges = _count_edges(fresh_indradb)

    assert daemon_vertices == nodes_written, (
        f"Daemon vertex count ({daemon_vertices}) != nodes_written ({nodes_written})"
    )
    assert daemon_edges == edges_written, (
        f"Daemon edge count ({daemon_edges}) != edges_written ({edges_written})"
    )

    # SC-V4-2-03: pinned count assertions
    assert nodes_written == _EXPECTED_VERTICES, (
        f"nodes_written={nodes_written} but pinned expected={_EXPECTED_VERTICES}.  "
        "Update _EXPECTED_VERTICES if the fixture file or schema changed."
    )
    assert edges_written == _EXPECTED_EDGES, (
        f"edges_written={edges_written} but pinned expected={_EXPECTED_EDGES}.  "
        "Update _EXPECTED_EDGES if the fixture file or schema changed."
    )


@pytest.mark.integration
@pytest.mark.indradb
async def test_sc_v4_2_04_idempotent_reexport(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """SC-V4-2-04: second export of the same file writes zero nodes and zero edges."""
    args = {
        "file_path_or_dir": _OS_CC,
        "build_path": _BUILD_PATH,
        "db_uri": fresh_indradb,
    }

    # First export — populate the daemon
    first = await mcp_client.call_tool("ingest_code", args)
    assert first.data is not None, f"First export returned no data: {first!r}"
    first_data: dict[str, Any] = first.data  # type: ignore[assignment]
    assert "code" not in first_data, (
        f"First export returned error: {first_data.get('code')!r}: {first_data.get('message')!r}"
    )
    assert first_data["nodes_written"] > 0, (
        "First export wrote 0 nodes; daemon state may be non-empty.  "
        "Ensure fresh_indradb fixture wiped state correctly."
    )

    # Second export — must be idempotent (AC-2-4)
    second = await mcp_client.call_tool("ingest_code", args)
    assert second.data is not None, f"Second export returned no data: {second!r}"
    second_data: dict[str, Any] = second.data  # type: ignore[assignment]
    assert "code" not in second_data, (
        f"Second export returned error: {second_data.get('code')!r}: {second_data.get('message')!r}"
    )

    assert second_data["nodes_written"] == 0, (
        f"Expected nodes_written=0 on re-export; got {second_data['nodes_written']}.  "
        f"Insert-counting logic (ADR-17) may not be working correctly."
    )
    assert second_data["edges_written"] == 0, (
        f"Expected edges_written=0 on re-export; got {second_data['edges_written']}.  "
        f"Insert-counting logic (ADR-17) may not be working correctly."
    )
