"""S4: Error envelope shape verification for all error codes.

SC_USM5_2 (US-M5/AC-2): For each error code, a tool call that
produces that code must return a dict with keys
``{"code", "message", "tool", "request_id"}`` and the expected code value.

Tests use stub functions decorated with @wrap_tool so no real libclang calls
are made; the existing test_error_envelope.py already validates exception→code
mapping — these tests add the wire-shape assertion on top.
"""

from __future__ import annotations

import pytest

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    ErrorCode,
    FatalParseError,
    FileNotFoundError_,
    InvalidArgumentError,
    InvalidPositionError,
    InvalidRangeError,
    PathViolationError,
    wrap_tool,
)

# Complete set of (exception_instance, expected_code) pairs — one per code.
_EXCEPTION_CODE_PAIRS: list[tuple[Exception, str]] = [
    (FileNotFoundError("file missing"), ErrorCode.FILE_NOT_FOUND),
    (FileNotFoundError_("post-validation miss"), ErrorCode.FILE_NOT_FOUND),
    (InvalidPositionError("line out of range"), ErrorCode.INVALID_POSITION),
    (InvalidRangeError("start > end"), ErrorCode.INVALID_RANGE),
    (InvalidArgumentError("bad arg value"), ErrorCode.INVALID_ARGUMENT),
    (PathViolationError("outside allowed roots"), ErrorCode.PATH_VIOLATION),
    (
        DependencyMissingError(
            'neo4j not installed. Install with: pip install "cpp-mcp[graphdb-neo4j]"'
        ),
        ErrorCode.DEPENDENCY_MISSING,
    ),
    (DBUnreachableError("neo4j down"), ErrorCode.DB_UNREACHABLE),
    (FatalParseError("zero AST nodes"), ErrorCode.PARSE_ERROR),
    (RuntimeError("unexpected"), ErrorCode.INTERNAL_ERROR),
]

_ENVELOPE_KEYS: frozenset[str] = frozenset({"code", "message", "tool", "request_id"})

_TOOL_NAME = "cpp_get_definition"


class TestEnvelopeShape:
    """SC_USM5_2: envelope has exactly the expected 4 keys for every error code."""

    @pytest.mark.parametrize(
        ("exc", "expected_code"),
        _EXCEPTION_CODE_PAIRS,
        ids=[str(code) for _, code in _EXCEPTION_CODE_PAIRS],
    )
    def test_envelope_keys_and_code(self, exc: Exception, expected_code: str) -> None:
        """Wire shape: exactly {code, message, tool, request_id} with correct code."""

        @wrap_tool(_TOOL_NAME)
        def failing_tool() -> None:  # type: ignore[return]
            raise exc

        result = failing_tool()

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert set(result.keys()) == _ENVELOPE_KEYS, (
            f"Envelope keys mismatch for code {expected_code}: {set(result.keys())!r}"
        )
        assert result["code"] == str(expected_code), (
            f"Wrong code: expected {expected_code!r}, got {result['code']!r}"
        )
        assert result["tool"] == _TOOL_NAME
        assert isinstance(result["request_id"], str) and result["request_id"]
        assert isinstance(result["message"], str) and result["message"]

    def test_all_error_codes_reachable(self) -> None:
        """Confirm every ErrorCode value has at least one test pair covering it."""
        covered = {str(code) for _, code in _EXCEPTION_CODE_PAIRS}
        all_codes = {str(c) for c in ErrorCode}
        assert covered >= all_codes, f"Uncovered error codes: {all_codes - covered}"

    def test_success_path_returns_payload_not_envelope(self) -> None:
        """wrap_tool must not alter a successful return value."""

        @wrap_tool(_TOOL_NAME)
        def good_tool(x: int) -> dict[str, int]:
            return {"value": x * 2}

        result = good_tool(21)
        assert result == {"value": 42}
