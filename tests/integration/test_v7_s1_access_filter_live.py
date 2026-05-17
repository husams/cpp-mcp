"""Live IndraDB integration test: MEMBER_OF.access filter (v7-S1).

Covers:
  S1-2 AC4 — live export: MEMBER_OF edges carry access property
  S1-6 AC2 — edge_with_property_equal{"name":"access","value":"private"} returns
              only private members, excluding public/protected
  S1-6 SC2 — returned member set equals declared private members

Fixture: test-repo/v7s1/members.cc
  Widget class declares:
    public:    width, height, resize()   → access == "public"
    protected: internal_state           → access == "protected"
    private:   secret_value, another_secret → access == "private"

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

# Expected private member spellings from Widget class in members.cc
_EXPECTED_PRIVATE_MEMBER_SPELLINGS = {"secret_value", "another_secret"}


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


async def _query(
    mcp_client: Any,
    db_uri: str,
    verb: str,
    args: dict[str, Any] | None = None,
    row_limit: int = 500,
) -> dict[str, Any]:
    """Call query_graphdb and return the full payload dict."""
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
async def test_member_of_edges_carry_access_property(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-2 AC4: every MEMBER_OF edge returned by all_edges carries an 'access' property.

    After ingesting members.cc, all MEMBER_OF edges (for Widget and Point members)
    must have a non-empty 'access' property with a value in {public, protected, private}.
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(mcp_client, fresh_indradb, "all_edges")
    all_edges: list[dict[str, Any]] = data["rows"]

    member_of_edges = [e for e in all_edges if e.get("t") == "MEMBER_OF"]

    assert member_of_edges, "Expected at least one MEMBER_OF edge after ingesting members.cc"

    valid_access_values = {"public", "protected", "private"}
    for edge in member_of_edges:
        props = edge.get("properties", {})
        access = props.get("access")
        assert access in valid_access_values, (
            f"MEMBER_OF edge has access={access!r} not in {valid_access_values}; edge: {edge}"
        )


@pytest.mark.integration
@pytest.mark.indradb
async def test_edge_with_property_equal_private_returns_only_private_members(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-2 AC4 / S1-6 AC2 / S1-6 SC2: edge_with_property_equal access==private
    returns only MEMBER_OF edges for private members, excluding public/protected.

    Widget::secret_value and Widget::another_secret are private.
    Widget::width, Widget::height, Widget::resize() are public.
    Widget::internal_state is protected.
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(
        mcp_client,
        fresh_indradb,
        "edge_with_property_equal",
        args={"name": "access", "value": "private"},
    )
    private_edges: list[dict[str, Any]] = data["rows"]

    # All returned edges must be MEMBER_OF with access == "private"
    for edge in private_edges:
        assert edge.get("t") == "MEMBER_OF", (
            f"Expected only MEMBER_OF edges; got t={edge.get('t')!r}: {edge}"
        )
        assert edge.get("properties", {}).get("access") == "private", (
            f"Edge has access != 'private': {edge}"
        )

    # Extract vertex IDs for the outbound (member) side of private MEMBER_OF edges
    # MEMBER_OF direction: member → class (outbound=member, inbound=class)
    private_member_ids = {e["outbound_id"] for e in private_edges}

    assert private_member_ids, (
        "Expected at least one private MEMBER_OF edge (Widget::secret_value, "
        "Widget::another_secret) but got none"
    )

    # Fetch Field vertices and build an id→spelling map to verify by name
    field_query_str = json.dumps({"query": "vertex_with_type", "args": {"t": "Field"}})
    field_result = await mcp_client.call_tool(
        "query_graphdb",
        {"db_uri": fresh_indradb, "query": field_query_str, "row_limit": 500},
    )
    assert field_result.data is not None
    field_data: dict[str, Any] = field_result.data  # type: ignore[assignment]
    assert "code" not in field_data
    field_rows: list[dict[str, Any]] = field_data["rows"]

    field_id_to_spelling = {row["id"]: row["properties"].get("spelling", "") for row in field_rows}

    # The private member IDs must map only to expected private field spellings
    private_member_spellings = {
        field_id_to_spelling[vid] for vid in private_member_ids if vid in field_id_to_spelling
    }

    # All declared private fields must be present
    assert private_member_spellings >= _EXPECTED_PRIVATE_MEMBER_SPELLINGS, (
        f"Missing private members: "
        f"{_EXPECTED_PRIVATE_MEMBER_SPELLINGS - private_member_spellings}.  "
        f"Found spellings: {private_member_spellings}"
    )

    # No public or protected member spellings may appear
    public_protected_spellings = {"width", "height", "internal_state"}
    unexpected = private_member_spellings & public_protected_spellings
    assert not unexpected, (
        f"Public/protected members appeared in private filter results: {unexpected}"
    )


@pytest.mark.integration
@pytest.mark.indradb
async def test_public_member_access_edges_present_and_correct(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """S1-2 AC4: public members carry access=='public' on their MEMBER_OF edges.

    Widget::width and Widget::height are public fields; their MEMBER_OF edges
    must be returned by edge_with_property_equal{'access':'public'}.
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _query(
        mcp_client,
        fresh_indradb,
        "edge_with_property_equal",
        args={"name": "access", "value": "public"},
    )
    public_edges: list[dict[str, Any]] = data["rows"]

    assert public_edges, (
        "Expected at least one MEMBER_OF edge with access=='public' "
        "(Widget::width, Widget::height and resize() are public)"
    )
    for edge in public_edges:
        assert edge.get("t") == "MEMBER_OF"
        assert edge.get("properties", {}).get("access") == "public"
