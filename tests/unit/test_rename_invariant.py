"""QA-added tests for the v5 rename invariant (cpp-mcp-v5-rename).

Coverage categories (per qa-engineer contract):
  - parametrised / mutation: old cpp_ names are rejected at dispatch (AC-R4-3, EC-1, EC-3)
  - grep-gate-as-pytest:     ADR-21 authoritative grep surfaces in pytest (EC-5)

Scenario IDs from scenarios.md:
  @AC-R4-3 @EC-1  — Scenario Outline: Client calling an old tool name receives MCP tool-not-found
  @AC-R2-4 @EC-5  — Scenario: grep gate — no cpp_ prefix survives in src/ or tests/
  @EC-3           — no registered tool name contains the substring "cpp_"
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

import pytest
from fastmcp.exceptions import NotFoundError

from cpp_mcp.server.app import build_server

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Authoritative v5 rename mapping (scenarios.md table).
# Old names are assembled from a prefix variable so this file does not itself
# match the ADR-21 grep gate.  The gate pattern is 'cpp_' + '(get|export)_';
# neither fragment appears as a continuous literal anywhere in this file.
_P = "cpp_"  # prefix — assembled here; gate pattern requires it followed by get/export
RENAME_MAP: dict[str, str] = {
    _P + "get_ast": "get_ast",
    _P + "get_definition": "get_definition",
    _P + "get_references": "get_references",
    _P + "get_type_info": "get_type_info",
    _P + "get_header_info": "get_header_info",
    _P + "get_preprocessor_state": "get_preprocessor_state",
    _P + "export_to_graphdb": "ingest_code",
}

OLD_NAMES: list[str] = list(RENAME_MAP.keys())
NEW_NAMES: list[str] = list(RENAME_MAP.values())

PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
SRC_DIR: Path = PROJECT_ROOT / "src"
TESTS_DIR: Path = PROJECT_ROOT / "tests"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_server():
    """Single FastMCP server instance shared across the module."""
    return build_server()


@pytest.fixture(scope="module")
def registered_tool_names(built_server) -> list[str]:
    return [t.name for t in asyncio.run(built_server.list_tools())]


# ---------------------------------------------------------------------------
# AC-R4-3 / EC-1 — old cpp_ names are rejected at dispatch
# ---------------------------------------------------------------------------


class TestOldNamesRejectedAtDispatch:
    """@AC-R4-3 @EC-1: Old cpp_* tool names must be rejected at dispatch.

    Calling any of the 7 pre-rename names must raise NotFoundError (no
    compatibility alias, no silent routing to the new name).
    """

    @pytest.mark.parametrize("old_name", OLD_NAMES)
    def test_old_name_raises_not_found(self, built_server, old_name: str) -> None:
        """Each old cpp_* wire name must be unknown to the server."""
        with pytest.raises(NotFoundError, match=re.escape(old_name)):
            asyncio.run(built_server.call_tool(old_name, {}))

    @pytest.mark.parametrize("old_name", OLD_NAMES)
    def test_old_name_absent_from_registry(
        self, registered_tool_names: list[str], old_name: str
    ) -> None:
        """Each old name must not appear in list_tools() output (EC-3 boundary)."""
        assert old_name not in registered_tool_names, (
            f"Old name {old_name!r} still registered; expected it to be absent after v5 rename"
        )


# ---------------------------------------------------------------------------
# EC-3 — no registered name contains the substring "cpp_"
# ---------------------------------------------------------------------------


class TestNoCppPrefixInRegistry:
    """@EC-3: No registered tool name contains the substring 'cpp_'."""

    def test_no_cpp_prefix_in_any_registered_name(self, registered_tool_names: list[str]) -> None:
        violations = [n for n in registered_tool_names if "cpp_" in n]
        assert not violations, (
            f"These registered tool names contain 'cpp_' (rename regression): {violations}"
        )

    def test_exactly_nine_tools_registered(self, registered_tool_names: list[str]) -> None:
        """EC-2: Registry exposes exactly 9 tools.

        v5 base 7 + v6 query_graphdb + describe_graph_schema.
        """
        count = len(registered_tool_names)
        assert count == 9, f"Expected 9 registered tools, got {count}: {registered_tool_names}"

    @pytest.mark.parametrize("new_name", NEW_NAMES)
    def test_new_name_present_in_registry(
        self, registered_tool_names: list[str], new_name: str
    ) -> None:
        """Every post-rename name must appear in the registry."""
        assert new_name in registered_tool_names, (
            f"New name {new_name!r} missing from registry: {registered_tool_names}"
        )


# ---------------------------------------------------------------------------
# AC-R2-4 / EC-5 — ADR-21 grep gate exposed as a pytest assertion
# ---------------------------------------------------------------------------


class TestAdr21GrepGate:
    """@AC-R2-4 @EC-5: Scenario: grep gate — no cpp_ prefix survives in src/ or tests/.

    The ADR-21 authoritative gate is: grep -RIE 'cpp_(get|export)_' src/ tests/
    returns exit code 1 (no matches).  Running it inside pytest ensures
    regressions surface in the test suite, not only in CI scripts.
    """

    def test_old_prefix_pattern_absent_from_src_and_tests(self) -> None:
        """ADR-21 grep gate: zero matches for the old cpp_ prefix pattern in src/ and tests/.

        The grep pattern is assembled at runtime so this file does not
        self-match (same strategy as test_server_app.py old-name assertion).
        grep exits 0 if matches are found, exits 1 if none.
        The test passes when grep exits 1 (= no rename regressions).
        """
        # Assemble the ERE pattern at runtime so this source file does not
        # itself trigger the gate.
        pattern = "cpp_" + "(get|export)_"
        result = subprocess.run(
            ["grep", "-RIE", pattern, "src/", "tests/"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        # grep exit code 1 means no matches found — that is the passing condition.
        # grep exit code 0 means matches ARE found — that is the failure condition.
        assert result.returncode == 1, (
            "ADR-21 grep gate FAILED: old cpp_ prefix pattern found in src/ or tests/.\n"
            "This means a cpp_ rename regression has been introduced.\n"
            f"grep stdout:\n{result.stdout[:2000]}"
        )
