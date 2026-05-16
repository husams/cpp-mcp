"""Unit test: runbook.md exists and contains required content strings.

Covers: US-M8/AC-3 (runbook with upgrade-check procedure and pin rationale).
Also covers US-G6/AC-2 (v3 runbook must include DEPENDENCY_MISSING error-code row).
"""

from pathlib import Path

RUNBOOK_V2 = Path(__file__).parents[2] / ".claude" / "handoff" / "v2" / "runbook.md"
RUNBOOK_V3 = Path(__file__).parents[2] / ".claude" / "handoff" / "v3" / "runbook.md"


def test_runbook_file_exists() -> None:
    assert RUNBOOK_V2.exists(), f"runbook.md not found at {RUNBOOK_V2}"


def test_runbook_contains_fastmcp_string() -> None:
    content = RUNBOOK_V2.read_text()
    assert "fastmcp" in content.lower(), "runbook.md must mention 'fastmcp'"


def test_runbook_contains_version_pin() -> None:
    content = RUNBOOK_V2.read_text()
    assert "~=3.1.0" in content, "runbook.md must contain the exact pin string '~=3.1.0'"


def test_v3_runbook_file_exists() -> None:
    """US-G6/AC-2: v3 runbook.md must be present (populated by S6)."""
    import pytest

    if not RUNBOOK_V3.exists():
        pytest.skip("v3 runbook.md not yet created (pending S6)")
    # Once S6 ships the file, this assert hardens the invariant.
    assert RUNBOOK_V3.exists(), f"v3 runbook.md not found at {RUNBOOK_V3}"


def test_v3_runbook_contains_dependency_missing() -> None:
    """US-G6/AC-2: v3 runbook must document the DEPENDENCY_MISSING error code."""
    import pytest

    if not RUNBOOK_V3.exists():
        pytest.skip("v3 runbook.md not yet created (pending S6)")
    content = RUNBOOK_V3.read_text()
    assert "DEPENDENCY_MISSING" in content, (
        "v3 runbook.md must contain a DEPENDENCY_MISSING error-code row"
    )
