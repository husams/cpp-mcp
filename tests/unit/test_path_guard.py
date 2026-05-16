"""Tests for cpp_mcp.core.path_guard.

Covers:
- Literal ``..`` segment rejection.
- Symlink escape via tmp_path fixture.
- Allowed-root pass (path inside root).
- Outside-allowed-root rejection.
- Missing file → FileNotFoundError.
- kind="dir" with a file → InvalidArgumentError.
- Empty raw path → PathViolationError.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cpp_mcp.core.error_envelope import InvalidArgumentError, PathViolationError
from cpp_mcp.core.path_guard import validate_path

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def allowed_root(tmp_path: Path) -> Path:
    """A temporary directory that acts as the sole allowed root."""
    root = tmp_path / "allowed"
    root.mkdir()
    return root


@pytest.fixture()
def outside_dir(tmp_path: Path) -> Path:
    """A temporary directory outside the allowed root."""
    out = tmp_path / "outside"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Literal .. rejection
# ---------------------------------------------------------------------------


def test_dotdot_in_path_raises_path_violation(allowed_root: Path) -> None:
    raw = str(allowed_root / ".." / "something")
    with pytest.raises(PathViolationError, match=r"'\.\.'"):
        validate_path(raw, (str(allowed_root),))


def test_dotdot_only_raises_path_violation(allowed_root: Path) -> None:
    with pytest.raises(PathViolationError, match=r"'\.\.'"):
        validate_path("..", (str(allowed_root),))


def test_dotdot_in_middle_segment_raises(allowed_root: Path) -> None:
    raw = str(allowed_root / "foo" / ".." / "bar")
    with pytest.raises(PathViolationError, match=r"'\.\.'"):
        validate_path(raw, (str(allowed_root),))


def test_filename_with_double_dots_not_rejected(allowed_root: Path) -> None:
    """A filename like 'foo..bar' is NOT a traversal segment and should pass."""
    target = allowed_root / "foo..bar"
    target.write_text("data")
    result = validate_path(str(target), (str(allowed_root),))
    assert result == target.resolve()


# ---------------------------------------------------------------------------
# Symlink escape
# ---------------------------------------------------------------------------


def test_symlink_resolving_inside_root_is_allowed(allowed_root: Path, tmp_path: Path) -> None:
    """A symlink whose target is inside the allowed root is accepted."""
    real_file = allowed_root / "real.cpp"
    real_file.write_text("int main() {}")
    link = allowed_root / "link.cpp"
    link.symlink_to(real_file)

    result = validate_path(str(link), (str(allowed_root),))
    assert result == real_file.resolve()


def test_symlink_escaping_root_raises_path_violation(allowed_root: Path, outside_dir: Path) -> None:
    """A symlink pointing outside the allowed root triggers PATH_VIOLATION."""
    secret = outside_dir / "secret.cpp"
    secret.write_text("// secret")
    link = allowed_root / "escape.cpp"
    link.symlink_to(secret)

    with pytest.raises(PathViolationError):
        validate_path(str(link), (str(allowed_root),))


def test_chained_symlink_escape_raises(allowed_root: Path, outside_dir: Path) -> None:
    """Chained symlinks that ultimately escape the root are rejected."""
    secret = outside_dir / "secret2.cpp"
    secret.write_text("// secret")
    intermediate = allowed_root / "hop.cpp"
    intermediate.symlink_to(secret)
    # Second link inside root points to the intermediate which escapes.
    link2 = allowed_root / "chain.cpp"
    link2.symlink_to(intermediate)

    with pytest.raises(PathViolationError):
        validate_path(str(link2), (str(allowed_root),))


# ---------------------------------------------------------------------------
# Allowed root pass
# ---------------------------------------------------------------------------


def test_valid_path_inside_root_returns_resolved(allowed_root: Path) -> None:
    target = allowed_root / "main.cpp"
    target.write_text("int main() {}")
    result = validate_path(str(target), (str(allowed_root),))
    assert result == target.resolve()
    assert result.is_absolute()


def test_path_equal_to_root_itself(allowed_root: Path) -> None:
    """The allowed root directory itself is a valid path when kind='dir'."""
    result = validate_path(str(allowed_root), (str(allowed_root),), kind="dir")
    assert result == allowed_root.resolve()


# ---------------------------------------------------------------------------
# Multiple allowed roots
# ---------------------------------------------------------------------------


def test_path_in_second_root_is_allowed(tmp_path: Path) -> None:
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    target = root2 / "file.cpp"
    target.write_text("// ok")
    result = validate_path(str(target), (str(root1), str(root2)))
    assert result == target.resolve()


def test_path_outside_all_roots_raises(tmp_path: Path) -> None:
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    outside = tmp_path / "outside"
    root1.mkdir()
    root2.mkdir()
    outside.mkdir()
    target = outside / "file.cpp"
    target.write_text("// bad")
    with pytest.raises(PathViolationError):
        validate_path(str(target), (str(root1), str(root2)))


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


def test_nonexistent_path_raises_file_not_found(allowed_root: Path) -> None:
    raw = str(allowed_root / "nonexistent.cpp")
    with pytest.raises(FileNotFoundError):
        validate_path(raw, (str(allowed_root),))


# ---------------------------------------------------------------------------
# kind="dir" — build_path is a file
# ---------------------------------------------------------------------------


def test_kind_dir_on_regular_file_raises_invalid_argument(
    allowed_root: Path,
) -> None:
    """kind='dir' must raise InvalidArgumentError when path is a regular file."""
    f = allowed_root / "compile_commands.json"
    f.write_text("{}")
    with pytest.raises(InvalidArgumentError, match="directory"):
        validate_path(str(f), (str(allowed_root),), kind="dir")


def test_kind_dir_on_directory_succeeds(allowed_root: Path) -> None:
    sub = allowed_root / "build"
    sub.mkdir()
    result = validate_path(str(sub), (str(allowed_root),), kind="dir")
    assert result == sub.resolve()


def test_kind_file_default_on_directory_succeeds(allowed_root: Path) -> None:
    """kind='file' (default) does NOT reject directories — that is path_guard's concern."""
    sub = allowed_root / "subdir"
    sub.mkdir()
    # kind="file" only checks allowed roots; compile_db cares about is_file.
    result = validate_path(str(sub), (str(allowed_root),), kind="file")
    assert result.is_dir()


