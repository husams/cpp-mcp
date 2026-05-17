"""Boundary / mutation tests for _resolve_access: full AccessSpecifier x parent_kind matrix.

QA-engineer addition — cpp-mcp-v7-s1 — category: mutation/boundary (role category 3).

Gaps addressed that the developer's test_member_of_access.py does NOT cover:
  1. Full Cartesian product: {PUBLIC, PROTECTED, PRIVATE} x every parent_kind in
     _MEMBER_PARENT_KINDS + _PUBLIC_DEFAULT_PARENT_KINDS — mutation coverage to
     detect any wrong-branch return when AccessSpecifier is explicit.
  2. {INVALID, NONE} x every parent_kind — default resolution logic for all
     context kinds (CLASS_DECL, STRUCT_DECL, CLASS_TEMPLATE, UNION_DECL).
  3. parent_kind=None — boundary that can occur if _walk_cursor caller passes None.
  4. Unknown parent_kind string — ensures private default holds for unrecognised parents.
  5. Exception-fallback branch — when the `except Exception` fires (AccessSpecifier
     import unavailable), the parent-kind default must still apply correctly.

Scenarios covered: S1-2 AC1 (SC1), S1-2 AC2 (SC2), S1-2 AC3 (SC3), S1-2 EC1 (union),
                   S1-2 EC3 (negative bound — every value in allowed set).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cpp_mcp.graphdb.exporter import (
    _PUBLIC_DEFAULT_PARENT_KINDS,
    _resolve_access,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_EXPLICIT_PARENT_KINDS = [
    "CLASS_DECL",
    "STRUCT_DECL",
    "CLASS_TEMPLATE",
    "UNION_DECL",
]

_PRIVATE_DEFAULT_PARENT_KINDS = {"CLASS_DECL", "CLASS_TEMPLATE"}
_PUBLIC_DEFAULT_SET = _PUBLIC_DEFAULT_PARENT_KINDS  # STRUCT_DECL, UNION_DECL


def _cursor_with_specifier(spec_value: object) -> MagicMock:
    """Return a mock cursor whose .access_specifier equals spec_value."""
    cursor = MagicMock()
    cursor.access_specifier = spec_value
    return cursor


def _import_access_specifier() -> object:
    from clang.cindex import AccessSpecifier  # type: ignore[import-untyped]

    return AccessSpecifier


# ---------------------------------------------------------------------------
# Part 1 — Explicit specifiers: result must equal the specifier regardless of
#           parent_kind.  Covers the "explicit beats parent" mutation.
# ---------------------------------------------------------------------------


class TestExplicitSpecifierBeatsParentKind:
    """Mutation guard: explicit ACCESS_SPECIFIER always wins over parent-kind default."""

    @pytest.mark.parametrize("parent_kind", _ALL_EXPLICIT_PARENT_KINDS)
    def test_explicit_public_always_returns_public(self, parent_kind: str) -> None:
        """S1-2 AC1, SC1: PUBLIC spec → 'public' for every parent_kind.

        Mutation caught: any branch that returns 'private' when spec==PUBLIC for
        CLASS_DECL or CLASS_TEMPLATE parent_kinds.
        """
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(AS.PUBLIC)  # type: ignore[attr-defined]
        result = _resolve_access(cursor, parent_kind)
        assert result == "public", (
            f"Explicit PUBLIC with parent_kind={parent_kind!r} must return 'public', got {result!r}"
        )

    @pytest.mark.parametrize("parent_kind", _ALL_EXPLICIT_PARENT_KINDS)
    def test_explicit_protected_always_returns_protected(self, parent_kind: str) -> None:
        """S1-2 AC1, SC1: PROTECTED spec → 'protected' for every parent_kind."""
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(AS.PROTECTED)  # type: ignore[attr-defined]
        result = _resolve_access(cursor, parent_kind)
        assert result == "protected", (
            f"Explicit PROTECTED with parent_kind={parent_kind!r} must return 'protected', "
            f"got {result!r}"
        )

    @pytest.mark.parametrize("parent_kind", _ALL_EXPLICIT_PARENT_KINDS)
    def test_explicit_private_always_returns_private(self, parent_kind: str) -> None:
        """S1-2 AC1, SC1: PRIVATE spec → 'private' for every parent_kind.

        Mutation caught: any branch that returns 'public' when spec==PRIVATE for
        STRUCT_DECL or UNION_DECL parent_kinds.
        """
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(AS.PRIVATE)  # type: ignore[attr-defined]
        result = _resolve_access(cursor, parent_kind)
        assert result == "private", (
            f"Explicit PRIVATE with parent_kind={parent_kind!r} must return 'private', "
            f"got {result!r}"
        )


# ---------------------------------------------------------------------------
# Part 2 — INVALID / NONE specifiers: parent_kind default must apply.
#           Covers the full default-resolution matrix.
# ---------------------------------------------------------------------------


class TestInvalidSpecifierUsesParentDefault:
    """S1-2 AC2, AC3, EC1: INVALID or NONE spec triggers parent-kind default."""

    @pytest.mark.parametrize(
        "parent_kind,expected",
        [
            ("STRUCT_DECL", "public"),  # S1-2 AC2, SC2
            ("UNION_DECL", "public"),  # S1-2 EC1 (OQ-3 resolved: union → public)
            ("CLASS_DECL", "private"),  # S1-2 AC3, SC3
            ("CLASS_TEMPLATE", "private"),  # ADR-25 D4: template class default
        ],
    )
    def test_invalid_spec_default_by_parent_kind(self, parent_kind: str, expected: str) -> None:
        """INVALID access specifier resolves to parent-kind default."""
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(AS.INVALID)  # type: ignore[attr-defined]
        result = _resolve_access(cursor, parent_kind)
        assert result == expected, (
            f"INVALID spec with parent_kind={parent_kind!r} expected {expected!r}, got {result!r}"
        )

    @pytest.mark.parametrize(
        "parent_kind,expected",
        [
            ("STRUCT_DECL", "public"),
            ("UNION_DECL", "public"),
            ("CLASS_DECL", "private"),
            ("CLASS_TEMPLATE", "private"),
        ],
    )
    def test_none_spec_default_by_parent_kind(self, parent_kind: str, expected: str) -> None:
        """NONE access specifier resolves to parent-kind default (same as INVALID)."""
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(AS.NONE)  # type: ignore[attr-defined]
        result = _resolve_access(cursor, parent_kind)
        assert result == expected, (
            f"NONE spec with parent_kind={parent_kind!r} expected {expected!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Part 3 — Boundary: parent_kind=None and unknown parent_kind string.
#           Mutation caught: any branch that crashes or returns 'public' for None/unknown.
# ---------------------------------------------------------------------------


class TestBoundaryParentKind:
    """Boundary conditions for parent_kind argument."""

    @pytest.mark.parametrize(
        "spec_attr,parent_kind,expected",
        [
            ("INVALID", None, "private"),  # None not in _PUBLIC_DEFAULT → private
            ("NONE", None, "private"),
            ("INVALID", "UNKNOWN_KIND", "private"),  # unrecognised kind → private
            ("NONE", "UNKNOWN_KIND", "private"),
            ("PUBLIC", None, "public"),  # explicit always wins
            ("PRIVATE", None, "private"),
        ],
    )
    def test_boundary_parent_kind(
        self, spec_attr: str, parent_kind: str | None, expected: str
    ) -> None:
        """Boundary: None or unknown parent_kind must not raise and must return a valid value."""
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(getattr(AS, spec_attr))
        result = _resolve_access(cursor, parent_kind)
        assert result == expected, (
            f"spec={spec_attr!r} parent_kind={parent_kind!r} expected {expected!r}, got {result!r}"
        )
        assert result in {"public", "protected", "private"}, (
            f"Result {result!r} not in allowed set {{public, protected, private}}"
        )


# ---------------------------------------------------------------------------
# Part 4 — Exception-fallback branch.
#           When the `from clang.cindex import AccessSpecifier` raises (simulating
#           libclang unavailable or too old), the except-branch falls through to
#           the parent-kind default.
# ---------------------------------------------------------------------------


class TestExceptionFallbackBranch:
    """Mutation guard: exception in the try-block must fall through to parent-kind default."""

    @pytest.mark.parametrize(
        "parent_kind,expected",
        [
            ("STRUCT_DECL", "public"),
            ("CLASS_DECL", "private"),
            ("CLASS_TEMPLATE", "private"),
            ("UNION_DECL", "public"),
        ],
    )
    def test_import_exception_uses_parent_default(self, parent_kind: str, expected: str) -> None:
        """If AccessSpecifier import raises, parent-kind default is applied.

        This exercises the `except Exception: pass` branch — a mutation that removes
        the try/except would cause an ImportError to propagate instead of defaulting.
        """
        cursor = MagicMock()
        # Make cursor.access_specifier raise to trigger except-branch.
        type(cursor).access_specifier = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no access_specifier"))
        )

        result = _resolve_access(cursor, parent_kind)
        assert result == expected, (
            f"Exception fallback with parent_kind={parent_kind!r} expected {expected!r}, "
            f"got {result!r}"
        )

    def test_import_exception_result_in_allowed_set(self) -> None:
        """S1-2 EC3: exception-path result is always in {{public, protected, private}}."""
        cursor = MagicMock()
        type(cursor).access_specifier = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no access_specifier"))
        )
        for parent_kind in [*_ALL_EXPLICIT_PARENT_KINDS, None, "UNKNOWN"]:
            result = _resolve_access(cursor, parent_kind)
            assert result in {"public", "protected", "private"}, (
                f"Exception-path result {result!r} for parent_kind={parent_kind!r} "
                f"is not in the allowed set"
            )


# ---------------------------------------------------------------------------
# Part 5 — Negative boundary: S1-2 EC3 — every result in allowed set.
#           Exhaustive parametrize over all spec x parent_kind combinations.
# ---------------------------------------------------------------------------


class TestAllResultsInAllowedSet:
    """S1-2 EC3: for any input combination, result must be in {{public, protected, private}}."""

    @pytest.mark.parametrize("parent_kind", [*_ALL_EXPLICIT_PARENT_KINDS, None, "BOGUS"])
    @pytest.mark.parametrize("spec_attr", ["PUBLIC", "PROTECTED", "PRIVATE", "INVALID", "NONE"])
    def test_result_always_in_allowed_set(self, spec_attr: str, parent_kind: str | None) -> None:
        """Every (spec, parent_kind) combination must produce a value in the allowed set."""
        AS = _import_access_specifier()
        cursor = _cursor_with_specifier(getattr(AS, spec_attr))
        result = _resolve_access(cursor, parent_kind)
        assert result in {"public", "protected", "private"}, (
            f"Unexpected access value {result!r} for "
            f"spec={spec_attr!r}, parent_kind={parent_kind!r}"
        )
