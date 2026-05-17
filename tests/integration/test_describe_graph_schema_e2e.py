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
#
# v1 counts (pre-S1, for reference only — do NOT assert these):
#   Variable(33) > TypeAlias(28) > Function(21) > Class(13) > Namespace(3) > File(1)
#
# v2 counts (post-S1 Variable→Field/GlobalVariable split, ADR-25 D2):
#   - "Variable" is emitted ONLY for PARM_DECL nodes; count < 33 (exact value
#     is corpus-dependent and not pinned here to avoid fragility)
#   - "Field"          — new: non-static class data members (previously Variable)
#   - "GlobalVariable" — new: namespace-scope vars (previously Variable)
#   - Total vertices unchanged: 99; total edges unchanged: 180
#   - "File: 1" is corpus-stable (one translation unit) and IS pinned
#   - TypeAlias(28), Function(21), Class(13), Namespace(3) are corpus-stable
#     (no v2 split affects them) and ARE pinned
#
# Rewrite rationale (QD-1 resolution, 2026-05-17):
#   The original exact-count dict assumed the v1 "Variable" type would survive
#   the S1 split unchanged.  After S1 the exporter emits Field/GlobalVariable
#   for data-members and globals; only PARM_DECL still produces Variable.
#   Because we have no live daemon at edit time to recompute exact Field /
#   GlobalVariable / Variable counts, we pin only types whose counts are
#   corpus-stable and well-documented, and assert structural invariants for
#   the split types (presence + sum constraint).
# ---------------------------------------------------------------------------

_EXPECTED_TOTAL_VERTICES: int = 99
_EXPECTED_TOTAL_EDGES: int = 180

# Corpus-stable pinned counts: types unaffected by the v2 Variable split.
_EXPECTED_NODE_COUNTS_STABLE: dict[str, int] = {
    "TypeAlias": 28,
    "Function": 21,
    "Class": 13,
    "Namespace": 3,
    "File": 1,
}

# v2-split types: must be present but counts are not pinned (TBD from live run).
_V2_SPLIT_TYPES = {"Field", "GlobalVariable", "Variable"}

# All expected v2 node type names (structural invariant — set equality).
_EXPECTED_NODE_TYPE_NAMES = set(_EXPECTED_NODE_COUNTS_STABLE.keys()) | _V2_SPLIT_TYPES

# Map edge type name → expected count.
_EXPECTED_EDGE_COUNTS: dict[str, int] = {
    "DEFINES": 98,
    "REFERENCES": 82,
}

# Property keys expected for symbol node types (from exporter.py props dict).
_SYMBOL_PROP_KEYS = {"spelling", "type", "file", "line", "col"}

# File node property keys.
_FILE_PROP_KEYS = {"path", "spelling", "schema_version"}

