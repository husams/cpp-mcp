"""Unit tests for cpp_mcp.core.compile_db.resolve_flags.

Test matrix (plan.md Story 3 / scenarios.md US-9):
  1. build_path=None       → default_flags, source="default"
  2. valid DB hit          → DB flags extracted, source="compilation_db"
  3. file not in DB        → default_flags, source="default"
  4. DB directory empty (no compile_commands.json) → default_flags, source="default"
  5. malformed compile_commands.json → default_flags, source="default"
  6. build_path is a file  → InvalidArgumentError raised
  7. custom default_flags  → returned verbatim when falling back
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpp_mcp.core.compile_db import resolve_flags
from cpp_mcp.core.error_envelope import InvalidArgumentError

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

_DEFAULT = ("-std=c++20", "-I.", "-x", "c++")

# Path to the static fixture directory (used only for notes; actual DB tests use
# tmp_path because libclang resolves file entries by absolute path).
_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "compile_dbs"


# ---------------------------------------------------------------------------
# 1. build_path is None → default flags
# ---------------------------------------------------------------------------


def test_build_path_none_returns_default_flags(tmp_path: Path) -> None:
    """When build_path is None resolve_flags returns default_flags, source='default'."""
    flags, source = resolve_flags(tmp_path / "src.cpp", None, _DEFAULT)
    assert flags == _DEFAULT
    assert source == "default"


# ---------------------------------------------------------------------------
# 2. Valid DB hit → DB flags, source="compilation_db"
# ---------------------------------------------------------------------------


def test_db_hit_returns_db_flags(tmp_path: Path) -> None:
    """File listed in DB → returns its DB flags with source='compilation_db'."""
    src = tmp_path / "main.cpp"
    src.write_text("int main(){}", encoding="utf-8")

    compile_commands = [
        {
            "directory": str(tmp_path),
            "command": f"clang++ -std=c++17 -DDEBUG {src}",
            "file": str(src),
        }
    ]
    db_dir = tmp_path / "build"
    db_dir.mkdir()
    (db_dir / "compile_commands.json").write_text(json.dumps(compile_commands), encoding="utf-8")

    flags, source = resolve_flags(src, db_dir, _DEFAULT)

    assert source == "compilation_db"
    # DB flags exclude the compiler binary and the source filename.
    assert "-std=c++17" in flags
    assert "-DDEBUG" in flags
    # The source filename must NOT appear in the extracted flags.
    assert str(src) not in flags


# ---------------------------------------------------------------------------
# 3. File not listed in DB → default flags, source="default"
# ---------------------------------------------------------------------------


def test_file_not_in_db_returns_default_flags(tmp_path: Path) -> None:
    """File absent from DB → silent fallback to default_flags, source='default'."""
    other_src = tmp_path / "other.cpp"
    other_src.write_text("int x;", encoding="utf-8")

    listed_src = tmp_path / "listed.cpp"
    compile_commands = [
        {
            "directory": str(tmp_path),
            "command": f"clang++ -std=c++17 {listed_src}",
            "file": str(listed_src),
        }
    ]
    db_dir = tmp_path / "build"
    db_dir.mkdir()
    (db_dir / "compile_commands.json").write_text(json.dumps(compile_commands), encoding="utf-8")

    flags, source = resolve_flags(other_src, db_dir, _DEFAULT)
    assert flags == _DEFAULT
    assert source == "default"


# ---------------------------------------------------------------------------
# 4. Empty directory (no compile_commands.json) → default flags
# ---------------------------------------------------------------------------


def test_empty_build_dir_returns_default_flags(tmp_path: Path) -> None:
    """Build directory without compile_commands.json → silent fallback."""
    empty_dir = tmp_path / "empty_build"
    empty_dir.mkdir()

    flags, source = resolve_flags(tmp_path / "src.cpp", empty_dir, _DEFAULT)
    assert flags == _DEFAULT
    assert source == "default"


# ---------------------------------------------------------------------------
# 5. Malformed compile_commands.json → silent fallback to default flags
# ---------------------------------------------------------------------------


def test_malformed_json_returns_default_flags(tmp_path: Path) -> None:
    """Malformed compile_commands.json → log WARN, silent fallback, source='default'."""
    bad_dir = tmp_path / "bad_build"
    bad_dir.mkdir()
    (bad_dir / "compile_commands.json").write_text(
        "{this is not valid JSON at all]", encoding="utf-8"
    )

    flags, source = resolve_flags(tmp_path / "src.cpp", bad_dir, _DEFAULT)
    assert flags == _DEFAULT
    assert source == "default"


# ---------------------------------------------------------------------------
# 6. build_path is a regular file → InvalidArgumentError
# ---------------------------------------------------------------------------


def test_build_path_is_file_raises_invalid_argument(tmp_path: Path) -> None:
    """Existing file passed as build_path → InvalidArgumentError (ADR-9 / OQ-NEW-1)."""
    not_a_dir = tmp_path / "compile_commands.json"
    not_a_dir.write_text("[]", encoding="utf-8")

    with pytest.raises(InvalidArgumentError, match="build_path must be a directory"):
        resolve_flags(tmp_path / "src.cpp", not_a_dir, _DEFAULT)


# ---------------------------------------------------------------------------
# 7. Custom default_flags are returned verbatim on fallback
# ---------------------------------------------------------------------------


def test_custom_default_flags_returned_on_none_build_path(tmp_path: Path) -> None:
    """Custom default_flags tuple is returned intact when build_path=None."""
    custom = ("-std=c++14", "-Wall", "-Wextra")
    flags, source = resolve_flags(tmp_path / "src.cpp", None, custom)
    assert flags == custom
    assert source == "default"


def test_custom_default_flags_returned_on_empty_build_dir(tmp_path: Path) -> None:
    """Custom default_flags tuple is returned intact when DB is absent."""
    custom = ("-std=c++14", "-Wall")
    empty_dir = tmp_path / "build"
    empty_dir.mkdir()

    flags, source = resolve_flags(tmp_path / "src.cpp", empty_dir, custom)
    assert flags == custom
    assert source == "default"


# ---------------------------------------------------------------------------
# Fixture sanity: static malformed fixture matches expected shape
# ---------------------------------------------------------------------------


def test_static_malformed_fixture_is_not_valid_json() -> None:
    """Sanity-check that the static malformed fixture file is indeed invalid JSON."""
    malformed_path = _FIXTURES_DIR / "malformed" / "compile_commands.json"
    assert malformed_path.exists(), f"Static fixture missing: {malformed_path}"
    content = malformed_path.read_text(encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(content)


def test_static_empty_fixture_dir_has_no_compile_commands() -> None:
    """Sanity-check that the static empty fixture directory has no compile_commands.json."""
    empty_dir = _FIXTURES_DIR / "empty"
    assert empty_dir.is_dir(), f"Static empty fixture dir missing: {empty_dir}"
    db_file = empty_dir / "compile_commands.json"
    assert not db_file.exists(), f"Unexpected compile_commands.json in empty fixture: {db_file}"


# ---------------------------------------------------------------------------
# Additional: non-existent build_path directory (does not exist on disk)
# ---------------------------------------------------------------------------


def test_nonexistent_build_path_returns_default_flags(tmp_path: Path) -> None:
    """Non-existent build_path directory → silent fallback (no exception)."""
    ghost_dir = tmp_path / "nonexistent_build"
    assert not ghost_dir.exists()

    flags, source = resolve_flags(tmp_path / "src.cpp", ghost_dir, _DEFAULT)
    assert flags == _DEFAULT
    assert source == "default"


# ---------------------------------------------------------------------------
# os.environ integration note (not a unit test): the compile_db module does
# NOT read any environment variables directly; callers inject default_flags.
# config.py parses CPP_MCP_DEFAULT_FLAGS and passes the result as a tuple.
# ---------------------------------------------------------------------------


def test_resolve_flags_does_not_read_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_flags ignores CPP_MCP_DEFAULT_FLAGS; caller injects flags explicitly."""
    monkeypatch.setenv("CPP_MCP_DEFAULT_FLAGS", "-std=c++11 -O2")
    custom = ("-std=c++20", "-I.")
    flags, _source = resolve_flags(tmp_path / "src.cpp", None, custom)
    # Should return *custom*, not whatever is in the env var.
    assert flags == custom
    assert "-std=c++11" not in flags


# ---------------------------------------------------------------------------
# OS path isolation: resolve_flags uses Path objects from caller
# ---------------------------------------------------------------------------


def test_os_path_resolution(tmp_path: Path) -> None:
    """resolve_flags works with Path objects (not just strings)."""
    src = tmp_path / "src.cpp"
    flags, source = resolve_flags(src, None, _DEFAULT)
    assert isinstance(flags, tuple)
    assert source == "default"
