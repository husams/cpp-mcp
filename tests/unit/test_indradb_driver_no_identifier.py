"""Structural grep test: indradb_driver.py must not reference indradb.Identifier.

Runs without the ``indradb`` package installed — pure source-text assertion.
Covers AC-5-1 and AC-5-2 (US-V4-5, S1).
"""

import pathlib

_DRIVER_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "cpp_mcp"
    / "graphdb"
    / "indradb_driver.py"
)


def test_no_indradb_identifier_in_driver_source() -> None:
    """indradb.Identifier must not appear anywhere in the driver source."""
    source = _DRIVER_PATH.read_text(encoding="utf-8")
    assert "indradb.Identifier" not in source, (
        f"Found 'indradb.Identifier' in {_DRIVER_PATH}; "
        "the Identifier wrapper was removed in v4-S1 — use plain str labels."
    )


def test_docstring_does_not_mention_identifier_wrapper() -> None:
    """Module docstring must not mention Identifier(...) on any line."""
    source = _DRIVER_PATH.read_text(encoding="utf-8")
    # Extract module docstring (first triple-quoted block)
    start = source.find('"""')
    end = source.find('"""', start + 3)
    docstring = source[start : end + 3]
    assert "Identifier(" not in docstring, (
        f"Module docstring in {_DRIVER_PATH} still references Identifier(...). "
        "Update to plain str labels per v4-S1."
    )
