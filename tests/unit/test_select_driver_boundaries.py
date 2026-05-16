"""Boundary / parametrised tests for select_driver and _normalise_prop (QA addition).

Covers URI edge cases not exercised by test_driver_dispatch.py:
  - Uppercase scheme letters (RFC 3986 §3.1: scheme is case-insensitive);
    urlparse normalises to lowercase, so BOLT://... must dispatch to Neo4jDriver.
  - IPv6 host form (bolt://[::1]:7687).
  - Trailing slash on authority (bolt://localhost:7687/).
  - Port-only omission — IndraDB default port 27615 is applied.
  - Scheme-only with no authority — unknown scheme → InvalidArgumentError.
  - Multiple consecutive delimiters or malformed '://' variants.

Also covers _normalise_prop type boundaries (ADR-15):
  - Scalars (bool, None, int, float, str) pass through unchanged.
  - list and tuple are JSON-encoded (non-scalar).
  - Empty dict and nested dict JSON-encode correctly.
  - Circular-reference falls back to repr() without raising.

Scenario-IDs: US-G3/AC-1, US-G3/AC-2, US-G2/AC-6 (ADR-15 ADR-14)
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

import tests.fixtures.fake_indradb as _fake_indradb_module
from cpp_mcp.core.error_envelope import InvalidArgumentError
from cpp_mcp.graphdb import select_driver
from cpp_mcp.graphdb.indradb_driver import _normalise_prop
from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_indradb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the fake indradb shim in sys.modules so IndraDBDriver can be instantiated."""
    fake_mod = types.ModuleType("indradb")
    fake_mod.Client = _fake_indradb_module.Client  # type: ignore[attr-defined]
    fake_mod.Vertex = _fake_indradb_module.Vertex  # type: ignore[attr-defined]
    fake_mod.Edge = _fake_indradb_module.Edge  # type: ignore[attr-defined]
    fake_mod.Identifier = _fake_indradb_module.Identifier  # type: ignore[attr-defined]
    fake_mod.SpecificVertexQuery = _fake_indradb_module.SpecificVertexQuery  # type: ignore[attr-defined]
    fake_mod.SpecificEdgeQuery = _fake_indradb_module.SpecificEdgeQuery  # type: ignore[attr-defined]
    fake_mod.BulkInserter = _fake_indradb_module.BulkInserter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "indradb", fake_mod)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# US-G3/AC-1 — uppercase scheme letters map to correct driver
# RFC 3986 §3.1 specifies scheme is case-insensitive; urlparse normalises.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "BOLT://localhost:7687",
        "Bolt://localhost:7687",
        "BOLT+S://localhost:7687",
        "NEO4J://localhost:7687",
        "Neo4j+s://localhost:7687",
    ],
)
def test_uppercase_neo4j_scheme_dispatches_to_neo4j_driver(uri: str) -> None:
    """Uppercase Neo4j URI schemes must dispatch to Neo4jDriver (RFC 3986 §3.1).

    Scenario-ID: US-G3/AC-1
    """
    driver = select_driver(uri)
    assert isinstance(driver, Neo4jDriver), (
        f"Expected Neo4jDriver for uppercase URI {uri!r}, got {type(driver).__name__}"
    )


