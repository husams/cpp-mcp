"""Integration tests for README install-section completeness and driver error wording.

Scenarios:
  SC-V4-7-01 — README contains all three ``uv sync --extra`` install strings.
  SC-V4-7-02 — Both drivers raise DependencyMissingError with the literal
               ``uv sync --extra graphdb-<name>`` flag when the dependency is absent.

AC-IDs satisfied: AC-7-1, AC-7-2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cpp_mcp.core.error_envelope import DependencyMissingError

_REPO_ROOT = Path(__file__).parent.parent.parent
_README = _REPO_ROOT / "README.md"


# ---------------------------------------------------------------------------
# SC-V4-7-01: README install section enumerates all three extras
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReadmeExtrasPresent:
    def test_readme_contains_graphdb_neo4j_extra(self) -> None:
        """README must contain ``uv sync --extra graphdb-neo4j``."""
        text = _README.read_text(encoding="utf-8")
        assert "uv sync --extra graphdb-neo4j" in text, (
            "README.md is missing 'uv sync --extra graphdb-neo4j' in the Install section"
        )

    def test_readme_contains_graphdb_indradb_extra(self) -> None:
        """README must contain ``uv sync --extra graphdb-indradb``."""
        text = _README.read_text(encoding="utf-8")
        assert "uv sync --extra graphdb-indradb" in text, (
            "README.md is missing 'uv sync --extra graphdb-indradb' in the Install section"
        )

    def test_readme_contains_graphdb_meta_extra(self) -> None:
        """README must contain ``uv sync --extra graphdb`` (meta-extra for both backends)."""
        text = _README.read_text(encoding="utf-8")
        assert "uv sync --extra graphdb" in text, (
            "README.md is missing 'uv sync --extra graphdb' in the Install section"
        )


# ---------------------------------------------------------------------------
# SC-V4-7-02: DependencyMissingError messages contain the uv sync --extra flag
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDependencyMissingErrorWording:
    def test_indradb_driver_message_contains_uv_sync_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IndraDBDriver.connect must include 'uv sync --extra graphdb-indradb' in the error."""
        monkeypatch.setitem(sys.modules, "indradb", None)  # type: ignore[arg-type]

        import importlib

        import cpp_mcp.graphdb.indradb_driver as drv_mod

        importlib.reload(drv_mod)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        with pytest.raises(DependencyMissingError, match="uv sync --extra graphdb-indradb"):
            driver.connect("indradb://localhost:27615")

    def test_neo4j_driver_message_contains_uv_sync_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Neo4jDriver.connect must include 'uv sync --extra graphdb-neo4j' in the error."""
        monkeypatch.setitem(sys.modules, "neo4j", None)  # type: ignore[arg-type]

        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver

        driver = Neo4jDriver()
        with pytest.raises(DependencyMissingError, match="uv sync --extra graphdb-neo4j"):
            driver.connect("bolt://localhost:7687")
