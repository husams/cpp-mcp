"""Unit tests for select_driver — URI-scheme dispatch (US-G3 / ADR-12).

Covers:
- All 6 Neo4j schemes return Neo4jDriver (US-G3/AC-1).
- All 3 IndraDB schemes return IndraDBDriver (US-G3/AC-1).
- Unknown scheme raises InvalidArgumentError with a message listing supported schemes.
- Empty string raises InvalidArgumentError.
- URI with no '://' separator raises InvalidArgumentError.
- select_driver does no I/O (no package import of neo4j or indradb).
"""

from __future__ import annotations

import sys

import pytest

from cpp_mcp.core.error_envelope import InvalidArgumentError
from cpp_mcp.graphdb import select_driver
from cpp_mcp.graphdb.indradb_driver import IndraDBDriver
from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

# ---------------------------------------------------------------------------
# Neo4j scheme → Neo4jDriver
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "bolt://localhost:7687",
        "bolt+s://localhost:7687",
        "bolt+ssc://localhost:7687",
        "neo4j://localhost:7687",
        "neo4j+s://localhost:7687",
        "neo4j+ssc://localhost:7687",
    ],
)
def test_select_driver_neo4j_schemes_return_neo4j_driver(uri: str) -> None:
    """All bolt/neo4j URI schemes return an unconnected Neo4jDriver."""
    driver = select_driver(uri)
    assert isinstance(driver, Neo4jDriver), f"Expected Neo4jDriver for {uri!r}, got {type(driver)}"


# ---------------------------------------------------------------------------
# IndraDB scheme → IndraDBDriver
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "indradb://localhost:27615",
        "grpc://localhost:27615",
        "indradb+grpc://localhost:27615",
    ],
)
def test_select_driver_indradb_schemes_return_indradb_driver(
    uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All indradb/grpc URI schemes return an unconnected IndraDBDriver.

    The indradb package need not be installed — select_driver must not import it.
    We remove it from sys.modules to confirm no import occurs.
    """
    monkeypatch.setitem(sys.modules, "indradb", None)  # type: ignore[arg-type]
    driver = select_driver(uri)
    assert isinstance(driver, IndraDBDriver), (
        f"Expected IndraDBDriver for {uri!r}, got {type(driver)}"
    )


# ---------------------------------------------------------------------------
# Invalid inputs → InvalidArgumentError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "memgraph://localhost:7687",
        "postgres://localhost/mydb",
        "surrealdb://localhost:8000",
        "mysql://localhost:3306",
        "cognee://my-dataset",  # cognee:// not wired in v3 (ADR-12)
    ],
)
def test_select_driver_unknown_scheme_raises_invalid_argument(uri: str) -> None:
    """Unknown URI schemes raise InvalidArgumentError (maps to INVALID_ARGUMENT)."""
    with pytest.raises(InvalidArgumentError, match="Unsupported"):
        select_driver(uri)


def test_select_driver_unknown_scheme_message_lists_supported() -> None:
    """Error message for unknown scheme includes the list of supported schemes."""
    with pytest.raises(InvalidArgumentError, match="bolt") as exc_info:
        select_driver("clickhouse://localhost")
    assert "indradb" in str(exc_info.value)
    assert "neo4j" in str(exc_info.value)


def test_select_driver_empty_string_raises_invalid_argument() -> None:
    """Empty db_uri raises InvalidArgumentError."""
    with pytest.raises(InvalidArgumentError):
        select_driver("")


def test_select_driver_no_scheme_delimiter_raises_invalid_argument() -> None:
    """URI without '://' separator raises InvalidArgumentError."""
    with pytest.raises(InvalidArgumentError):
        select_driver("localhost:7687")


def test_select_driver_scheme_only_no_slash_slash_raises() -> None:
    """URI that looks like a bare scheme without '//' raises InvalidArgumentError."""
    with pytest.raises(InvalidArgumentError):
        select_driver("bolt:localhost:7687")


# ---------------------------------------------------------------------------
# No I/O — select_driver does not import neo4j or indradb
# ---------------------------------------------------------------------------


def test_select_driver_neo4j_does_not_import_neo4j_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """select_driver('bolt://...') must NOT import the neo4j package.

    The package is placed as None in sys.modules to simulate absence.
    If select_driver tried to import it, an ImportError would be raised.
    """
    # Remove any cached import first.
    monkeypatch.setitem(sys.modules, "neo4j", None)  # type: ignore[arg-type]
    # select_driver should return an instance without touching sys.modules["neo4j"].
    driver = select_driver("bolt://localhost:7687")
    assert isinstance(driver, Neo4jDriver)


def test_select_driver_indradb_does_not_import_indradb_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """select_driver('indradb://...') must NOT import the indradb package."""
    monkeypatch.setitem(sys.modules, "indradb", None)  # type: ignore[arg-type]
    driver = select_driver("indradb://localhost:27615")
    assert isinstance(driver, IndraDBDriver)


# ---------------------------------------------------------------------------
# Returned instances are unconnected (no _driver / _client set)
# ---------------------------------------------------------------------------


def test_select_driver_returns_unconnected_neo4j_driver() -> None:
    """Returned Neo4jDriver has _driver == None (not yet connected)."""
    driver = select_driver("bolt://localhost:7687")
    assert isinstance(driver, Neo4jDriver)
    assert driver._driver is None  # type: ignore[union-attr]


def test_select_driver_returns_unconnected_indradb_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returned IndraDBDriver has _client == None (not yet connected)."""
    monkeypatch.setitem(sys.modules, "indradb", None)  # type: ignore[arg-type]
    driver = select_driver("indradb://localhost:27615")
    assert isinstance(driver, IndraDBDriver)
    assert driver._client is None  # type: ignore[union-attr]
