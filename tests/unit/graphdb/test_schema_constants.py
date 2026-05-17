"""v7-S1: Verify NODE_FIELD, NODE_GLOBAL_VARIABLE constants and ALL_NODE_TYPES membership.

Covers S1-1 AC1 (constant existence — partial) per plan.md P1.
ADR-25 D1: NODE_VARIABLE retained for read-side compat and PARM_DECL (transitional).
"""

from __future__ import annotations

from cpp_mcp.graphdb.schema import (
    ALL_NODE_TYPES,
    NODE_FIELD,
    NODE_GLOBAL_VARIABLE,
    NODE_VARIABLE,
)


class TestSchemaConstants:
    """Schema constant values and membership in ALL_NODE_TYPES (ADR-25 D1)."""

    def test_node_field_value(self) -> None:
        """NODE_FIELD == 'Field'."""
        assert NODE_FIELD == "Field"

    def test_node_global_variable_value(self) -> None:
        """NODE_GLOBAL_VARIABLE == 'GlobalVariable'."""
        assert NODE_GLOBAL_VARIABLE == "GlobalVariable"

    def test_node_field_in_all_node_types(self) -> None:
        """NODE_FIELD appears in ALL_NODE_TYPES."""
        assert NODE_FIELD in ALL_NODE_TYPES

    def test_node_global_variable_in_all_node_types(self) -> None:
        """NODE_GLOBAL_VARIABLE appears in ALL_NODE_TYPES."""
        assert NODE_GLOBAL_VARIABLE in ALL_NODE_TYPES

    def test_node_variable_still_exported(self) -> None:
        """NODE_VARIABLE is still exported from schema (ADR-25 D1 read-compat)."""
        assert NODE_VARIABLE == "Variable"

    def test_node_variable_in_all_node_types(self) -> None:
        """NODE_VARIABLE remains in ALL_NODE_TYPES (ADR-25 D1)."""
        assert NODE_VARIABLE in ALL_NODE_TYPES
