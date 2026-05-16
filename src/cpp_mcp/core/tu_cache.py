"""Translation unit (TU) cache: OrderedDict LRU keyed by (file, build, flags_hash).

ADR-6 behavior:
  - Key: (realpath(file), realpath(build_path) or "", sha1(tuple(flags)))
  - Value: (TU, source_mtime_ns, flags_used, source_path)
  - Capacity: configurable; default 128.
  - Invalidation: poll source file mtime on every lookup; mismatch → evict + re-parse.
  - Thread safety: threading.Lock guards all dict mutations; lock is released before
    calling the parser and re-acquired for insertion.
  - Stats: size, capacity, hits, misses, evictions, hit_rate exposed via stats().
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

# The translation unit type is opaque (clang.cindex.TranslationUnit); use Any
# so tu_cache remains importable without libclang on the host.
TU = Any

_DEFAULT_CAPACITY = 128

# Parser callable type: (file_path, flags) -> TU
ParserFn = Callable[[Path, tuple[str, ...]], TU]


class _CacheKey(NamedTuple):
    file_realpath: str
    build_realpath: str  # "" when build_path is None
    flags_sha1: str


class _CacheEntry(NamedTuple):
    tu: TU
    source_mtime_ns: int
    flags_used: tuple[str, ...]
    source_path: Path


def _make_key(file_path: Path, build_path: Path | None, flags: tuple[str, ...]) -> _CacheKey:
    """Compute the canonical cache key per ADR-6."""
    file_real = os.path.realpath(str(file_path))
    build_real = os.path.realpath(str(build_path)) if build_path is not None else ""
    flags_hash = hashlib.sha1(repr(flags).encode()).hexdigest()
    return _CacheKey(file_realpath=file_real, build_realpath=build_real, flags_sha1=flags_hash)


class TUCache:
    """Thread-safe LRU cache for libclang TranslationUnit objects.

    Args:
        capacity: Maximum number of TU entries to retain. Oldest-used entry is
            evicted when the limit is reached. Default 128 (ADR-6).
    """

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError(f"TUCache capacity must be positive, got {capacity}")
        self._capacity = capacity
        self._store: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_parse(
        self,
        file_path: Path,
        build_path: Path | None,
        flags: tuple[str, ...],
        parser: ParserFn,
    ) -> tuple[TU, bool]:
        """Return a cached TU or invoke *parser* to produce one.

        On a cache hit the source file mtime is re-checked; a mtime mismatch
        evicts the stale entry and triggers a re-parse (counts as a miss).

        Args:
            file_path: Absolute path to the C++ source file.
            build_path: Absolute path to the build directory, or None.
            flags: Compiler flags tuple (used as part of the cache key).
            parser: Callable ``(file_path, flags) -> TU`` invoked on a cache miss.
                    Must NOT be called while the internal lock is held.

        Returns:
            A ``(tu, cache_hit)`` tuple where *cache_hit* is ``True`` when the TU
            was returned from cache without re-parsing.
        """
        key = _make_key(file_path, build_path, flags)
        source_path = Path(os.path.realpath(str(file_path)))

        # --- Check cache under lock ---
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                # Validate mtime before accepting the hit.
                try:
                    current_mtime = os.stat(str(source_path)).st_mtime_ns
                except OSError:
                    current_mtime = -1  # file gone → treat as stale

                if current_mtime == entry.source_mtime_ns:
                    # Cache hit: move to end (MRU position) and return.
                    self._store.move_to_end(key)
                    self._hits += 1
                    return entry.tu, True

                # Stale mtime: evict and fall through to re-parse.
                del self._store[key]
                self._evictions += 1

            self._misses += 1
            # Release lock before the (potentially slow) parse call.

        # --- Parse outside the lock ---
        new_tu = parser(source_path, flags)

        # Stat the file after parsing (best-effort; may differ if file changed
        # during parse, but that's the microsecond race documented in ADR-6).
        try:
            new_mtime = os.stat(str(source_path)).st_mtime_ns
        except OSError:
            new_mtime = 0

        new_entry = _CacheEntry(
            tu=new_tu,
            source_mtime_ns=new_mtime,
            flags_used=flags,
            source_path=source_path,
        )

        # --- Insert under lock, enforcing capacity ---
        with self._lock:
            # Evict LRU entries until we have room (another thread may have
            # inserted while we were parsing; re-check capacity).
            while len(self._store) >= self._capacity:
                self._store.popitem(last=False)  # pop LRU (oldest) end
                self._evictions += 1
            self._store[key] = new_entry
            self._store.move_to_end(key)  # ensure it is at MRU end

        return new_tu, False

    def invalidate(self, file_path: Path, build_path: Path | None = None) -> int:
        """Remove all cache entries matching *file_path* (and optionally *build_path*).

        Returns the number of entries removed.
        """
        file_real = os.path.realpath(str(file_path))
        build_real: str | None = (
            os.path.realpath(str(build_path)) if build_path is not None else None
        )

        to_remove: list[_CacheKey] = []
        with self._lock:
            for key in list(self._store.keys()):
                if key.file_realpath != file_real:
                    continue
                if build_real is not None and key.build_realpath != build_real:
                    continue
                to_remove.append(key)
            for key in to_remove:
                del self._store[key]
                self._evictions += 1
        return len(to_remove)

    def stats(self) -> dict[str, int | float]:
        """Return cache statistics per ADR-6 / US-10/AC-3.

        Keys:
            cache_size       — current number of entries.
            cache_capacity   — configured capacity.
            hits             — total cache hits since creation.
            misses           — total cache misses since creation.
            evictions        — total evictions (LRU overflow + mtime invalidation).
            cache_hit_rate   — hits / (hits + misses), or 0.0 if no lookups yet.
        """
        with self._lock:
            size = len(self._store)
            hits = self._hits
            misses = self._misses
            evictions = self._evictions

        total = hits + misses
        hit_rate: float = hits / total if total > 0 else 0.0
        return {
            "cache_size": size,
            "cache_capacity": self._capacity,
            "hits": hits,
            "misses": misses,
            "evictions": evictions,
            "cache_hit_rate": hit_rate,
        }

    def clear(self) -> None:
        """Remove all entries from the cache (for testing/teardown)."""
        with self._lock:
            self._store.clear()
