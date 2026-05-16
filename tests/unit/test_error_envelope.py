"""Tests for cpp_mcp.core.error_envelope.

Covers:
- All 8 ErrorCode values exist in the StrEnum.
- build_error() envelope shape matches ADR-8 wire format.
- Message sanitizer: internal paths redacted, caller-echoed paths preserved.
- wrap_tool() decorator: maps each domain exception to correct code.
- INTERNAL_ERROR: no traceback or internal path in returned message.
- Unknown exception → INTERNAL_ERROR.
"""

from __future__ import annotations

import re

import pytest

from cpp_mcp.core.error_envelope import (
    ConfigError,
    DBUnreachableError,
    ErrorCode,
    FatalParseError,
    InvalidArgumentError,
    InvalidPositionError,
    InvalidRangeError,
    PathViolationError,
    build_error,
    wrap_tool,
)

# ---------------------------------------------------------------------------
# ErrorCode enum
# ---------------------------------------------------------------------------

EXPECTED_CODES = {
    "FILE_NOT_FOUND",
    "INVALID_POSITION",
    "INVALID_RANGE",
    "INVALID_ARGUMENT",
    "PATH_VIOLATION",
    "DB_UNREACHABLE",
    "DEPENDENCY_MISSING",
    "PARSE_ERROR",
    "INTERNAL_ERROR",
}


def test_error_code_count() -> None:
    assert len(ErrorCode) == 9


def test_all_expected_codes_present() -> None:
    assert {c.value for c in ErrorCode} == EXPECTED_CODES


@pytest.mark.parametrize("code", list(ErrorCode))
def test_error_code_str_value(code: ErrorCode) -> None:
    """StrEnum: str(code) and code.value are both the UPPER_SNAKE string."""
    assert str(code) == code.value
    assert code == code.value  # StrEnum equality with string


# ---------------------------------------------------------------------------
# build_error — envelope shape
# ---------------------------------------------------------------------------


def test_build_error_shape() -> None:
    envelope = build_error(
        ErrorCode.FILE_NOT_FOUND,
        "The file /projects/src/main.cpp was not found.",
        "cpp_get_definition",
        "abc123",
        echo=("/projects/src/main.cpp",),
    )
    assert set(envelope.keys()) == {"code", "message", "tool", "request_id"}
    assert envelope["code"] == "FILE_NOT_FOUND"
    assert envelope["tool"] == "cpp_get_definition"
    assert envelope["request_id"] == "abc123"


def test_build_error_all_codes() -> None:
    """build_error works for every ErrorCode without raising."""
    for code in ErrorCode:
        envelope = build_error(code, "test message", "test_tool", "rid-001")
        assert envelope["code"] == str(code)


# ---------------------------------------------------------------------------
# Message sanitizer
# ---------------------------------------------------------------------------


def test_sanitizer_redacts_internal_path() -> None:
    """An internal server path not echoed by caller must be redacted."""
    envelope = build_error(
        ErrorCode.INTERNAL_ERROR,
        "Error in /Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/error_envelope.py",
        "cpp_get_definition",
        "rid-002",
        echo=(),
    )
    assert "<redacted>" in envelope["message"]
    assert "/Users/husam" not in envelope["message"]


def test_sanitizer_preserves_echoed_caller_path() -> None:
    """A caller-supplied path explicitly echoed must survive sanitization."""
    caller_path = "/projects/src/main.cpp"
    envelope = build_error(
        ErrorCode.FILE_NOT_FOUND,
        f"File not found: {caller_path}",
        "cpp_get_definition",
        "rid-003",
        echo=(caller_path,),
    )
    assert caller_path in envelope["message"]
    assert "<redacted>" not in envelope["message"]


def test_sanitizer_redacts_path_not_in_echo() -> None:
    """A path not in echo is redacted even if it looks like a project path."""
    envelope = build_error(
        ErrorCode.PATH_VIOLATION,
        "Resolved to /etc/passwd which is outside allowed roots.",
        "cpp_get_definition",
        "rid-004",
        echo=(),
    )
    assert "/etc/passwd" not in envelope["message"]
    assert "<redacted>" in envelope["message"]


def test_sanitizer_static_message_unchanged() -> None:
    """A message with no path-shaped substrings passes through unchanged."""
    msg = "An internal error occurred."
    envelope = build_error(ErrorCode.INTERNAL_ERROR, msg, "tool", "rid-005")
    assert envelope["message"] == msg


