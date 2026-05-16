"""Schema parity test: FastMCP-generated input schemas must match frozen v1 baselines.

Story S5 / US-M4/AC-2..4 / SC_USM4_2/5/6
ADR-6 (v2): schemas moved to tests/fixtures/expected_schemas/

The test builds the server (no transport), fetches live schemas via FastMCP's public
API, normalises both sides with _normalize(), and asserts structural equivalence.

Normalisation rules applied to both sides before comparison:
  N1. Strip "title" from every property dict.
  N2. Collapse Optional types: anyOf:[{type:X},{type:null}] and type:["X","null"]
      both become {"optional": True, "inner_type": X}.
  N3. Replace property description with a boolean (present and non-empty) so minor
      wording changes outside tests/fixtures/ do not cause false failures.
      (The description-presence assertion is separate from the content check.)
  N4. Sort required lists for stable comparison.
  N5. Drop "default": null entries that FastMCP injects for Optional params
      (v1 schemas did not carry a default key for nullable args without a default).

The parity gate checks (per US-M4/AC-2..4):
  - Equal required sets.
  - Equal property-name sets.
  - Equal type structures (after normalisation).
  - Equal enum values where present (EC-8).
  - Equal minimum constraints where present.
  - additionalProperties is False (EC-7).
  - Every argument has a non-empty description (EC-14).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.fixtures.expected_schemas import EXPECTED

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_prop(prop: dict[str, Any]) -> dict[str, Any]:
    """Return a normalised copy of a single property dict.

    Applies N1, N2, N3, N5 in order.
    """
    out: dict[str, Any] = {}

    # N1: drop title
    for key, val in prop.items():
        if key == "title":
            continue
        out[key] = val

    # N2: collapse anyOf:[{type:X},{type:null}] -> {optional:True, type:X, ...}
    if "anyOf" in out:
        any_of: list[dict[str, Any]] = out.pop("anyOf")
        non_null = [entry for entry in any_of if entry.get("type") != "null"]
        if len(non_null) == 1 and len(any_of) == 2:
            inner = non_null[0]
            out["type"] = inner.get("type")
            out["_optional"] = True
        else:
            # More complex anyOf — keep as-is for explicit comparison.
            out["anyOf"] = any_of

    # Also collapse type:["X","null"] form
    if isinstance(out.get("type"), list):
        type_list: list[str] = out.pop("type")
        non_null_types = [t for t in type_list if t != "null"]
        if len(non_null_types) == 1 and len(type_list) == 2:
            out["type"] = non_null_types[0]
            out["_optional"] = True
        else:
            out["type"] = type_list

    # N3: replace description value with a boolean (present & non-empty)
    if "description" in out:
        desc = out["description"]
        out["_has_description"] = bool(desc and str(desc).strip())
        del out["description"]

    # N5: drop default:null (FastMCP injects for Optional params)
    if out.get("default") is None and out.get("_optional"):
        out.pop("default", None)

    return out


def _normalize(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a normalised copy of a full tool input schema."""
    out: dict[str, Any] = {}

    for key, val in schema.items():
        if key == "properties":
            out["properties"] = {
                prop_name: _normalize_prop(prop_val) for prop_name, prop_val in val.items()
            }
        elif key == "required":
            out["required"] = sorted(val)
        else:
            out[key] = val

    return out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live_schemas() -> dict[str, dict[str, Any]]:
    """Build server and return {tool_name: inputSchema} for all registered tools."""
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    tools = asyncio.run(mcp.list_tools())
    return {t.name: t.to_mcp_tool().inputSchema for t in tools}


# ---------------------------------------------------------------------------
# Parity tests
# ---------------------------------------------------------------------------


TOOL_NAMES = list(EXPECTED.keys())


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_schema_required_sets_match(
    live_schemas: dict[str, dict[str, Any]], tool_name: str
) -> None:
    """US-M4/AC-2 — required field sets must be equal. SC_USM4_2."""
    live = live_schemas[tool_name]
    expected = EXPECTED[tool_name]
    assert set(live.get("required", [])) == set(expected.get("required", [])), (
        f"{tool_name}: required mismatch\n"
        f"  live:     {sorted(live.get('required', []))}\n"
        f"  expected: {sorted(expected.get('required', []))}"
    )


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_schema_property_names_match(
    live_schemas: dict[str, dict[str, Any]], tool_name: str
) -> None:
    """US-M4/AC-2 — property name sets must be equal. SC_USM4_5."""
    live_props = set(live_schemas[tool_name].get("properties", {}).keys())
    expected_props = set(EXPECTED[tool_name].get("properties", {}).keys())
    assert live_props == expected_props, (
        f"{tool_name}: property name mismatch\n"
        f"  missing in live: {expected_props - live_props}\n"
        f"  extra in live:   {live_props - expected_props}"
    )


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_schema_property_types_match(
    live_schemas: dict[str, dict[str, Any]], tool_name: str
) -> None:
    """US-M4/AC-2 — normalised property types must match. SC_USM4_2."""
    live_props: dict[str, Any] = live_schemas[tool_name].get("properties", {})
    expected_props: dict[str, Any] = EXPECTED[tool_name].get("properties", {})
    for prop_name in expected_props:
        if prop_name not in live_props:
            continue  # name-set mismatch caught by the previous test
        live_n = _normalize_prop(live_props[prop_name])
        expected_n = _normalize_prop(expected_props[prop_name])
        # Compare type, _optional, enum, minimum (exclude description keys)
        keys_to_compare = {"type", "_optional", "enum", "minimum"}
        for k in keys_to_compare:
            assert live_n.get(k) == expected_n.get(k), (
                f"{tool_name}.{prop_name}: field {k!r} mismatch\n"
                f"  live:     {live_n.get(k)!r}\n"
                f"  expected: {expected_n.get(k)!r}"
            )


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_schema_additional_properties_false(
    live_schemas: dict[str, dict[str, Any]], tool_name: str
) -> None:
    """EC-7 — additionalProperties must be False. SC_USM4_6."""
    live = live_schemas[tool_name]
    assert live.get("additionalProperties") is False, (
        f"{tool_name}: expected additionalProperties=False, got "
        f"{live.get('additionalProperties')!r}"
    )


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_schema_all_properties_have_descriptions(
    live_schemas: dict[str, dict[str, Any]], tool_name: str
) -> None:
    """EC-14 / US-M4/AC-4 — every argument must have a non-empty description. SC_USM4_5."""
    live_props: dict[str, Any] = live_schemas[tool_name].get("properties", {})
    for prop_name, prop in live_props.items():
        desc = prop.get("description", "")
        assert desc and str(desc).strip(), f"{tool_name}.{prop_name}: missing or empty description"
