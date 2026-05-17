"""P1 schema-constants tests — S2 (ADR-26 D8, D9).

Asserts:
- New node constants exist and are non-empty strings.
- New edge constants exist and are non-empty strings.
- All new constants appear in their respective ALL_* frozensets.
- All new constants are unique across the full ALL_* sets.
- NODE_VARIABLE is still exported (read-compat invariant, ADR-25 D1 / ADR-26 D9).
"""

from __future__ import annotations

import cpp_mcp.graphdb.schema as schema

# ---------------------------------------------------------------------------
# New node constants
# ---------------------------------------------------------------------------


def test_node_type_constant_value() -> None:
    assert schema.NODE_TYPE == "Type"


def test_node_parameter_constant_value() -> None:
    assert schema.NODE_PARAMETER == "Parameter"


def test_new_node_constants_are_strings() -> None:
    for const in (schema.NODE_TYPE, schema.NODE_PARAMETER):
        assert isinstance(const, str) and const, f"Expected non-empty str, got {const!r}"


def test_new_node_constants_in_all_node_types() -> None:
    assert schema.NODE_TYPE in schema.ALL_NODE_TYPES
    assert schema.NODE_PARAMETER in schema.ALL_NODE_TYPES


# ---------------------------------------------------------------------------
# New edge constants
# ---------------------------------------------------------------------------


def test_edge_returns_constant_value() -> None:
    assert schema.EDGE_RETURNS == "RETURNS"


def test_edge_has_param_constant_value() -> None:
    assert schema.EDGE_HAS_PARAM == "HAS_PARAM"


def test_edge_of_type_constant_value() -> None:
    assert schema.EDGE_OF_TYPE == "OF_TYPE"


def test_edge_points_to_constant_value() -> None:
    assert schema.EDGE_POINTS_TO == "POINTS_TO"


def test_edge_refers_to_constant_value() -> None:
    assert schema.EDGE_REFERS_TO == "REFERS_TO"


def test_new_edge_constants_are_strings() -> None:
    new_edges = (
        schema.EDGE_RETURNS,
        schema.EDGE_HAS_PARAM,
        schema.EDGE_OF_TYPE,
        schema.EDGE_POINTS_TO,
        schema.EDGE_REFERS_TO,
    )
    for const in new_edges:
        assert isinstance(const, str) and const, f"Expected non-empty str, got {const!r}"


def test_new_edge_constants_in_all_edge_types() -> None:
    assert schema.EDGE_RETURNS in schema.ALL_EDGE_TYPES
    assert schema.EDGE_HAS_PARAM in schema.ALL_EDGE_TYPES
    assert schema.EDGE_OF_TYPE in schema.ALL_EDGE_TYPES
    assert schema.EDGE_POINTS_TO in schema.ALL_EDGE_TYPES
    assert schema.EDGE_REFERS_TO in schema.ALL_EDGE_TYPES


# ---------------------------------------------------------------------------
# Uniqueness — no label collision across ALL_NODE_TYPES
# ---------------------------------------------------------------------------


def test_all_node_types_unique() -> None:
    labels = list(schema.ALL_NODE_TYPES)
    assert len(labels) == len(set(labels)), "Duplicate label in ALL_NODE_TYPES"


def test_all_edge_types_unique() -> None:
    labels = list(schema.ALL_EDGE_TYPES)
    assert len(labels) == len(set(labels)), "Duplicate label in ALL_EDGE_TYPES"


# ---------------------------------------------------------------------------
# Read-compat invariant (ADR-25 D1 / ADR-26 D9): NODE_VARIABLE must persist
# ---------------------------------------------------------------------------


def test_node_variable_still_exported() -> None:
    assert schema.NODE_VARIABLE == "Variable"


def test_node_variable_still_in_all_node_types() -> None:
    assert schema.NODE_VARIABLE in schema.ALL_NODE_TYPES