# ---------------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------------


def test_empty_path_raises_path_violation(allowed_root: Path) -> None:
    with pytest.raises(PathViolationError):
        validate_path("", (str(allowed_root),))


# ---------------------------------------------------------------------------
# config.py — ConfigError on missing ALLOWED_ROOTS
# ---------------------------------------------------------------------------


def test_load_config_raises_on_missing_allowed_roots() -> None:
    from cpp_mcp.core.error_envelope import ConfigError
    from cpp_mcp.server.config import load_config

    with pytest.raises(ConfigError, match="CPP_MCP_ALLOWED_ROOTS is required"):
        load_config(env={})


def test_load_config_raises_on_non_absolute_root(tmp_path: Path) -> None:
    from cpp_mcp.core.error_envelope import ConfigError
    from cpp_mcp.server.config import load_config

    with pytest.raises(ConfigError, match="not absolute"):
        load_config(env={"CPP_MCP_ALLOWED_ROOTS": "relative/path"})


def test_load_config_raises_on_nonexistent_root() -> None:
    from cpp_mcp.core.error_envelope import ConfigError
    from cpp_mcp.server.config import load_config

    with pytest.raises(ConfigError, match="does not exist"):
        load_config(env={"CPP_MCP_ALLOWED_ROOTS": "/this/does/not/exist/at/all"})


def test_load_config_success(tmp_path: Path) -> None:
    from cpp_mcp.server.config import load_config

    root = tmp_path / "allowed"
    root.mkdir()
    cfg = load_config(env={"CPP_MCP_ALLOWED_ROOTS": str(root)})
    assert cfg.allowed_roots == (str(root),)
    assert cfg.cache_capacity == 128
    assert cfg.ast_max_nodes == 5000
    assert cfg.ast_max_bytes == 1_048_576


def test_load_config_custom_flags(tmp_path: Path) -> None:
    from cpp_mcp.server.config import load_config

    root = tmp_path / "allowed"
    root.mkdir()
    cfg = load_config(
        env={
            "CPP_MCP_ALLOWED_ROOTS": str(root),
            "CPP_MCP_DEFAULT_FLAGS": "-std=c++17 -Wall",
        }
    )
    assert cfg.default_flags == ("-std=c++17", "-Wall")


def test_load_config_multiple_roots(tmp_path: Path) -> None:
    from cpp_mcp.server.config import load_config

    root1 = tmp_path / "r1"
    root2 = tmp_path / "r2"
    root1.mkdir()
    root2.mkdir()
    cfg = load_config(env={"CPP_MCP_ALLOWED_ROOTS": f"{root1}:{root2}"})
    assert set(cfg.allowed_roots) == {str(root1), str(root2)}


def test_load_config_invalid_cache_capacity(tmp_path: Path) -> None:
    from cpp_mcp.core.error_envelope import ConfigError
    from cpp_mcp.server.config import load_config

    root = tmp_path / "allowed"
    root.mkdir()
    with pytest.raises(ConfigError, match="CPP_MCP_CACHE_CAPACITY"):
        load_config(
            env={
                "CPP_MCP_ALLOWED_ROOTS": str(root),
                "CPP_MCP_CACHE_CAPACITY": "abc",
            }
        )


def test_load_config_zero_cache_capacity(tmp_path: Path) -> None:
    from cpp_mcp.core.error_envelope import ConfigError
    from cpp_mcp.server.config import load_config

    root = tmp_path / "allowed"
    root.mkdir()
    with pytest.raises(ConfigError, match="CPP_MCP_CACHE_CAPACITY"):
        load_config(
            env={
                "CPP_MCP_ALLOWED_ROOTS": str(root),
                "CPP_MCP_CACHE_CAPACITY": "0",
            }
        )
