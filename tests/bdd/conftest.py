"""BDD test fixtures and shared steps for Story 5 navigation tools.

Architecture:
  - ``tmp_allowed_root`` fixture creates a temp directory set as the allowed root.
  - ``translate(path)`` maps a scenario path string to a tmp_path equivalent.
  - ``ctx`` (request-scoped) holds per-scenario state shared across steps.
  - ``session`` fixture provides a ClangSession (skipped when libclang absent).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# libclang availability guard
# ---------------------------------------------------------------------------

_LIBCLANG_AVAILABLE = False
try:
    import clang.cindex as _ci

    _ci.Index.create()
    _LIBCLANG_AVAILABLE = True
except Exception:
    pass

requires_libclang = pytest.mark.skipif(
    not _LIBCLANG_AVAILABLE,
    reason="libclang not available on this host",
)

# ---------------------------------------------------------------------------
# Source fixtures directory
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "cpp"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_allowed_root(tmp_path: Path) -> Path:
    """Create a temp directory that acts as the allowed root."""
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture()
def allowed_roots(tmp_allowed_root: Path) -> tuple[str, ...]:
    """Return the allowed roots tuple for path validation."""
    return (str(tmp_allowed_root),)


@pytest.fixture()
def default_flags() -> tuple[str, ...]:
    """Default compiler flags for tests."""
    return ("-std=c++17", "-I.", "-x", "c++")


@pytest.fixture()
def clang_session(tmp_allowed_root: Path) -> Any:
    """Return a ClangSession; skip if libclang is not available."""
    if not _LIBCLANG_AVAILABLE:
        pytest.skip("libclang not available")
    from cpp_mcp.core.clang_session import ClangSession

    return ClangSession(capacity=4)


@pytest.fixture()
def ctx() -> dict[str, Any]:
    """Per-scenario mutable state bag for sharing between steps."""
    return {}


# ---------------------------------------------------------------------------
# Helper: copy a fixture file to tmp_allowed_root
# ---------------------------------------------------------------------------


def copy_fixture(name: str, root: Path) -> Path:
    """Copy ``tests/fixtures/cpp/<name>`` into *root* and return the dest path."""
    src = _FIXTURES_DIR / name
    if not src.exists():
        raise FileNotFoundError(f"Fixture not found: {src}")
    dst = root / name
    shutil.copy2(str(src), str(dst))
    return dst


# ---------------------------------------------------------------------------
# Shared step helpers (imported by per-feature step files)
# ---------------------------------------------------------------------------


def make_nonexistent_path(root: Path) -> str:
    """Return a path inside *root* that does not exist."""
    return str(root / f"nonexistent_{uuid.uuid4().hex}.cpp")
