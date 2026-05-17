"""Tests for pyproject.toml optional-dependency extras (US-G4/AC-1..4)."""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent.parent / "pyproject.toml"


def _load_extras() -> dict[str, list[str]]:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["optional-dependencies"]


def test_graphdb_neo4j_extra_exists() -> None:
    extras = _load_extras()
    assert "graphdb-neo4j" in extras, "graphdb-neo4j extra must exist"


def test_graphdb_indradb_extra_exists() -> None:
    extras = _load_extras()
    assert "graphdb-indradb" in extras, "graphdb-indradb extra must exist"


def test_graphdb_meta_extra_exists() -> None:
    extras = _load_extras()
    assert "graphdb" in extras, "graphdb meta-extra must exist"


def test_neo4j_pin() -> None:
    extras = _load_extras()
    assert extras["graphdb-neo4j"] == ["neo4j>=5,<6"], (
        f"graphdb-neo4j must pin to 'neo4j>=5,<6', got {extras['graphdb-neo4j']}"
    )


def test_indradb_pin() -> None:
    extras = _load_extras()
    expected = ["indradb>=3.0,<4", "protobuf<4"]
    got = extras["graphdb-indradb"]
    assert got == expected, f"graphdb-indradb must pin to {expected!r}, got {got!r}"


def test_graphdb_meta_references_neo4j() -> None:
    extras = _load_extras()
    assert "cpp-mcp[graphdb-neo4j]" in extras["graphdb"], (
        "graphdb meta-extra must include cpp-mcp[graphdb-neo4j]"
    )


def test_graphdb_meta_references_indradb() -> None:
    extras = _load_extras()
    assert "cpp-mcp[graphdb-indradb]" in extras["graphdb"], (
        "graphdb meta-extra must include cpp-mcp[graphdb-indradb]"
    )
