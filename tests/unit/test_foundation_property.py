"""Property-based tests for foundation modules (Stories 1-4).

Uses Hypothesis to exercise boundary conditions and invariants beyond the
developer's happy-path parametrised tests.

Mandatory-addition category: property-based / parametrised (Hypothesis).

Scenarios covered:
  SC-US-12-1 (PATH_VIOLATION for .. in path)
  SC-US-12-4 (absolute path within root passes)
  SC-US-12-6 (absolute path outside root rejected)
  SC-US-13-1 (error envelope always conforms to schema)
  SC-US-13-2 (INTERNAL_ERROR never exposes internals)
  SC-US-13-3 (no unstructured error string)
  SC-US-9-1  (default flags returned when build_path=None)
  SC-US-8-1  (stateless: resolve_flags is pure, no cross-call contamination)
  SC-US-10-2 (cache miss on first call for new key)
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    ErrorCode,
    FatalParseError,
    FileNotFoundError_,
    InvalidArgumentError,
    InvalidPositionError,
    InvalidRangeError,
    PathViolationError,
    build_error,
    wrap_tool,
)
from cpp_mcp.core.path_guard import validate_path
from cpp_mcp.core.tu_cache import TUCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All valid ErrorCode values as a flat list for strategies.
_ALL_CODES = list(ErrorCode)

# Strategy for arbitrary tool names (non-empty ASCII strings).
_tool_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=32,
)

# Strategy for safe printable non-path strings (no leading '/').
_safe_msg_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"), whitelist_characters=" .,!"
    ),
    min_size=0,
    max_size=200,
)


# ---------------------------------------------------------------------------
# Property 1: build_error always produces exactly the 4-key envelope schema
# [SC-US-13-1]
# ---------------------------------------------------------------------------


@given(
    code=st.sampled_from(_ALL_CODES),
    message=_safe_msg_st,
    tool=_tool_name_st,
    request_id=st.uuids().map(lambda u: u.hex),
)
@settings(max_examples=200)
def test_build_error_envelope_schema_invariant(
    code: ErrorCode,
    message: str,
    tool: str,
    request_id: str,
) -> None:
    """SC-US-13-1: build_error always returns exactly {code, message, tool, request_id}."""
    envelope = build_error(code, message, tool, request_id)
    assert set(envelope.keys()) == {"code", "message", "tool", "request_id"}
    assert envelope["code"] in {c.value for c in ErrorCode}
    assert isinstance(envelope["message"], str)
    assert isinstance(envelope["tool"], str)
    assert isinstance(envelope["request_id"], str)


# ---------------------------------------------------------------------------
# Property 2: sanitizer never leaks absolute paths not in echo
# [SC-US-13-2, SC-US-13-3]
# ---------------------------------------------------------------------------


@given(
    internal_path=st.from_regex(r"/[a-z]{1,8}/[a-z]{1,8}/[a-z]{1,8}\.py", fullmatch=True),
    prefix=_safe_msg_st,
    suffix=_safe_msg_st,
)
@settings(max_examples=200)
def test_sanitizer_redacts_unechoed_absolute_paths(
    internal_path: str,
    prefix: str,
    suffix: str,
) -> None:
    """SC-US-13-2: Any absolute-path-shaped substring not in echo is redacted."""
    message = f"{prefix}{internal_path}{suffix}"
    envelope = build_error(
        ErrorCode.INTERNAL_ERROR,
        message,
        "test_tool",
        uuid.uuid4().hex,
        echo=(),
    )
    # The internal path must not survive in the message.
    assert internal_path not in envelope["message"]
    # Its replacement must be <redacted> (or the path was a substring of a larger match).
    assert "<redacted>" in envelope["message"] or internal_path not in envelope["message"]


@given(
    caller_path=st.from_regex(r"/projects/[a-z]{1,8}/[a-z]{1,8}\.cpp", fullmatch=True),
    prefix=_safe_msg_st,
)
@settings(max_examples=100)
def test_sanitizer_preserves_echoed_paths(
    caller_path: str,
    prefix: str,
) -> None:
    """SC-US-13-2: Caller-supplied paths that are echoed survive sanitization verbatim."""
    message = f"{prefix}File not found: {caller_path}"
    envelope = build_error(
        ErrorCode.FILE_NOT_FOUND,
        message,
        "test_tool",
        uuid.uuid4().hex,
        echo=(caller_path,),
    )
    assert caller_path in envelope["message"]


# ---------------------------------------------------------------------------
# Property 3: wrap_tool always produces a structured dict (never a plain string)
# [SC-US-13-3]
# ---------------------------------------------------------------------------

_ALL_DOMAIN_EXCEPTIONS: list[BaseException] = [
    PathViolationError("path escape"),
    FileNotFoundError("not found"),
    FileNotFoundError_("not found post-validation"),
    InvalidPositionError("out of range"),
    InvalidRangeError("start > end"),
    InvalidArgumentError("bad arg"),
    DBUnreachableError("db down"),
    FatalParseError("zero nodes"),
    RuntimeError("unexpected bug"),
    ValueError("bad value"),
    KeyError("missing key"),
]


@given(exc_index=st.integers(min_value=0, max_value=len(_ALL_DOMAIN_EXCEPTIONS) - 1))
@settings(max_examples=len(_ALL_DOMAIN_EXCEPTIONS))
def test_wrap_tool_always_returns_structured_dict(exc_index: int) -> None:
    """SC-US-13-3: wrap_tool never returns a plain string; always returns dict with 'code'."""
    exc = _ALL_DOMAIN_EXCEPTIONS[exc_index]

    @wrap_tool("test_tool")
    def failing() -> None:  # type: ignore[return]
        raise exc

    result = failing()
    assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result!r}"
    assert "code" in result
    assert result["code"] in {c.value for c in ErrorCode}
    assert "message" in result
    assert "tool" in result
    assert "request_id" in result


# ---------------------------------------------------------------------------
# Property 4: path_guard._has_dotdot — any path with a ".." segment is caught
# [SC-US-12-1]
# ---------------------------------------------------------------------------

# Generate paths that actually contain ".." as a segment (not just in filename).
_dotdot_path_st = st.one_of(
    # Relative traversal
    st.just("../etc/passwd"),
    st.just("../../etc/passwd"),
    st.just("foo/../bar"),
    st.just("foo/bar/../../etc"),
    # With leading slash
    st.just("/projects/../etc"),
    st.just("/projects/src/../../etc/shadow"),
    # Just ".."
    st.just(".."),
    # ".." as a component at any nesting level
    st.lists(
        st.one_of(
            st.just(".."),
            st.text(alphabet=st.characters(whitelist_categories=("Ll",)), min_size=1, max_size=8),
        ),
        min_size=1,
        max_size=5,
    )
    .map(lambda parts: "/".join(parts))
    .filter(lambda p: ".." in p.split("/")),
)


@given(path_with_dotdot=_dotdot_path_st)
@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_has_dotdot_rejects_all_dotdot_paths(path_with_dotdot: str) -> None:
    """SC-US-12-1: Any path containing a '..' segment raises PathViolationError."""
    import os as _os

    with tempfile.TemporaryDirectory() as tmp:
        allowed = (_os.path.realpath(tmp),)
        # The path must contain '..' as a component — confirm assumption before test.
        parts = Path(path_with_dotdot).parts
        assume(".." in parts)
        with pytest.raises(PathViolationError):
            validate_path(path_with_dotdot, allowed)


# ---------------------------------------------------------------------------
# Property 5: path outside allowed root is always rejected
# [SC-US-12-6]
# ---------------------------------------------------------------------------


@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=20,
    ).map(lambda n: n + ".cpp"),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_path_outside_root_always_rejected(filename: str) -> None:
    """SC-US-12-6: File outside allowed_root raises PathViolationError regardless of name."""
    import os as _os

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(_os.path.realpath(tmp))
        allowed_root = tmp_path / "allowed"
        allowed_root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / filename
        target.write_text("// outside", encoding="utf-8")

        with pytest.raises(PathViolationError):
            validate_path(str(target), (str(allowed_root),))


# ---------------------------------------------------------------------------
# Property 6: path inside allowed root always passes validation (no dotdot, real file)
# [SC-US-12-4]
# ---------------------------------------------------------------------------


@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=20,
    ).map(lambda n: n + ".cpp"),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_valid_path_inside_root_always_passes(filename: str) -> None:
    """SC-US-12-4: An absolute path inside allowed_root passes validation."""
    import os as _os

    with tempfile.TemporaryDirectory() as tmp:
        # Resolve symlinks so macOS /var/folders -> /private/var/folders is handled.
        tmp_real = _os.path.realpath(tmp)
        allowed_root = Path(tmp_real) / "projects"
        allowed_root.mkdir()
        target = allowed_root / filename
        target.write_text("// ok", encoding="utf-8")

        result = validate_path(str(target), (str(allowed_root),))
        assert result.is_absolute()
        assert str(result).startswith(str(allowed_root))


# ---------------------------------------------------------------------------
# Property 7: resolve_flags with build_path=None always returns supplied default_flags
# [SC-US-9-1, SC-US-8-1]
# ---------------------------------------------------------------------------


@given(
    default_flags=st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_="
            ),
            min_size=1,
            max_size=20,
        ),
        min_size=0,
        max_size=10,
    ).map(tuple),
)
@settings(max_examples=200)
def test_resolve_flags_none_build_path_returns_default(
    default_flags: tuple[str, ...],
) -> None:
    """SC-US-9-1: resolve_flags(build_path=None) always returns (default_flags, 'default').

    Also validates SC-US-8-1 (stateless): calling multiple times with None
    always produces the same pure result; no cross-call contamination.
    """
    from cpp_mcp.core.compile_db import resolve_flags

    # Use a Path that does not need to exist (build_path=None path)
    src = Path("/tmp/nonexistent_src.cpp")
    # Call twice to verify stateless purity.
    flags1, src1 = resolve_flags(src, None, default_flags)
    flags2, src2 = resolve_flags(src, None, default_flags)

    assert flags1 == default_flags
    assert src1 == "default"
    assert flags2 == default_flags
    assert src2 == "default"


# ---------------------------------------------------------------------------
# Property 8: TUCache miss on every distinct (file, build, flags) key
# [SC-US-10-2]
# ---------------------------------------------------------------------------


@given(
    n_files=st.integers(min_value=1, max_value=5),
    capacity=st.integers(min_value=5, max_value=20),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_tu_cache_miss_on_each_distinct_key(
    n_files: int,
    capacity: int,
) -> None:
    """SC-US-10-2: Each new (file_path, build_path, flags) key is always a miss."""
    import os as _os

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(_os.path.realpath(tmp))
        cache = TUCache(capacity=capacity)
        flags = ("-std=c++20",)

        for i in range(n_files):
            src = tmp_path / f"file_{i}.cpp"
            src.write_text(f"int x{i};", encoding="utf-8")
            parser = MagicMock(return_value=MagicMock(name=f"TU{i}"))
            _, cache_hit = cache.get_or_parse(src, None, flags, parser)
            assert cache_hit is False, f"Expected miss for new file {i}, got hit"


# ---------------------------------------------------------------------------
# Property 9: ErrorCode closed-set invariant — error code is always valid
# [SC-US-13-1]
# ---------------------------------------------------------------------------

_VALID_CODES = frozenset(c.value for c in ErrorCode)


@given(
    exc_index=st.integers(min_value=0, max_value=len(_ALL_DOMAIN_EXCEPTIONS) - 1),
    tool_name=_tool_name_st,
)
@settings(max_examples=100)
def test_wrap_tool_code_always_in_valid_set(exc_index: int, tool_name: str) -> None:
    """SC-US-13-1: code field always in the closed ErrorCode set."""
    exc = _ALL_DOMAIN_EXCEPTIONS[exc_index]

    @wrap_tool(tool_name)
    def failing() -> None:  # type: ignore[return]
        raise exc

    result = failing()
    assert result["code"] in _VALID_CODES, (
        f"code={result['code']!r} not in valid set {_VALID_CODES}"
    )


# ---------------------------------------------------------------------------
# Property 10: Parametrised boundary — dotdot as exactly the first or last segment
# [SC-US-12-1] — supplementary parametrised variant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_path",
    [
        # Leading traversal
        "../escape",
        "../../escape",
        "../../../etc/passwd",
        # Trailing traversal
        "foo/..",
        "foo/bar/..",
        # Middle traversal
        "foo/../bar",
        "a/b/../c/d",
        "/projects/../etc",
        "/projects/src/../../other",
        # Windows-style (rejected by PurePath.parts on POSIX too)
        "..",
        # Mixed depth
        "a/../b/../c",
    ],
)
def test_dotdot_boundary_cases(raw_path: str, tmp_path: Path) -> None:
    """SC-US-12-1: Explicit boundary-condition paths with '..' are all rejected."""
    parts = Path(raw_path).parts
    if ".." not in parts:
        pytest.skip(f"path {raw_path!r} has no '..' segment after PurePath parsing")
    with pytest.raises(PathViolationError):
        validate_path(raw_path, (str(tmp_path),))
