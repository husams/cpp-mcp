"""S1: Verify the four new query-surface error codes and exception classes.

AC-Q1-7: new codes registered in ErrorCode enum and mapped via _EXC_TO_CODE.
"""

from __future__ import annotations

import pytest

from cpp_mcp.core.error_envelope import (
    _EXC_TO_CODE,
    ErrorCode,
    QueryParseError,
    QueryTimeoutError,
    QueryUnsupportedError,
    ReadOnlyViolationError,
)

# ---------------------------------------------------------------------------
# Expected new codes + their exception types
# ---------------------------------------------------------------------------

_NEW_CODE_EXC_PAIRS: list[tuple[type[Exception], ErrorCode]] = [
    (ReadOnlyViolationError, ErrorCode.READ_ONLY_VIOLATION),
    (QueryParseError, ErrorCode.QUERY_PARSE_ERROR),
    (QueryUnsupportedError, ErrorCode.QUERY_UNSUPPORTED),
    (QueryTimeoutError, ErrorCode.QUERY_TIMEOUT),
]


class TestNewErrorCodesPresent:
    """Each new code must appear in the ErrorCode enum."""

    @pytest.mark.parametrize(
        ("exc_cls", "expected_code"),
        _NEW_CODE_EXC_PAIRS,
        ids=[c.value for _, c in _NEW_CODE_EXC_PAIRS],
    )
    def test_code_in_enum(self, exc_cls: type[Exception], expected_code: ErrorCode) -> None:
        assert expected_code in ErrorCode, f"{expected_code!r} missing from ErrorCode enum"

    def test_all_new_codes_unique(self) -> None:
        """New code values must not collide with each other or any existing code."""
        new_values = [c.value for _, c in _NEW_CODE_EXC_PAIRS]
        assert len(new_values) == len(set(new_values)), "Duplicate values among new codes"
        all_values = [c.value for c in ErrorCode]
        assert len(all_values) == len(set(all_values)), "Duplicate values in full ErrorCode enum"


class TestExcToCodeMapping:
    """Each new exception class must appear in _EXC_TO_CODE with its correct code."""

    @pytest.mark.parametrize(
        ("exc_cls", "expected_code"),
        _NEW_CODE_EXC_PAIRS,
        ids=[c.value for _, c in _NEW_CODE_EXC_PAIRS],
    )
    def test_exc_mapped_to_code(self, exc_cls: type[Exception], expected_code: ErrorCode) -> None:
        matched = [code for exc_type, code in _EXC_TO_CODE if exc_type is exc_cls]
        assert matched, f"{exc_cls.__name__} not found in _EXC_TO_CODE"
        assert matched[0] == expected_code, (
            f"{exc_cls.__name__} maps to {matched[0]!r}, expected {expected_code!r}"
        )

    def test_no_duplicate_exc_entries(self) -> None:
        """No exception type should appear more than once in _EXC_TO_CODE."""
        exc_types = [exc_type for exc_type, _ in _EXC_TO_CODE]
        assert len(exc_types) == len(set(exc_types)), "Duplicate exception types in _EXC_TO_CODE"
