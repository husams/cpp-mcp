"""Negative (meta) tests for the schema parity test harness itself.

SC_USM4_3: parity test fails when a property is renamed.
SC_USM4_4: parity test fails when a description is empty.

These tests verify that test_schema_parity.py's assertions are sensitive enough
to catch regressions in the tool schemas — i.e., the test cannot silently pass
on a broken schema.

Implementation: call the assertion logic directly with hand-crafted bad schemas
to prove the parity checks raise AssertionError on known-bad inputs.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from tests.fixtures.expected_schemas import EXPECTED
from tests.unit.test_schema_parity import _normalize_prop

# ---------------------------------------------------------------------------
# Helpers — inline assertion logic to avoid importing parametrized tests
# ---------------------------------------------------------------------------


def _assert_property_names_match(live_schemas: dict[str, dict[str, Any]], tool_name: str) -> None:
    """Replicate the property-name assertion from test_schema_parity."""
    live_props = set(live_schemas[tool_name].get("properties", {}).keys())
    expected_props = set(EXPECTED[tool_name].get("properties", {}).keys())
    assert live_props == expected_props, (
        f"{tool_name}: property name mismatch\n"
        f"  missing in live: {expected_props - live_props}\n"
        f"  extra in live:   {live_props - expected_props}"
    )


def _assert_all_properties_have_descriptions(
    live_schemas: dict[str, dict[str, Any]], tool_name: str
) -> None:
    """Replicate the description-presence assertion from test_schema_parity."""
    live_props: dict[str, Any] = live_schemas[tool_name].get("properties", {})
    for prop_name, prop in live_props.items():
        desc = prop.get("description", "")
        assert desc and str(desc).strip(), f"{tool_name}.{prop_name}: missing or empty description"


# ---------------------------------------------------------------------------
# SC_USM4_3 — rename detection
# ---------------------------------------------------------------------------


def test_parity_fails_on_rename() -> None:
    """SC_USM4_3: property rename is detected as a mismatch.

    Injects a renamed property into a fake live schema and asserts that the
    property-name check raises AssertionError.
    """
    original = EXPECTED["get_definition"]
    props = deepcopy(original["properties"])
    props["file"] = props.pop("file_path")  # rename file_path -> file
    fake_live_schemas: dict[str, dict[str, Any]] = {
        "get_definition": {
            **original,
            "properties": props,
        }
    }

    with pytest.raises(AssertionError, match="property name mismatch"):
        _assert_property_names_match(fake_live_schemas, "get_definition")


# ---------------------------------------------------------------------------
# SC_USM4_4 — empty description detection
# ---------------------------------------------------------------------------


def test_parity_fails_on_empty_description() -> None:
    """SC_USM4_4: empty description on any argument is detected.

    Injects a blank description for file_path in a fake live schema and asserts
    that the description-presence check raises AssertionError.
    """
    original = EXPECTED["get_definition"]
    props = deepcopy(original["properties"])
    props["file_path"] = {**props["file_path"], "description": ""}
    fake_live_schemas: dict[str, dict[str, Any]] = {
        "get_definition": {
            **original,
            "properties": props,
        }
    }

    with pytest.raises(AssertionError, match="missing or empty description"):
        _assert_all_properties_have_descriptions(fake_live_schemas, "get_definition")


# ---------------------------------------------------------------------------
# Positive sanity: normaliser correctly handles optional type forms
# ---------------------------------------------------------------------------


def test_normalize_prop_handles_anyof_optional() -> None:
    """_normalize_prop converts anyOf:[str,null] to _optional=True + type='string'."""
    prop: dict[str, Any] = {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": None,
        "description": "some desc",
    }
    result = _normalize_prop(prop)
    assert result.get("_optional") is True
    assert result.get("type") == "string"
    assert "_has_description" in result


def test_normalize_prop_handles_list_type_optional() -> None:
    """_normalize_prop converts type:['string','null'] to _optional=True + type='string'."""
    prop: dict[str, Any] = {
        "type": ["string", "null"],
        "description": "some desc",
    }
    result = _normalize_prop(prop)
    assert result.get("_optional") is True
    assert result.get("type") == "string"