@pytest.mark.parametrize(
    "uri",
    [
        "INDRADB://localhost:27615",
        "GRPC://localhost:27615",
        "Indradb+Grpc://localhost:27615",
    ],
)
def test_uppercase_indradb_scheme_dispatches_to_indradb_driver(
    uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uppercase IndraDB URI schemes must dispatch to IndraDBDriver (RFC 3986 §3.1).

    Scenario-ID: US-G3/AC-1
    select_driver must not import the indradb package (no I/O).

    Note: IndraDBDriver is imported fresh here to avoid isinstance failures when
    test_indradb_driver.py calls importlib.reload on the same module in the same
    pytest session, which creates a new class identity.
    """
    import importlib

    import cpp_mcp.graphdb.indradb_driver as drv_mod

    importlib.reload(drv_mod)
    _install_fake_indradb(monkeypatch)
    driver = select_driver(uri)
    IndraDBDriver = drv_mod.IndraDBDriver
    assert isinstance(driver, IndraDBDriver), (
        f"Expected IndraDBDriver for uppercase URI {uri!r}, got {type(driver).__name__}"
    )


# ---------------------------------------------------------------------------
# US-G3/AC-1 — IPv6 host and trailing-slash variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "bolt://[::1]:7687",
        "bolt://[::1]:7687/",
        "neo4j+s://[2001:db8::1]:7687",
    ],
)
def test_ipv6_neo4j_uri_dispatches_to_neo4j_driver(uri: str) -> None:
    """IPv6 host addresses in Neo4j URIs must dispatch to Neo4jDriver.

    Scenario-ID: US-G3/AC-1
    """
    driver = select_driver(uri)
    assert isinstance(driver, Neo4jDriver), (
        f"Expected Neo4jDriver for IPv6 URI {uri!r}, got {type(driver).__name__}"
    )


def test_neo4j_uri_with_trailing_slash_dispatches_correctly() -> None:
    """Trailing slash on authority component must not prevent Neo4j dispatch.

    Scenario-ID: US-G3/AC-1
    """
    driver = select_driver("bolt+ssc://localhost:7687/")
    assert isinstance(driver, Neo4jDriver)


# ---------------------------------------------------------------------------
# US-G3/AC-2 — Boundary: unknown scheme variants raise InvalidArgumentError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "bolt+extra+ssc://localhost",  # three-segment scheme not in table
        "MYSQL://localhost:3306",  # unknown scheme, even in uppercase
        "ftp://localhost",  # common but unsupported
        "://localhost",  # empty scheme with delimiter present
    ],
)
def test_unknown_or_malformed_scheme_raises_invalid_argument(uri: str) -> None:
    """Unknown and unrecognised URI schemes must raise InvalidArgumentError.

    Scenario-ID: US-G3/AC-2
    """
    with pytest.raises(InvalidArgumentError):
        select_driver(uri)


# ---------------------------------------------------------------------------
# US-G3/AC-1 — IndraDB default port: _strip_scheme applies 27615 when absent
# This exercises IndraDBDriver.connect side-effect through the driver layer.
# ---------------------------------------------------------------------------


def test_indradb_uri_without_port_uses_default_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IndraDB URI with no port number must default to 27615.

    Verifies _strip_scheme host:port composition (ADR-14).
    Scenario-ID: US-G2/AC-2
    """
    import importlib

    import cpp_mcp.graphdb.indradb_driver as drv_mod

    importlib.reload(drv_mod)
    _install_fake_indradb(monkeypatch)
    driver = select_driver("indradb://localhost")
    IndraDBDriver = drv_mod.IndraDBDriver
    assert isinstance(driver, IndraDBDriver)
    driver.connect("indradb://localhost")
    assert driver._client is not None
    assert driver._client.host == "localhost:27615", (  # type: ignore[union-attr]
        f"Default port 27615 must be applied; got {driver._client.host!r}"  # type: ignore[union-attr]
    )
    driver.close()


# ---------------------------------------------------------------------------
# ADR-15 — _normalise_prop: scalar pass-through and non-scalar encoding
# Scenario-ID: US-G2/AC-6
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,value,expected_type",
    [
        ("flag_true", True, bool),
        ("flag_false", False, bool),
        ("none_val", None, type(None)),
        ("int_val", 42, int),
        ("neg_int", -100, int),
        ("float_val", 3.14, float),
        ("zero_float", 0.0, float),
        ("str_val", "hello", str),
        ("empty_str", "", str),
    ],
)
def test_normalise_prop_scalars_pass_through_unchanged(
    key: str, value: Any, expected_type: type
) -> None:
    """All JSON scalar types must be returned unchanged by _normalise_prop (ADR-15).

    Scenario-ID: US-G2/AC-6 (ADR-15)
    """
    result = _normalise_prop(key, value)
    assert result == value, f"Expected value {value!r} unchanged, got {result!r}"
    assert isinstance(result, expected_type), (
        f"Expected type {expected_type.__name__}, got {type(result).__name__}"
    )


@pytest.mark.parametrize(
    "key,value,expected_json_fragment",
    [
        ("list_val", [1, 2, 3], "[1, 2, 3]"),
        ("tuple_val", (10, 20), "[10, 20]"),
        ("empty_list", [], "[]"),
        ("empty_dict", {}, "{}"),
        ("nested_dict", {"a": {"b": 1}}, '{"a": {"b": 1}}'),
        ("sorted_keys", {"z": 1, "a": 2}, '{"a": 2, "z": 1}'),  # sort_keys=True
    ],
)
def test_normalise_prop_non_scalars_are_json_encoded(
    key: str, value: Any, expected_json_fragment: str
) -> None:
    """Non-scalar types must be JSON-encoded to a string by _normalise_prop (ADR-15).

    sort_keys=True is verified for dict inputs to ensure deterministic serialisation.
    Scenario-ID: US-G2/AC-6 (ADR-15)
    """
    result = _normalise_prop(key, value)
    result_type = type(result).__name__
    assert isinstance(result, str), (
        f"Non-scalar {type(value).__name__} must be JSON-encoded to str, got {result_type}"
    )
    assert result == expected_json_fragment, (
        f"Expected JSON fragment {expected_json_fragment!r}, got {result!r}"
    )


def test_normalise_prop_circular_reference_returns_string_not_raises() -> None:
    """A circular-reference dict must not raise; _normalise_prop returns repr() (ADR-15).

    Scenario-ID: US-G2/AC-6 (ADR-15)
    """
    d: dict[str, Any] = {}
    d["self"] = d
    result = _normalise_prop("circular", d)
    assert isinstance(result, str), (
        "Circular-reference prop must fall back to a string (repr()), not raise"
    )
    # The result should contain something recognisable from the dict repr
    assert "self" in result or "{" in result, (
        f"repr() output expected to contain dict-like content; got {result!r}"
    )


def test_normalise_prop_sort_keys_produces_deterministic_output() -> None:
    """Dict serialisation must be deterministic (sort_keys=True) per ADR-15.

    Scenario-ID: US-G2/AC-6 (ADR-15)
    """
    import json

    value = {"z": 3, "a": 1, "m": 2}
    result = _normalise_prop("props", value)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed == value
    # Verify sort_keys produces consistent ordering across multiple calls
    result_2 = _normalise_prop("props", value)
    assert result == result_2, "Serialisation must be deterministic"
