"""Real IndraDB end-to-end tests for describe_graph_schema.

Covers:
  AC-Q3-1 — totals.vertices == 99 and totals.edges == 180
  AC-Q3-2 — six vertex types with pinned counts; two edge types with pinned counts
  AC-Q3-4 — schema_version field present; property_keys non-empty per type

Environment:
    INDRADB_TEST_URI    gRPC URI, e.g. grpc://127.0.0.1:27615 (required; else skip)
    INDRADB_AUTOSTART   set to '1' to spawn indradb-server memory automatically
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixture paths (same as test_indradb_e2e.py)
# ---------------------------------------------------------------------------

_OS_CC = "test-repo/fmt/src/os.cc"
_BUILD_PATH = "test-repo/fmt/build"

# ---------------------------------------------------------------------------
# Pinned schema counts (2026-05-17 live run against test-repo/fmt/src/os.cc)
# sorted by (-count, name): Variable(33) > TypeAlias(28) > Function(21) >
#   Class(13) > Namespace(3) > File(1)
# edge types: DEFINES(98) > REFERENCES(82)
# ---------------------------------------------------------------------------

_EXPECTED_TOTAL_VERTICES: int = 99
_EXPECTED_TOTAL_EDGES: int = 180

# Map vertex type name → expected count.
_EXPECTED_NODE_COUNTS: dict[str, int] = {
    "Variable": 33,
    "TypeAlias": 28,
    "Function": 21,
    "Class": 13,
    "Namespace": 3,
    "File": 1,
}

# Map edge type name → expected count.
_EXPECTED_EDGE_COUNTS: dict[str, int] = {
    "DEFINES": 98,
    "REFERENCES": 82,
}

# Property keys expected for symbol node types (from exporter.py props dict).
_SYMBOL_PROP_KEYS = {"spelling", "type", "file", "line", "col"}

# File node property keys.
_FILE_PROP_KEYS = {"path", "spelling", "schema_version"}

# Node types that are symbols (not File).
_SYMBOL_NODE_TYPES = {"Variable", "TypeAlias", "Function", "Class", "Namespace"}


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
        f"ingest_code returned error: code={data.get('code')!r}  "
        f"message={data.get('message')!r}"
    )


async def _describe(mcp_client: Any, db_uri: str, sample_size: int = 100) -> dict[str, Any]:
    """Call describe_graph_schema and return the success payload dict."""
    result = await mcp_client.call_tool(
        "describe_graph_schema",
        {
            "db_uri": db_uri,
            "sample_size": sample_size,
        },
    )
    assert result.data is not None, f"describe_graph_schema returned no data: {result!r}"
    data: dict[str, Any] = result.data  # type: ignore[assignment]
    assert "code" not in data, (
        f"describe_graph_schema returned error: code={data.get('code')!r}  "
        f"message={data.get('message')!r}"
    )
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_1_totals_pinned(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-1: totals.vertices==99 and totals.edges==180 after ingest of os.cc."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    totals: dict[str, int] = data["totals"]
    assert totals["vertices"] == _EXPECTED_TOTAL_VERTICES, (
        f"totals.vertices={totals['vertices']} but pinned={_EXPECTED_TOTAL_VERTICES}"
    )
    assert totals["edges"] == _EXPECTED_TOTAL_EDGES, (
        f"totals.edges={totals['edges']} but pinned={_EXPECTED_TOTAL_EDGES}"
    )

    # Top-level shape checks.
    assert data["backend"] == "indradb"
    assert data["schema_version"] == "v1"
    assert "request_id" in data
    assert len(data["request_id"]) == 32  # UUID4 hex


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_2_vertex_type_counts_pinned(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-2: exactly six vertex types with pinned counts."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    node_types: list[dict[str, Any]] = data["node_types"]

    type_names = {t["name"] for t in node_types}
    expected_names = set(_EXPECTED_NODE_COUNTS.keys())
    assert type_names == expected_names, (
        f"Vertex type names mismatch.\n"
        f"  expected: {sorted(expected_names)}\n  got: {sorted(type_names)}"
    )
    assert len(node_types) == len(_EXPECTED_NODE_COUNTS), (
        f"Expected {len(_EXPECTED_NODE_COUNTS)} vertex types, got {len(node_types)}"
    )

    for entry in node_types:
        name = entry["name"]
        expected_count = _EXPECTED_NODE_COUNTS[name]
        assert entry["count"] == expected_count, (
            f"Vertex type {name!r}: expected count={expected_count}, got {entry['count']}"
        )


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_2_edge_type_counts_pinned(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-2: exactly two edge types (DEFINES, REFERENCES) with pinned counts."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    edge_types: list[dict[str, Any]] = data["edge_types"]

    type_names = {t["name"] for t in edge_types}
    expected_names = set(_EXPECTED_EDGE_COUNTS.keys())
    assert type_names == expected_names, (
        f"Edge type names mismatch.\n"
        f"  expected: {sorted(expected_names)}\n  got: {sorted(type_names)}"
    )
    assert len(edge_types) == len(_EXPECTED_EDGE_COUNTS), (
        f"Expected {len(_EXPECTED_EDGE_COUNTS)} edge types, got {len(edge_types)}"
    )

    for entry in edge_types:
        name = entry["name"]
        expected_count = _EXPECTED_EDGE_COUNTS[name]
        assert entry["count"] == expected_count, (
            f"Edge type {name!r}: expected count={expected_count}, got {entry['count']}"
        )


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_4_property_keys_non_empty(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-4: each vertex type's property_keys is non-empty and contains expected keys.

    Symbol node types (Function, Class, Variable, Namespace, TypeAlias) must
    include 'spelling' (the identifier name key from exporter.py).
    File node type must include 'path' and 'schema_version'.
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    node_types: list[dict[str, Any]] = data["node_types"]
    node_map = {t["name"]: t for t in node_types}

    for name, entry in node_map.items():
        prop_keys: list[str] = entry["property_keys"]
        assert len(prop_keys) > 0, (
            f"Vertex type {name!r} has empty property_keys"
        )

        if name in _SYMBOL_NODE_TYPES:
            assert "spelling" in prop_keys, (
                f"Vertex type {name!r} missing 'spelling' in property_keys: {prop_keys}"
            )
        elif name == "File":
            assert "path" in prop_keys, (
                f"File vertex type missing 'path' in property_keys: {prop_keys}"
            )
            assert "schema_version" in prop_keys, (
                f"File vertex type missing 'schema_version' in property_keys: {prop_keys}"
            )


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_4_sort_order_by_count_desc(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-4 / AC-Q2-5: node_types and edge_types are sorted by (-count, name)."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    node_types: list[dict[str, Any]] = data["node_types"]
    edge_types: list[dict[str, Any]] = data["edge_types"]

    # Verify node sort order: Variable(33) > TypeAlias(28) > Function(21) >
    #   Class(13) > Namespace(3) > File(1)
    expected_node_order = ["Variable", "TypeAlias", "Function", "Class", "Namespace", "File"]
    actual_node_order = [t["name"] for t in node_types]
    assert actual_node_order == expected_node_order, (
        f"node_types sort order wrong.\n"
        f"  expected: {expected_node_order}\n  got: {actual_node_order}"
    )

    # Verify edge sort order: DEFINES(98) > REFERENCES(82)
    expected_edge_order = ["DEFINES", "REFERENCES"]
    actual_edge_order = [t["name"] for t in edge_types]
    assert actual_edge_order == expected_edge_order, (
        f"edge_types sort order wrong.\n"
        f"  expected: {expected_edge_order}\n  got: {actual_edge_order}"
    )


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_4_schema_version_field_and_notes(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-4: schema_version == 'v1'; notes list has at least the two static entries."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    assert data["schema_version"] == "v1", (
        f"Expected schema_version='v1', got {data['schema_version']!r}"
    )

    notes: list[str] = data["notes"]
    assert len(notes) >= 2, f"Expected at least 2 static notes, got {len(notes)}: {notes}"
    # Static note substrings that must appear in the notes list.
    assert any("sample" in n.lower() for n in notes), (
        "Expected a note about property key sampling"
    )
    assert any("live" in n.lower() or "concurrent" in n.lower() for n in notes), (
        "Expected a note about live counts"
    )
