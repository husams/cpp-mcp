"""Test that fastmcp is pinned correctly in pyproject.toml (US-M8/AC-1)."""

import re
import tomllib
from pathlib import Path


def _load_pyproject() -> dict:  # type: ignore[type-arg]
    root = Path(__file__).parent.parent.parent
    with open(root / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_fastmcp_specifier_matches_pin() -> None:
    """fastmcp dependency specifier must match ~=3.1.<patch> (compatible-release on minor)."""
    data = _load_pyproject()
    deps: list[str] = data["project"]["dependencies"]
    fastmcp_entries = [d for d in deps if d.startswith("fastmcp")]
    assert fastmcp_entries, "fastmcp not found in [project].dependencies"
    specifier = fastmcp_entries[0][len("fastmcp") :].strip()
    assert re.match(r"^~=3\.1\.\d+$", specifier), (
        f"fastmcp specifier {specifier!r} does not match ~=3.1.<patch>"
    )
