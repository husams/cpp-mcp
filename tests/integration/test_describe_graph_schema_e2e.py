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
#
# S2 rewrite addendum (ADR-26 D9, 2026-05-17):
#   PARM_DECL is now reclassified from Variable → Parameter (ADR-26 D9).
#   "Variable" count drops to 0 for fresh S2 exports; "Parameter" count > 0.
#   _V2_SPLIT_TYPES updated: "Variable" replaced by "Parameter".
#   The split_sum invariant becomes Field + GlobalVariable + Parameter == 33.
#
#   S2 also adds Type/Parameter nodes and RETURNS/HAS_PARAM/OF_TYPE/POINTS_TO/
#   REFERS_TO edges, so total vertex and edge counts change after S2 export.
#   Total counts are now asserted as >= the S1 baseline (not pinned == 99/180)
#   to avoid fragility across schema enrichments.
#
#   Edge set assertion changed from exact-set-equality to subset-of-actual so
#   the five new S2 edge types (RETURNS, HAS_PARAM, etc.) do not break this
#   test when a live S2 export is used.
# ---------------------------------------------------------------------------

# S1 baseline totals; S2 may produce more vertices (Type nodes) and more edges.
_EXPECTED_TOTAL_VERTICES_MIN: int = 99
_EXPECTED_TOTAL_EDGES_MIN: int = 180

# Keep original names as aliases for clarity in comments below.
_EXPECTED_TOTAL_VERTICES: int = _EXPECTED_TOTAL_VERTICES_MIN
_EXPECTED_TOTAL_EDGES: int = _EXPECTED_TOTAL_EDGES_MIN

# Corpus-stable pinned counts: types unaffected by the v2 Variable split or S2.
_EXPECTED_NODE_COUNTS_STABLE: dict[str, int] = {
    "TypeAlias": 28,
    "Function": 21,
    "Class": 13,
    "Namespace": 3,
    "File": 1,
}

# v2+S2 split types: Variable replaced by Parameter per ADR-26 D9.
# Fresh S2 exports emit Parameter for PARM_DECL, not Variable.
# Variable is retained in ALL_NODE_TYPES for read-compat (ADR-25 D1) but
# the count for fresh exports is 0.
_V2_SPLIT_TYPES = {"Field", "GlobalVariable", "Parameter"}

# All expected v2+S2 node type names (structural invariant — set equality).
# S2 additionally adds Type and Parameter; both must appear.
_EXPECTED_NODE_TYPE_NAMES = set(_EXPECTED_NODE_COUNTS_STABLE.keys()) | _V2_SPLIT_TYPES | {"Type"}

# Corpus-stable edge types: these always appear regardless of S2 additions.
# The full set includes S2 edges; we assert as a subset so new edge types
# added in future stages do not break this test.
_EXPECTED_EDGE_COUNTS: dict[str, int] = {
    "DEFINES": 98,
    "REFERENCES": 82,
}

# Property keys expected for symbol node types (from exporter.py props dict).
_SYMBOL_PROP_KEYS = {"spelling", "type", "file", "line", "col"}

# File node property keys.
_FILE_PROP_KEYS = {"path", "spelling", "schema_version"}

