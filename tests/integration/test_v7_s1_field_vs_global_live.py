"""Live IndraDB integration test: Field vs GlobalVariable split (v7-S1).

Covers:
  S1-1 AC5 — live export produces Field and GlobalVariable vertex types (not Variable)
  S1-6 AC1 — at least one Field and one GlobalVariable vertex present and disjoint
  S1-6 SC1 — Field and GlobalVariable vertex sets are mutually exclusive

Fixture: test-repo/v7s1/members.cc
  - Widget class with non-static data members (width, height, internal_state,
    secret_value, another_secret) → Field nodes
  - Namespace-scope vars (global_counter, MAX_SIZE) → GlobalVariable nodes

Environment:
    INDRADB_TEST_URI    gRPC URI, e.g. grpc://127.0.0.1:27615 (required; else skip)
    INDRADB_AUTOSTART   set to '1' to spawn indradb-server memory automatically
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_MEMBERS_CC = "test-repo/v7s1/members.cc"
_BUILD_PATH = "test-repo/v7s1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ingest(mcp_client: Any, db_uri: str) -> None:
    """Ingest members.cc via the production ingest_code MCP tool."""
    result = await mcp_client.call_tool(
        "ingest_code",
        {
            "file_path_or_dir": _MEMBERS_CC,
            "build_path": _BUILD_PATH,
            "db_uri": db_uri,
        },
    )
    assert result.data is not None, f"ingest_code returned no data: {result!r}"
    data: dict[str, Any] = result.data  # type: ignore[assignment]
    assert "code" not in data, (
        f"ingest_code returned error: code={data.get('code')!r}  message={data.get('message')!r}"
    )
    assert data["files_processed"] == 1, (
        f"Expected 1 file processed, got {data['files_processed']}.  "
        f"Errors: {data.get('errors', [])}"
    )


async def _query_vertex_type(
    mcp_client: Any,
    db_uri: str,
    t: str,
    row_limit: int = 500,
) -> list[dict[str, Any]]:
    """Query all vertices of type *t* and return the rows list."""
    query_str = json.dumps({"query": "vertex_with_type", "args": {"t": t}})
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
    return data["rows"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_field_nodes_present_after_ingest(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-1 AC5 / S1-6 AC1: at least one Field vertex is present after ingest.

    Widget::width, Widget::height, Widget::internal_state, Widget::secret_value,
    Widget::another_secret, Point::x, Point::y are all non-static class data
    members → Field nodes (ADR-25 D1).
    """
    await _ingest(mcp_client, fresh_indradb)

    field_rows = await _query_vertex_type(mcp_client, fresh_indradb, "Field")

    assert len(field_rows) >= 1, (
        f"Expected at least one Field vertex after ingesting {_MEMBERS_CC}; got 0"
    )
    for row in field_rows:
        assert row.get("t") == "Field", f"Unexpected vertex type in row: {row}"
        assert "id" in row
        assert "properties" in row


@pytest.mark.integration
@pytest.mark.indradb
async def test_global_variable_nodes_present_after_ingest(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-1 AC5 / S1-6 AC1: at least one GlobalVariable vertex is present after ingest.

    global_counter and MAX_SIZE are namespace-scope VAR_DECL → GlobalVariable
    nodes (ADR-25 D1).
    """
    await _ingest(mcp_client, fresh_indradb)

    gv_rows = await _query_vertex_type(mcp_client, fresh_indradb, "GlobalVariable")

    assert len(gv_rows) >= 1, (
        f"Expected at least one GlobalVariable vertex after ingesting {_MEMBERS_CC}; got 0"
    )
    for row in gv_rows:
        assert row.get("t") == "GlobalVariable", f"Unexpected vertex type in row: {row}"
        assert "id" in row
        assert "properties" in row


@pytest.mark.integration
@pytest.mark.indradb
async def test_field_and_global_variable_vertex_sets_are_disjoint(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-6 AC1 / S1-6 SC1: Field and GlobalVariable vertex ID sets are mutually exclusive.

    No vertex can carry both labels simultaneously (IndraDB is single-label per vertex).
    Verified by comparing the UUID sets returned by each vertex_with_type query.
    """
    await _ingest(mcp_client, fresh_indradb)

    field_rows = await _query_vertex_type(mcp_client, fresh_indradb, "Field")
    gv_rows = await _query_vertex_type(mcp_client, fresh_indradb, "GlobalVariable")

    field_ids = {row["id"] for row in field_rows}
    gv_ids = {row["id"] for row in gv_rows}

    overlap = field_ids & gv_ids
    assert not overlap, f"Field and GlobalVariable vertex sets overlap; shared IDs: {overlap}"


@pytest.mark.integration
@pytest.mark.indradb
async def test_no_variable_nodes_for_class_members_or_namespace_vars(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-1 AC5: FIELD_DECL and VAR_DECL no longer emit Variable nodes in v2 schema.

    After ingesting members.cc (which contains only data members, no functions),
    there are no PARM_DECL cursors in the file.  Variable vertices (which map only
    to PARM_DECL in v2) should therefore be absent from this fresh ingest.

    Note: this assertion is scoped to the freshly-wiped members.cc ingest.  It does
    not assert "no Variable nodes anywhere" — ADR-25 D2 keeps PARM_DECL as Variable
    for files that contain functions with parameters.
    """
    await _ingest(mcp_client, fresh_indradb)

    variable_rows = await _query_vertex_type(mcp_client, fresh_indradb, "Variable")

    assert len(variable_rows) == 0, (
        f"Unexpected Variable vertices found after v2 ingest of {_MEMBERS_CC}: "
        f"{[r.get('properties', {}).get('spelling', r['id']) for r in variable_rows]}"
    )
