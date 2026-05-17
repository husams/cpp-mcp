"""S1: Verify that extract_nodes_and_edges stamps schema_version on every File node.

ADR-24: every File node written by the exporter must carry
``props["schema_version"] == SCHEMA_VERSION``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from cpp_mcp.graphdb.exporter import extract_nodes_and_edges
from cpp_mcp.graphdb.schema import NODE_FILE
from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Fake TU helpers
# ---------------------------------------------------------------------------


def _make_cursor(
    *,
    kind_name: str,
    usr: str,
    spelling: str,
    file_name: str | None = None,
    is_definition: bool = True,
    children: list[Any] | None = None,
) -> Any:
    cursor = MagicMock()
    cursor.kind.name = kind_name
    cursor.get_usr.return_value = usr
    cursor.spelling = spelling
    cursor.is_definition.return_value = is_definition
    cursor.type.spelling = ""
    if file_name is not None:
        cursor.location.file = MagicMock()
        cursor.location.file.name = file_name
    else:
        cursor.location.file = None
    cursor.location.line = 1
    cursor.location.column = 1
    cursor.get_children.return_value = children or []
    cursor.referenced = None
    return cursor


def _make_tu(file_path: Path, *, extra_children: list[Any] | None = None) -> Any:
    """Return a minimal fake TranslationUnit with one function cursor."""
    tu = MagicMock()
    tu.diagnostics = []

    func_cursor = _make_cursor(
        kind_name="FUNCTION_DECL",
        usr="c:@F@hello",
        spelling="hello",
        file_name=str(file_path),
        is_definition=True,
    )

    children: list[Any] = [func_cursor] + (extra_children or [])
    tu.cursor.get_children.return_value = children
    tu.cursor.location.file = None
    tu.cursor.kind.name = "TRANSLATION_UNIT"
    tu.cursor.get_usr.return_value = ""
    tu.cursor.spelling = ""
    tu.cursor.is_definition.return_value = False
    return tu


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchemaVersionStamp:
    """Every File node emitted by extract_nodes_and_edges must carry schema_version."""

    def test_primary_file_node_has_schema_version(self, tmp_path: Path) -> None:
        """The File node for the parsed file itself carries schema_version."""
        source = tmp_path / "hello.cpp"
        source.write_text("void hello() {}")

        tu = _make_tu(source)
        nodes, _ = extract_nodes_and_edges(tu, source)

        file_nodes = [
            n for n in nodes if n["label"] == NODE_FILE and n["props"].get("path") == str(source)
        ]
        assert file_nodes, "No File node found for the source file"
        assert file_nodes[0]["props"].get("schema_version") == SCHEMA_VERSION, (
            f"Expected schema_version={SCHEMA_VERSION!r}, "
            f"got {file_nodes[0]['props'].get('schema_version')!r}"
        )

    def test_included_file_node_has_schema_version(self, tmp_path: Path) -> None:
        """File nodes created for #include directives also carry schema_version."""
        source = tmp_path / "main.cpp"
        source.write_text("")
        inc_path = str(tmp_path / "util.h")

        # Build a fake INCLUSION_DIRECTIVE cursor
        inc_file_mock = MagicMock()
        inc_file_mock.name = inc_path

        inc_cursor = MagicMock()
        inc_cursor.kind.name = "INCLUSION_DIRECTIVE"
        inc_cursor.get_included_file.return_value = inc_file_mock
        inc_cursor.location.file = MagicMock()
        inc_cursor.location.file.name = str(source)
        inc_cursor.location.line = 1
        inc_cursor.location.column = 1
        inc_cursor.get_usr.return_value = ""
        inc_cursor.spelling = ""
        inc_cursor.get_children.return_value = []

        tu = MagicMock()
        tu.diagnostics = []
        tu.cursor.get_children.return_value = [inc_cursor]
        tu.cursor.location.file = None
        tu.cursor.kind.name = "TRANSLATION_UNIT"
        tu.cursor.get_usr.return_value = ""
        tu.cursor.spelling = ""
        tu.cursor.is_definition.return_value = False

        nodes, _ = extract_nodes_and_edges(tu, source)

        inc_file_nodes = [
            n for n in nodes if n["label"] == NODE_FILE and n["props"].get("path") == inc_path
        ]
        assert inc_file_nodes, "No File node found for included file"
        assert inc_file_nodes[0]["props"].get("schema_version") == SCHEMA_VERSION, (
            f"Included File node missing schema_version={SCHEMA_VERSION!r}, "
            f"got {inc_file_nodes[0]['props'].get('schema_version')!r}"
        )

    def test_all_file_nodes_have_schema_version(self, tmp_path: Path) -> None:
        """All File nodes (primary + includes) carry schema_version."""
        source = tmp_path / "all.cpp"
        source.write_text("")

        tu = _make_tu(source)
        nodes, _ = extract_nodes_and_edges(tu, source)

        file_nodes = [n for n in nodes if n["label"] == NODE_FILE]
        assert file_nodes, "Expected at least one File node"
        for node in file_nodes:
            assert node["props"].get("schema_version") == SCHEMA_VERSION, (
                f"File node {node['usr']!r} missing schema_version: {node['props']!r}"
            )

    def test_schema_version_constant_value(self) -> None:
        """SCHEMA_VERSION is the string 'v1'."""
        assert SCHEMA_VERSION == "v1"
