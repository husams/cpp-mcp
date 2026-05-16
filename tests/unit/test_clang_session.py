"""Unit tests for cpp_mcp.core.clang_session.ClangSession.

Marked @pytest.mark.libclang — skipped automatically if libclang cannot be loaded.

Test matrix (Story 4 / US-8, US-10):
  1. Smoke parse of tests/fixtures/cpp/tiny.cpp → TU returned, no fatal errors.
  2. Two concurrent async parses run on the same worker thread (serialized).
  3. cache_stats() returns the expected keys after a parse.
  4. shutdown() is idempotent.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# libclang availability check — skip the whole module if not available
# ---------------------------------------------------------------------------

_libclang_available = False
try:
    import clang.cindex as _ci  # type: ignore[import-untyped]

    # Actually try to create an Index to confirm the .dylib/.so loads.
    _ci.Index.create()
    _libclang_available = True
except Exception:
    pass

pytestmark = pytest.mark.libclang

# Apply module-level skip if libclang is not loadable on this host.
if not _libclang_available:
    pytestmark = pytest.mark.skip(reason="libclang not available on this host")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TINY_CPP = Path(__file__).parent.parent / "fixtures" / "cpp" / "tiny.cpp"
_DEFAULT_FLAGS: tuple[str, ...] = ("-std=c++20",)


@pytest.fixture()
def session():  # type: ignore[no-untyped-def]
    from cpp_mcp.core.clang_session import ClangSession

    s = ClangSession(capacity=16)
    yield s
    s.shutdown(wait=True)


# ---------------------------------------------------------------------------
# 1. Smoke parse of tiny.cpp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_parse_tiny_cpp(session) -> None:  # type: ignore[no-untyped-def]
    """Parse tiny.cpp; expect a TU back with no fatal diagnostics."""
    assert _TINY_CPP.exists(), f"Fixture missing: {_TINY_CPP}"

    tu, cache_hit = await session.parse(_TINY_CPP, None, _DEFAULT_FLAGS)

    # A successful parse returns a TranslationUnit-like object with diagnostics.
    assert tu is not None
    assert cache_hit is False  # first parse is always a miss
    # Check there are no fatal-severity diagnostics (severity 4 = FATAL).
    import clang.cindex as ci  # type: ignore[import-untyped]

    fatal = [d for d in tu.diagnostics if d.severity == ci.Diagnostic.Fatal]
    assert fatal == [], f"Fatal diagnostics: {[d.spelling for d in fatal]}"


# ---------------------------------------------------------------------------
# 2. Two concurrent async parses run on the same worker thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_parses_serialized_on_same_thread(session) -> None:  # type: ignore[no-untyped-def]
    """Two async parses run concurrently but are serialized to one thread."""
    thread_ids: list[int] = []

    loop = asyncio.get_running_loop()

    def _record_thread(_: Path, __: tuple[str, ...]) -> object:
        thread_ids.append(threading.get_ident())
        return object()  # fake TU — we only care about thread IDs

    # Use two distinct flag sets to force two cache misses so _record_thread is called.
    assert _TINY_CPP.exists()

    flags_a = ("-DFOO",)
    flags_b = ("-DBAR",)

    t1 = loop.run_in_executor(
        session._executor,
        lambda: session._cache.get_or_parse(_TINY_CPP, None, flags_a, _record_thread),
    )
    t2 = loop.run_in_executor(
        session._executor,
        lambda: session._cache.get_or_parse(_TINY_CPP, None, flags_b, _record_thread),
    )

    await asyncio.gather(t1, t2)

    assert len(thread_ids) == 2, f"Expected 2 parser calls, got {len(thread_ids)}"
    # All parses must have occurred on the SAME worker thread (single-worker executor).
    assert thread_ids[0] == thread_ids[1], (
        f"Parses ran on different threads: {thread_ids}; single-worker constraint violated"
    )


# ---------------------------------------------------------------------------
# 3. cache_stats() returns expected keys after a parse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_stats_after_parse(session) -> None:  # type: ignore[no-untyped-def]
    assert _TINY_CPP.exists()

    stats_before = session.cache_stats()
    assert stats_before["cache_size"] == 0
    assert stats_before["misses"] == 0

    await session.parse(_TINY_CPP, None, _DEFAULT_FLAGS)

    stats_after = session.cache_stats()
    assert stats_after["cache_size"] == 1
    assert stats_after["misses"] == 1
    assert stats_after["hits"] == 0

    # Second parse → cache hit
    await session.parse(_TINY_CPP, None, _DEFAULT_FLAGS)
    stats_hit = session.cache_stats()
    assert stats_hit["hits"] == 1
    assert stats_hit["misses"] == 1

    expected_keys = {
        "cache_size",
        "cache_capacity",
        "hits",
        "misses",
        "evictions",
        "cache_hit_rate",
    }
    assert set(stats_hit.keys()) == expected_keys


# ---------------------------------------------------------------------------
# 4. Shutdown is idempotent
# ---------------------------------------------------------------------------


def test_shutdown_is_idempotent() -> None:
    from cpp_mcp.core.clang_session import ClangSession

    s = ClangSession(capacity=4)
    s.shutdown(wait=True)
    s.shutdown(wait=True)  # Should not raise