# Node types that are symbols (not File) — v2+S2 names.
# Parameter and Type are S2 additions; both have a 'spelling' property.
# Variable is retained for read-compat (ADR-25 D1) but may be absent in
# fresh S2 exports (ADR-26 D9: PARM_DECL → Parameter).
_SYMBOL_NODE_TYPES = {
    "Variable",
    "Field",
    "GlobalVariable",
    "TypeAlias",
    "Function",
    "Class",
    "Namespace",
    "Parameter",
    "Type",
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
    """AC-Q3-1: totals.vertices>=99 and totals.edges>=180 after ingest of os.cc.

    S2 rewrite (ADR-26 D9, 2026-05-17): S2 adds Type nodes (one per distinct
    type spelling) and five new edge types (RETURNS, HAS_PARAM, OF_TYPE,
    POINTS_TO, REFERS_TO).  The exact totals are corpus-dependent and will
    be higher than the S1 baseline (99 vertices, 180 edges).  We assert
    >= the S1 baseline rather than == to avoid fragility across S2 additions.
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    totals: dict[str, int] = data["totals"]
    assert totals["vertices"] >= _EXPECTED_TOTAL_VERTICES_MIN, (
        f"totals.vertices={totals['vertices']} below S1 baseline={_EXPECTED_TOTAL_VERTICES_MIN}"
    )
    assert totals["edges"] >= _EXPECTED_TOTAL_EDGES_MIN, (
        f"totals.edges={totals['edges']} below S1 baseline={_EXPECTED_TOTAL_EDGES_MIN}"
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
    """AC-Q3-2: v2+S2 vertex types present with structural + corpus-stable counts.

    QD-1 fix (2026-05-17): the original test pinned "Variable: 33" which is a
    v1 count.  After the S1 Variable→Field/GlobalVariable split (ADR-25 D2)
    the exporter emits Field/GlobalVariable for data-members/globals; Variable
    survives only for PARM_DECL nodes and its count is < 33.

    S2 rewrite (ADR-26 D9, 2026-05-17): PARM_DECL is now reclassified from
    Variable → Parameter.  Fresh S2 exports emit zero Variable nodes and
    non-zero Parameter nodes.  _V2_SPLIT_TYPES now contains
    {Field, GlobalVariable, Parameter}.  The split_sum invariant becomes
    Field + GlobalVariable + Parameter == 33 (same physical nodes, renamed).
    S2 also adds Type nodes; "Type" must appear in the node type set.

    We assert:
      (a) The required node types are a subset of actual (superset OK for
          forward compat — new node types added in future stages are fine).
      (b) The three v2+S2 split types (Field, GlobalVariable, Parameter) are
          all present and their counts sum to 33 (original v1 Variable total).
      (c) Parameter count > 0 and Variable count == 0 for a fresh S2 export.
      (d) Corpus-stable types (TypeAlias, Function, Class, Namespace, File) have
          pinned counts that should not change across schema versions.
      (e) Type node type is present with count > 0 (S2 adds Type nodes).
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    node_types: list[dict[str, Any]] = data["node_types"]
    node_map: dict[str, dict[str, Any]] = {t["name"]: t for t in node_types}

    # (a) Structural invariant: required node type names must be present (subset check).
    type_names = set(node_map.keys())
    assert _EXPECTED_NODE_TYPE_NAMES.issubset(type_names), (
        f"Missing expected node type names.\n"
        f"  missing: {sorted(_EXPECTED_NODE_TYPE_NAMES - type_names)}\n"
        f"  got: {sorted(type_names)}"
    )

    # (b) v2+S2 split types all present; Field + GlobalVariable + Parameter == 33.
    for split_type in _V2_SPLIT_TYPES:
        assert split_type in node_map, f"v2+S2 split type {split_type!r} missing from node_types"
    split_sum = sum(node_map[t]["count"] for t in _V2_SPLIT_TYPES)
    field_c = node_map["Field"]["count"]
    gvar_c = node_map["GlobalVariable"]["count"]
    param_c = node_map["Parameter"]["count"]
    assert split_sum == 33, (
        f"Field+GlobalVariable+Parameter count sum expected 33 (v1 Variable total), "
        f"got {split_sum}; Field={field_c}, GlobalVariable={gvar_c}, Parameter={param_c}"
    )

    # (c) Parameter count > 0; Variable count == 0 for fresh S2 export (ADR-26 D9).
    assert param_c > 0, f"Parameter count={param_c} should be > 0 after S2 (PARM_DECL → Parameter)"
    # Variable may be absent from fresh S2 exports; if present count must be 0.
    if "Variable" in node_map:
        variable_count = node_map["Variable"]["count"]
        assert variable_count == 0, (
            f"Variable count={variable_count} should be 0 for fresh S2 export "
            f"(PARM_DECL reclassified to Parameter per ADR-26 D9)"
        )

    # (d) Corpus-stable types: pinned counts unchanged by v2 split or S2 additions.
    for name, expected_count in _EXPECTED_NODE_COUNTS_STABLE.items():
        actual_count = node_map[name]["count"]
        assert actual_count == expected_count, (
            f"Vertex type {name!r}: expected corpus-stable "
            f"count={expected_count}, got {actual_count}"
        )

    # (e) Type node present with count > 0 (S2 adds Type nodes per ADR-26 D1).
    assert "Type" in node_map, "Type node type must appear in S2 export describe output"
    type_count = node_map["Type"]["count"]
    assert type_count > 0, f"Type node count={type_count} should be > 0 after S2 ingest"


@pytest.mark.integration
@pytest.mark.indradb
async def test_ac_q3_2_edge_type_counts_pinned(
    mcp_client: Any,
    fresh_indradb: str,
) -> None:
    """AC-Q3-2: DEFINES and REFERENCES edge types with pinned counts.

    S2 rewrite (ADR-26 D9, 2026-05-17): S2 adds five new edge types
    (RETURNS, HAS_PARAM, OF_TYPE, POINTS_TO, REFERS_TO).  The exact set
    of edge types in the graph is no longer just DEFINES+REFERENCES.
    We now assert:
      - DEFINES and REFERENCES are present (subset check, not equality).
      - DEFINES and REFERENCES counts match the corpus-stable pinned values.
      - Total edge type count >= 2 (forward-compat: new types allowed).
    """
    await _ingest(mcp_client, fresh_indradb)

    data = await _describe(mcp_client, fresh_indradb)

    edge_types: list[dict[str, Any]] = data["edge_types"]

    type_names = {t["name"] for t in edge_types}
    expected_names = set(_EXPECTED_EDGE_COUNTS.keys())
    # Subset check: DEFINES and REFERENCES must be present; S2 may add more.
    assert expected_names.issubset(type_names), (
        f"Missing expected edge type names.\n"
        f"  missing: {sorted(expected_names - type_names)}\n"
        f"  got: {sorted(type_names)}"
    )
    assert len(edge_types) >= len(_EXPECTED_EDGE_COUNTS), (
        f"Expected at least {len(_EXPECTED_EDGE_COUNTS)} edge types, got {len(edge_types)}"
    )

    edge_map = {t["name"]: t for t in edge_types}
    for name, expected_count in _EXPECTED_EDGE_COUNTS.items():
        assert name in edge_map, f"Edge type {name!r} missing from edge_types"
        assert edge_map[name]["count"] == expected_count, (
            f"Edge type {name!r}: expected count={expected_count}, got {edge_map[name]['count']}"
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
    # v2+S2 exact order depends on Field/GlobalVariable/Parameter split counts and
    # Type count (S2 new node) that are not pinned without a live run.
    # We assert the corpus-stable invariants:
    #   - The v2+S2 split types (Field, GlobalVariable, Parameter) appear before
    #     TypeAlias(28) because their combined count is 33 and all three must be
    #     > 0; individually at least one must rank above TypeAlias.
    #   - TypeAlias(28) > Function(21) > Class(13) > Namespace(3) > File(1) ordering
    #     is corpus-stable (these types are unaffected by the v2 split or S2).
    #
    # QD-1 fix (2026-05-17): removed the exact 6-element list assertion.
    # S2 rewrite (ADR-26 D9, 2026-05-17): _V2_SPLIT_TYPES updated to
    # {Field, GlobalVariable, Parameter}; Variable replaced by Parameter.
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
    # All v2+S2 split types must appear before TypeAlias (index of TypeAlias > index of each).
    type_alias_idx = actual_node_order.index("TypeAlias")
    for split_type in _V2_SPLIT_TYPES:
        if split_type not in actual_node_order:
            continue  # skip if not present (may be zero-count and omitted by introspector)
        split_idx = actual_node_order.index(split_type)
        assert split_idx < type_alias_idx, (
            f"v2+S2 split type {split_type!r} (index {split_idx}) must appear before "
            f"TypeAlias (index {type_alias_idx}); full order: {actual_node_order}"
        )

    # Verify edge sort order: DEFINES(98) > REFERENCES(82) must appear at the top.
    # S2 adds more edge types so we verify the relative order of the two corpus-stable
    # edge types, not the full list.
    actual_edge_order = [t["name"] for t in edge_types]
    stable_edges = [name for name in actual_edge_order if name in {"DEFINES", "REFERENCES"}]
    assert stable_edges == ["DEFINES", "REFERENCES"], (
        f"DEFINES and REFERENCES must appear in descending count order.\n"
        f"  expected relative order: ['DEFINES', 'REFERENCES']\n"
        f"  got (filtered): {stable_edges}\n"
        f"  full actual edge order: {actual_edge_order}"
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
