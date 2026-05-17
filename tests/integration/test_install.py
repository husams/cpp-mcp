"""Integration tests verifying that the graphdb-indradb extra can be imported.

These tests require the graphdb-indradb extra to be installed:
    uv sync --extra graphdb-indradb

They do NOT require a running IndraDB daemon.
"""

import pytest


@pytest.mark.integration
def test_import_indradb() -> None:
    """indradb package is importable when the graphdb-indradb extra is installed."""
    import indradb  # noqa: F401


@pytest.mark.integration
def test_import_indradb_driver() -> None:
    """cpp_mcp.graphdb.indradb_driver is importable with the extra installed."""
    import cpp_mcp.graphdb.indradb_driver  # noqa: F401
