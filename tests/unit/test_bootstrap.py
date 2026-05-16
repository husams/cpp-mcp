"""Smoke tests for project bootstrap — Story 1."""


def test_import_cpp_mcp() -> None:
    import cpp_mcp

    assert cpp_mcp.__version__, "cpp_mcp.__version__ must be a non-empty string"


def test_version_is_string() -> None:
    import cpp_mcp

    assert isinstance(cpp_mcp.__version__, str)