# ---------------------------------------------------------------------------
# wrap_tool — exception-to-code mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (PathViolationError("path escape"), "PATH_VIOLATION"),
        (FileNotFoundError("not found"), "FILE_NOT_FOUND"),
        (InvalidPositionError("out of range"), "INVALID_POSITION"),
        (InvalidRangeError("start > end"), "INVALID_RANGE"),
        (InvalidArgumentError("bad arg"), "INVALID_ARGUMENT"),
        (DBUnreachableError("neo4j down"), "DB_UNREACHABLE"),
        (FatalParseError("zero nodes"), "PARSE_ERROR"),
    ],
)
def test_wrap_tool_maps_domain_exceptions(exc: Exception, expected_code: str) -> None:
    @wrap_tool("my_tool")
    def failing_tool() -> None:  # type: ignore[return]
        raise exc

    result = failing_tool()
    assert isinstance(result, dict)
    assert result["code"] == expected_code
    assert result["tool"] == "my_tool"
    assert "request_id" in result


def test_wrap_tool_unknown_exception_becomes_internal_error() -> None:
    @wrap_tool("my_tool")
    def buggy_tool() -> None:  # type: ignore[return]
        raise RuntimeError("unexpected!")

    result = buggy_tool()
    assert result["code"] == "INTERNAL_ERROR"
    assert result["tool"] == "my_tool"


def test_wrap_tool_internal_error_no_traceback_in_message() -> None:
    """INTERNAL_ERROR message must not contain Python traceback text."""

    @wrap_tool("my_tool")
    def buggy_tool() -> None:  # type: ignore[return]
        raise RuntimeError("Traceback (most recent call last): secret detail")

    result = buggy_tool()
    assert result["code"] == "INTERNAL_ERROR"
    # The sanitized message should not expose the original exception text.
    assert "secret detail" not in result["message"]


def test_wrap_tool_internal_error_no_internal_path() -> None:
    """INTERNAL_ERROR must not expose server-internal absolute paths."""

    @wrap_tool("my_tool")
    def buggy_tool() -> None:  # type: ignore[return]
        raise RuntimeError("failed in /Users/husam/workspace/cpp-mcp/src/secret.py")

    result = buggy_tool()
    assert result["code"] == "INTERNAL_ERROR"
    assert "/Users/husam" not in result["message"]


def test_wrap_tool_happy_path_returns_result() -> None:
    @wrap_tool("my_tool")
    def good_tool(x: int) -> dict[str, int]:
        return {"value": x * 2}

    result = good_tool(21)
    assert result == {"value": 42}


def test_wrap_tool_generates_unique_request_ids() -> None:
    results: list[dict[str, str]] = []

    @wrap_tool("my_tool")
    def failing_tool() -> None:  # type: ignore[return]
        raise PathViolationError("esc")

    for _ in range(3):
        results.append(failing_tool())  # type: ignore[arg-type]

    ids = [r["request_id"] for r in results]
    assert len(set(ids)) == 3  # all unique


def test_wrap_tool_echoes_caller_path_in_error() -> None:
    """Caller-provided path args should be preserved in error messages."""
    caller_path = "/projects/src/main.cpp"

    @wrap_tool("my_tool")
    def tool_with_path(file_path: str) -> None:  # type: ignore[return]
        raise FileNotFoundError(f"File not found: {file_path}")

    result = tool_with_path(file_path=caller_path)
    assert caller_path in result["message"]


# ---------------------------------------------------------------------------
# ConfigError is importable from error_envelope
# ---------------------------------------------------------------------------


def test_config_error_importable() -> None:
    assert issubclass(ConfigError, Exception)


# ---------------------------------------------------------------------------
# INTERNAL_ERROR: no traceback per US-13/AC-2
# ---------------------------------------------------------------------------


def test_internal_error_message_is_generic() -> None:
    """INTERNAL_ERROR response message should be a static safe string."""

    @wrap_tool("my_tool")
    def buggy() -> None:  # type: ignore[return]
        raise ValueError("db password is s3cr3t!")

    result = buggy()
    assert result["code"] == "INTERNAL_ERROR"
    # Should not leak the exception message content.
    assert "s3cr3t" not in result["message"]
    assert re.match(r"[A-Za-z .']+", result["message"])
