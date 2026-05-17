"""AC-Q1-4: The indradb_query_executor module must not import or expose
write-surface symbols (no names starting with 'set_' or 'delete_').
"""

from __future__ import annotations

import sys


class TestIndraDbQueryExecutorPurity:
    """AC-Q1-4: module namespace contains no set_* or delete_* symbols."""

    def test_no_write_symbols_in_module_namespace(self) -> None:
        # Import the module (it may not be in sys.modules yet).
        import cpp_mcp.graphdb.indradb_query_executor as m

        write_names = [
            name
            for name in dir(m)
            if name.startswith(("set_", "delete_"))
        ]
        assert not write_names, (
            f"indradb_query_executor exposes write-surface symbols: {write_names}. "
            "This violates AC-Q1-4 read-only purity requirement."
        )

    def test_module_is_importable_without_indradb_installed(self) -> None:
        """The module must be importable without the optional 'indradb' package."""
        # Temporarily hide indradb if present.
        original = sys.modules.pop("indradb", None)
        try:
            # Remove cached module to force re-evaluation of top-level imports.
            cached = sys.modules.pop("cpp_mcp.graphdb.indradb_query_executor", None)
            import cpp_mcp.graphdb.indradb_query_executor  # noqa: F401 — import is the test

            # Restore module state.
            sys.modules["cpp_mcp.graphdb.indradb_query_executor"] = (
                cached
                or sys.modules["cpp_mcp.graphdb.indradb_query_executor"]
            )
        finally:
            if original is not None:
                sys.modules["indradb"] = original
            elif "indradb" in sys.modules:
                del sys.modules["indradb"]