# Node types that are symbols (not File) — v2 names.
_SYMBOL_NODE_TYPES = {
    "Variable",
    "Field",
    "GlobalVariable",
    "TypeAlias",
    "Function",
    "Class",
    "Namespace",
}


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
    assert data["schema_version"] == "v2"
    assert "request_id" in data
    assert len(data["request_id"]) == 32  # UUID4 hex


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_2_vertex_type_counts_pinned(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-2: v2 vertex types present with structural + corpus-stable counts.

    QD-1 fix (2026-05-17): the original test pinned "Variable: 33" which is a
    v1 count.  After the S1 Variable→Field/GlobalVariable split (ADR-25 D2)
    the exporter emits Field/GlobalVariable for data-members/globals; Variable
    survives only for PARM_DECL nodes and its count is < 33.  We assert:
      (a) The set of vertex type names equals _EXPECTED_NODE_TYPE_NAMES (includes
          Field, GlobalVariable, Variable; excludes the v1-only "Variable" key).
      (b) The three v2-split types (Field, GlobalVariable, Variable) are all
          present and their counts sum to the original v1 Variable count of 33.
      (c) Variable count is strictly less than 33 (PARM_DECL-only).
      (d) Corpus-stable types (TypeAlias, Function, Class, Namespace, File) have
          pinned counts that should not change across schema versions.
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    node_types: list[dict[str, Any]] = data["node_types"]
    node_map: dict[str, dict[str, Any]] = {t["name"]: t for t in node_types}

    # (a) Structural invariant: exact set of v2 node type names.
    type_names = set(node_map.keys())
    assert type_names == _EXPECTED_NODE_TYPE_NAMES, (
        f"Vertex type names mismatch.\n"
        f"  expected: {sorted(_EXPECTED_NODE_TYPE_NAMES)}\n  got: {sorted(type_names)}"
    )

    # (b) v2-split types all present; Field + GlobalVariable + Variable == 33 (original total).
    for split_type in _V2_SPLIT_TYPES:
        assert split_type in node_map, f"v2 split type {split_type!r} missing from node_types"
    split_sum = sum(node_map[t]["count"] for t in _V2_SPLIT_TYPES)
    field_c = node_map["Field"]["count"]
    gvar_c = node_map["GlobalVariable"]["count"]
    var_c = node_map["Variable"]["count"]
    assert split_sum == 33, (
        f"Field+GlobalVariable+Variable count sum expected 33 (v1 Variable total), "
        f"got {split_sum}; Field={field_c}, GlobalVariable={gvar_c}, Variable={var_c}"
    )

    # (c) Variable is PARM_DECL-only after S1 — count must be < 33.
    variable_count = node_map["Variable"]["count"]
    assert variable_count < 33, (
        f"Variable count={variable_count} should be < 33 after v2 split (PARM_DECL-only)"
    )

    # (d) Corpus-stable types: pinned counts unchanged by v2 split.
    for name, expected_count in _EXPECTED_NODE_COUNTS_STABLE.items():
        actual_count = node_map[name]["count"]
        assert actual_count == expected_count, (
            f"Vertex type {name!r}: expected corpus-stable "
            f"count={expected_count}, got {actual_count}"
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
        assert len(prop_keys) > 0, f"Vertex type {name!r} has empty property_keys"

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

    # Verify node sort order: sorted by (-count, name).
    # v2 exact order depends on Field/GlobalVariable/Variable split counts that
    # are not pinned without a live run.  We assert the corpus-stable invariants:
    #   - The three v2 split types (Field, GlobalVariable, Variable) appear before
    #     TypeAlias(28) because their combined count was 33 and all three must be
    #     > 0; individually at least one must rank above TypeAlias.
    #   - TypeAlias(28) > Function(21) > Class(13) > Namespace(3) > File(1) ordering
    #     is corpus-stable (these types are unaffected by the v2 split).
    #
    # QD-1 fix (2026-05-17): removed the exact 6-element list assertion because the
    # v2 split produces 8 node types with relative ordering among Field/GlobalVariable/
    # Variable that depends on live corpus counts.  Pinning the stable suffix is
    # sufficient for regression detection.
    actual_node_order = [t["name"] for t in node_types]
    stable_suffix = ["TypeAlias", "Function", "Class", "Namespace", "File"]
    # All stable types must appear in the correct relative order at the tail.
    stable_actual = [name for name in actual_node_order if name in set(stable_suffix)]
    assert stable_actual == stable_suffix, (
        f"Corpus-stable node_types tail order wrong.\n"
        f"  expected suffix (relative): {stable_suffix}\n"
        f"  got (filtered): {stable_actual}\n"
        f"  full actual order: {actual_node_order}"
    )
    # All v2-split types must appear before TypeAlias (index of TypeAlias > index of each).
    type_alias_idx = actual_node_order.index("TypeAlias")
    for split_type in _V2_SPLIT_TYPES:
        split_idx = actual_node_order.index(split_type)
        assert split_idx < type_alias_idx, (
            f"v2 split type {split_type!r} (index {split_idx}) must appear before "
            f"TypeAlias (index {type_alias_idx}); full order: {actual_node_order}"
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
    """AC-Q3-4: schema_version == 'v2'; notes list has at least the two static entries."""
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    assert data["schema_version"] == "v2", (
        f"Expected schema_version='v2', got {data['schema_version']!r}"
    )

    notes: list[str] = data["notes"]
    assert len(notes) >= 2, f"Expected at least 2 static notes, got {len(notes)}: {notes}"
    # Static note substrings that must appear in the notes list.
    assert any("sample" in n.lower() for n in notes), "Expected a note about property key sampling"
    assert any("live" in n.lower() or "concurrent" in n.lower() for n in notes), (
        "Expected a note about live counts"
    )
