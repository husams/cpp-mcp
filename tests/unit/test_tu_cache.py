"""Unit tests for cpp_mcp.core.tu_cache.TUCache.

libclang is NOT required; a fake parser callable is injected.

Test matrix (Story 4 / US-10):
  1. Cache miss on first access → parser called once.
  2. Cache hit on second access for same (file, build, flags) → parser not called again.
  3. LRU eviction: insert capacity+1 distinct keys → oldest is evicted.
  4. Two build_paths for the same file → two independent cache entries.
  5. mtime invalidation: touch file → next lookup is a miss, re-parses.
  6. stats() returns correct keys and counts.
  7. Configurable capacity: TUCache(capacity=2) evicts at 3rd entry.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.core.tu_cache import TUCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_FLAGS: tuple[str, ...] = ("-std=c++20",)


def _make_fake_parser(return_value: Any = None) -> tuple[Any, MagicMock]:
    """Return (return_value_or_mock, mock_callable) for injection as parser."""
    tu = return_value if return_value is not None else MagicMock(name="TU")
    mock = MagicMock(return_value=tu)
    return tu, mock


# ---------------------------------------------------------------------------
# 1. Cache miss on first access
# ---------------------------------------------------------------------------


def test_first_access_is_miss(tmp_path: Path) -> None:
    src = tmp_path / "main.cpp"
    src.write_text("int main(){}", encoding="utf-8")

    tu_obj, parser = _make_fake_parser()
    cache = TUCache(capacity=4)

    result, cache_hit = cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)

    assert result is tu_obj
    assert cache_hit is False
    parser.assert_called_once_with(src.resolve(), _DEFAULT_FLAGS)


# ---------------------------------------------------------------------------
# 2. Cache hit on second access — parser NOT called again
# ---------------------------------------------------------------------------


def test_second_access_is_hit(tmp_path: Path) -> None:
    src = tmp_path / "main.cpp"
    src.write_text("int main(){}", encoding="utf-8")

    tu_obj, parser = _make_fake_parser()
    cache = TUCache(capacity=4)

    cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)
    result2, cache_hit2 = cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)

    assert result2 is tu_obj
    assert cache_hit2 is True
    assert parser.call_count == 1  # Only called once (the first miss)


# ---------------------------------------------------------------------------
# 3. LRU eviction: insert capacity+1 distinct files → oldest is evicted
# ---------------------------------------------------------------------------


def test_lru_eviction(tmp_path: Path) -> None:
    capacity = 3
    cache = TUCache(capacity=capacity)
    sources: list[Path] = []
    parsers: list[MagicMock] = []

    for i in range(capacity + 1):
        src = tmp_path / f"file{i}.cpp"
        src.write_text(f"int x{i};", encoding="utf-8")
        sources.append(src)
        _, p = _make_fake_parser(MagicMock(name=f"TU{i}"))
        parsers.append(p)

    # Fill cache to capacity (0, 1, 2)
    for i in range(capacity):
        cache.get_or_parse(sources[i], None, _DEFAULT_FLAGS, parsers[i])

    # Access file 0 to make it MRU (so file 1 becomes LRU)
    cache.get_or_parse(sources[0], None, _DEFAULT_FLAGS, parsers[0])

    # Insert capacity+1 (file 3) — file 1 (LRU) should be evicted
    _, parser3 = _make_fake_parser(MagicMock(name="TU3"))
    cache.get_or_parse(sources[3], None, _DEFAULT_FLAGS, parser3)

    stats = cache.stats()
    assert stats["cache_size"] == capacity
    assert stats["evictions"] >= 1

    # File 1 should be a miss now (evicted)
    _, reparser1 = _make_fake_parser()
    cache.get_or_parse(sources[1], None, _DEFAULT_FLAGS, reparser1)
    reparser1.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Two build_paths for the same file → independent entries
# ---------------------------------------------------------------------------


def test_two_build_paths_separate_entries(tmp_path: Path) -> None:
    src = tmp_path / "main.cpp"
    src.write_text("int main(){}", encoding="utf-8")

    build_a = tmp_path / "build_a"
    build_a.mkdir()
    build_b = tmp_path / "build_b"
    build_b.mkdir()

    tu_a, parser_a = _make_fake_parser(MagicMock(name="TU_A"))
    tu_b, parser_b = _make_fake_parser(MagicMock(name="TU_B"))

    cache = TUCache(capacity=8)

    result_a, hit_a1 = cache.get_or_parse(src, build_a, _DEFAULT_FLAGS, parser_a)
    result_b, hit_b1 = cache.get_or_parse(src, build_b, _DEFAULT_FLAGS, parser_b)

    assert result_a is tu_a
    assert result_b is tu_b
    assert result_a is not result_b
    assert hit_a1 is False
    assert hit_b1 is False

    parser_a.assert_called_once()
    parser_b.assert_called_once()

    # Second access for each → cache hits
    _, hit_a2 = cache.get_or_parse(src, build_a, _DEFAULT_FLAGS, parser_a)
    _, hit_b2 = cache.get_or_parse(src, build_b, _DEFAULT_FLAGS, parser_b)
    assert hit_a2 is True
    assert hit_b2 is True
    assert parser_a.call_count == 1
    assert parser_b.call_count == 1

    stats = cache.stats()
    assert stats["cache_size"] == 2


# ---------------------------------------------------------------------------
# 5. mtime invalidation: modify file → next lookup is a miss
# ---------------------------------------------------------------------------


def test_mtime_invalidation_triggers_reparse(tmp_path: Path) -> None:
    src = tmp_path / "main.cpp"
    src.write_text("int main(){}", encoding="utf-8")

    _tu1, parser1 = _make_fake_parser(MagicMock(name="TU1"))
    cache = TUCache(capacity=4)

    cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser1)
    parser1.assert_called_once()

    # Force a deterministic mtime change (advance by 2 seconds).
    stat = os.stat(str(src))
    new_ns = stat.st_mtime_ns + 2_000_000_000  # +2 s in nanoseconds
    os.utime(str(src), ns=(stat.st_atime_ns, new_ns))

    tu2, parser2 = _make_fake_parser(MagicMock(name="TU2"))
    result, cache_hit = cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser2)

    parser2.assert_called_once()  # miss → re-parse
    assert result is tu2
    assert cache_hit is False

    stats = cache.stats()
    assert stats["misses"] == 2
    assert stats["hits"] == 0
    assert stats["evictions"] >= 1  # stale entry evicted


# ---------------------------------------------------------------------------
# 6. stats() returns correct structure and counts
# ---------------------------------------------------------------------------


def test_stats_structure_and_counts(tmp_path: Path) -> None:
    src = tmp_path / "s.cpp"
    src.write_text("void f(){}", encoding="utf-8")

    cache = TUCache(capacity=4)
    _, parser = _make_fake_parser()

    # Initial stats
    s0 = cache.stats()
    assert set(s0.keys()) == {
        "cache_size",
        "cache_capacity",
        "hits",
        "misses",
        "evictions",
        "cache_hit_rate",
    }
    assert s0["cache_hit_rate"] == 0.0
    assert s0["cache_size"] == 0

    # One miss
    cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)
    s1 = cache.stats()
    assert s1["misses"] == 1
    assert s1["hits"] == 0
    assert s1["cache_size"] == 1

    # One hit
    cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)
    s2 = cache.stats()
    assert s2["hits"] == 1
    assert s2["misses"] == 1
    assert s2["cache_hit_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 7. Configurable capacity — evict at boundary
# ---------------------------------------------------------------------------


def test_configurable_capacity(tmp_path: Path) -> None:
    cache = TUCache(capacity=2)

    src_a = tmp_path / "a.cpp"
    src_a.write_text("int a;", encoding="utf-8")
    src_b = tmp_path / "b.cpp"
    src_b.write_text("int b;", encoding="utf-8")
    src_c = tmp_path / "c.cpp"
    src_c.write_text("int c;", encoding="utf-8")

    _, pa = _make_fake_parser()
    _, pb = _make_fake_parser()
    _, pc = _make_fake_parser()

    cache.get_or_parse(src_a, None, _DEFAULT_FLAGS, pa)
    cache.get_or_parse(src_b, None, _DEFAULT_FLAGS, pb)
    assert cache.stats()["cache_size"] == 2

    # Third entry: should evict the LRU (src_a)
    cache.get_or_parse(src_c, None, _DEFAULT_FLAGS, pc)
    assert cache.stats()["cache_size"] == 2
    assert cache.stats()["evictions"] >= 1


# ---------------------------------------------------------------------------
# 8. Different flags for same (file, build) → separate entries
# ---------------------------------------------------------------------------


def test_different_flags_separate_entries(tmp_path: Path) -> None:
    src = tmp_path / "m.cpp"
    src.write_text("int m;", encoding="utf-8")

    flags_a = ("-std=c++17",)
    flags_b = ("-std=c++20",)

    _tu_a, pa = _make_fake_parser(MagicMock(name="TU_A"))
    _tu_b, pb = _make_fake_parser(MagicMock(name="TU_B"))
    cache = TUCache(capacity=4)

    result_a, _ = cache.get_or_parse(src, None, flags_a, pa)
    result_b, _ = cache.get_or_parse(src, None, flags_b, pb)

    assert result_a is not result_b
    pa.assert_called_once()
    pb.assert_called_once()


# ---------------------------------------------------------------------------
# 9. invalidate() removes matching entries
# ---------------------------------------------------------------------------


def test_invalidate_removes_entry(tmp_path: Path) -> None:
    src = tmp_path / "x.cpp"
    src.write_text("int x;", encoding="utf-8")

    cache = TUCache(capacity=4)
    _, parser = _make_fake_parser()

    cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)
    assert cache.stats()["cache_size"] == 1

    removed = cache.invalidate(src)
    assert removed == 1
    assert cache.stats()["cache_size"] == 0


# ---------------------------------------------------------------------------
# 10. TUCache rejects non-positive capacity
# ---------------------------------------------------------------------------


def test_invalid_capacity_raises() -> None:
    with pytest.raises(ValueError, match="capacity must be positive"):
        TUCache(capacity=0)

    with pytest.raises(ValueError, match="capacity must be positive"):
        TUCache(capacity=-1)


# ---------------------------------------------------------------------------
# 11. Cache miss when build_path is None vs a directory
# ---------------------------------------------------------------------------


def test_none_vs_directory_build_path_are_different_keys(tmp_path: Path) -> None:
    src = tmp_path / "y.cpp"
    src.write_text("int y;", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()

    tu_none, p_none = _make_fake_parser(MagicMock(name="TU_none"))
    tu_dir, p_dir = _make_fake_parser(MagicMock(name="TU_dir"))
    cache = TUCache(capacity=4)

    r_none, _ = cache.get_or_parse(src, None, _DEFAULT_FLAGS, p_none)
    r_dir, _ = cache.get_or_parse(src, build, _DEFAULT_FLAGS, p_dir)

    assert r_none is tu_none
    assert r_dir is tu_dir
    assert r_none is not r_dir
    p_none.assert_called_once()
    p_dir.assert_called_once()


# ---------------------------------------------------------------------------
# 12. clear() empties the cache
# ---------------------------------------------------------------------------


def test_clear_empties_cache(tmp_path: Path) -> None:
    src = tmp_path / "z.cpp"
    src.write_text("int z;", encoding="utf-8")

    cache = TUCache(capacity=4)
    _, parser = _make_fake_parser()

    cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)
    assert cache.stats()["cache_size"] == 1

    cache.clear()
    assert cache.stats()["cache_size"] == 0


# ---------------------------------------------------------------------------
# 13. hit_rate is 0.0 when no lookups have occurred
# ---------------------------------------------------------------------------


def test_initial_hit_rate_is_zero() -> None:
    cache = TUCache(capacity=8)
    stats = cache.stats()
    assert stats["cache_hit_rate"] == 0.0
    assert stats["hits"] == 0
    assert stats["misses"] == 0


# ---------------------------------------------------------------------------
# 14. Timing overlap: stats are consistent (no negative counts)
# ---------------------------------------------------------------------------


def test_stats_are_non_negative(tmp_path: Path) -> None:
    cache = TUCache(capacity=2)
    files = [tmp_path / f"f{i}.cpp" for i in range(5)]
    for f in files:
        f.write_text("int x;", encoding="utf-8")

    for f in files:
        _, p = _make_fake_parser()
        cache.get_or_parse(f, None, _DEFAULT_FLAGS, p)
        # Re-access each file to generate some hits
        cache.get_or_parse(f, None, _DEFAULT_FLAGS, p)

    s = cache.stats()
    assert s["hits"] >= 0
    assert s["misses"] >= 0
    assert s["evictions"] >= 0
    assert 0.0 <= float(s["cache_hit_rate"]) <= 1.0


# ---------------------------------------------------------------------------
# 15. stat time fixture: mtime equal → hit; mtime ahead by 1 ns → miss
# ---------------------------------------------------------------------------


def test_mtime_boundary_one_ns(tmp_path: Path) -> None:
    src = tmp_path / "ns.cpp"
    src.write_text("int ns;", encoding="utf-8")

    cache = TUCache(capacity=4)
    _, p1 = _make_fake_parser()
    cache.get_or_parse(src, None, _DEFAULT_FLAGS, p1)

    # Advance mtime by exactly 1 nanosecond.
    stat = os.stat(str(src))
    os.utime(str(src), ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))

    _, p2 = _make_fake_parser()
    cache.get_or_parse(src, None, _DEFAULT_FLAGS, p2)
    p2.assert_called_once()  # Should be a miss due to mtime change


# ---------------------------------------------------------------------------
# Performance guard: many sequential accesses don't accumulate
# ---------------------------------------------------------------------------


def test_sequential_hits_dont_grow_size(tmp_path: Path) -> None:
    src = tmp_path / "seq.cpp"
    src.write_text("void seq(){}", encoding="utf-8")

    cache = TUCache(capacity=4)
    _, parser = _make_fake_parser()

    for _ in range(50):
        cache.get_or_parse(src, None, _DEFAULT_FLAGS, parser)

    assert cache.stats()["cache_size"] == 1
    assert cache.stats()["hits"] == 49
    assert cache.stats()["misses"] == 1


# ---------------------------------------------------------------------------
# Thread interleaving guard: no duplicate misses when two threads race on miss
# (tests the lock-release-parse-reacquire pattern in TUCache)
# ---------------------------------------------------------------------------


def test_concurrent_miss_same_key(tmp_path: Path) -> None:
    """Two threads racing on the same key should both get a result."""
    import threading

    src = tmp_path / "race.cpp"
    src.write_text("void race(){}", encoding="utf-8")
    cache = TUCache(capacity=4)

    results: list[Any] = []
    lock = threading.Lock()

    def worker() -> None:
        _, p = _make_fake_parser(MagicMock(name="TU_race"))
        tu, _hit = cache.get_or_parse(src, None, _DEFAULT_FLAGS, p)
        with lock:
            results.append(tu)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 4
    # All results are non-None
    assert all(r is not None for r in results)
