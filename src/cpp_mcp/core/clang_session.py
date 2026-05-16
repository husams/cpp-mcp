"""ClangSession: single libclang worker thread behind asyncio.

ADR-2: All libclang parse() calls run on exactly one background thread
(ThreadPoolExecutor(max_workers=1)) so the asyncio event loop stays responsive.

The shared clang.cindex.Index is created lazily at first parse so that modules
that never parse do not trigger the libclang shared-library load.

libclang auto-discovery (Story 3 follow-up #2): on import, this module
replicates the candidate-path logic from tests/conftest.py so that server
startup configures libclang automatically from common system locations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from cpp_mcp.core.tu_cache import TUCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# libclang auto-discovery
# ---------------------------------------------------------------------------

_LIBCLANG_CANDIDATES: list[str] = [
    # macOS Xcode (default toolchain)
    "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib",
    # macOS Xcode (Frameworks — older layout)
    "/Applications/Xcode.app/Contents/Frameworks",
    # macOS Swift Playgrounds (secondary)
    (
        "/Applications/Swift Playground.app/Contents/Developer/Toolchains/"
        "XcodeDefault.xctoolchain/usr/lib"
    ),
    # Homebrew LLVM (Apple Silicon)
    "/opt/homebrew/opt/llvm/lib",
    # Homebrew LLVM (Intel)
    "/usr/local/opt/llvm/lib",
    # Linux system LLVM (common distro paths)
    "/usr/lib/llvm-19/lib",
    "/usr/lib/llvm-18/lib",
    "/usr/lib/llvm-17/lib",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib",
]

# Allow callers to override via environment variable (useful in CI).
_env_override = os.environ.get("CPP_MCP_LIBCLANG_PATH", "")
if _env_override:
    _LIBCLANG_CANDIDATES.insert(0, _env_override)


def _configure_libclang() -> None:
    """Try each candidate directory until libclang can be loaded, then stop."""
    try:
        import clang.cindex as ci
    except ImportError:
        return  # clang Python package not installed; nothing to do.

    for candidate in _LIBCLANG_CANDIDATES:
        if not Path(candidate).is_dir():
            continue
        dylibs = list(Path(candidate).glob("libclang*.dylib")) + list(
            Path(candidate).glob("libclang*.so*")
        )
        if not dylibs:
            continue
        try:
            ci.Config.set_library_path(candidate)
            # Trigger an actual load to confirm the path works.
            ci.Index.create()
            logger.debug("libclang configured from %s", candidate)
            return
        except Exception:
            continue  # Try next candidate.


# Run auto-discovery at import time (no-op if libclang is already on LD path).
_configure_libclang()


# ---------------------------------------------------------------------------
# ClangSession
# ---------------------------------------------------------------------------


class ClangSession:
    """Singleton-like session owning the libclang Index and TU cache.

    Concurrency model (ADR-2):
      - One ``ThreadPoolExecutor(max_workers=1)`` serializes all parse calls.
      - The asyncio event loop dispatches blocking work via ``run_in_executor``.
      - TU cache mutations are guarded by a ``threading.Lock`` inside TUCache.
      - The libclang ``Index`` is created once and reused; it is NOT thread-safe
        for concurrent parse calls, which the single-worker executor prevents.

    Usage::

        session = ClangSession(capacity=128)
        tu = await session.parse(Path("src/main.cpp"), Path("build"), ("-std=c++20",))
    """

    def __init__(self, capacity: int = 128) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clang-worker")
        self._index_lock = threading.Lock()
        self._index: Any = None  # clang.cindex.Index; created lazily
        self._cache = TUCache(capacity=capacity)

    # ------------------------------------------------------------------
    # Private helpers (all run on the single worker thread)
    # ------------------------------------------------------------------

    def _get_or_create_index(self) -> Any:
        """Return the shared Index, creating it on first call (worker thread only)."""
        with self._index_lock:
            if self._index is None:
                import clang.cindex as ci

                self._index = ci.Index.create()
            return self._index

    def _parse_sync(self, file_path: Path, flags: tuple[str, ...], options: int = 0) -> Any:
        """Synchronous parse; MUST be called only from the single worker thread."""
        index = self._get_or_create_index()
        if options:
            return index.parse(str(file_path), list(flags), options=options)
        return index.parse(str(file_path), list(flags))

    def _get_or_parse_sync(
        self,
        file_path: Path,
        build_path: Path | None,
        flags: tuple[str, ...],
        options: int = 0,
    ) -> tuple[Any, bool]:
        """Lookup cache then parse if needed; runs on the single worker thread.

        Returns:
            ``(tu, cache_hit)`` — same semantics as :meth:`TUCache.get_or_parse`.
        """
        # When extra parse options are requested (e.g. PARSE_DETAILED_PROCESSING_RECORD
        # for macro cursors), we use a flags key that encodes the options so entries
        # with different options occupy separate cache slots.
        effective_flags = flags if not options else (*flags, f"__options={options}")
        parser = lambda p, f: self._parse_sync(  # noqa: E731
            p,
            tuple(x for x in f if not x.startswith("__options=")),
            options,
        )
        return self._cache.get_or_parse(file_path, build_path, effective_flags, parser)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def parse(
        self,
        file_path: Path,
        build_path: Path | None,
        flags: tuple[str, ...],
        options: int = 0,
    ) -> tuple[Any, bool]:
        """Async entry point: dispatch parse/cache lookup to the worker thread.

        Args:
            file_path: Absolute path to the C++ source file.
            build_path: Absolute path to the build directory, or None.
            flags: Compiler flags tuple.
            options: Optional libclang parse options bitfield (e.g.
                ``TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD`` to include
                macro-definition cursors).  Entries parsed with different options
                occupy separate TU cache slots.  Default 0 (no extra options).

        Returns:
            ``(tu, cache_hit)`` — the TranslationUnit and whether it was a cache hit.
        """
        loop = asyncio.get_running_loop()
        result: tuple[Any, bool] = await loop.run_in_executor(
            self._executor,
            lambda: self._get_or_parse_sync(file_path, build_path, flags, options),
        )
        return result

    @property
    def executor(self) -> ThreadPoolExecutor:
        """Return the single-worker executor (ADR-7: tool handlers submit work here)."""
        return self._executor

    def cache_stats(self) -> dict[str, int | float]:
        """Return TU cache statistics (delegates to TUCache.stats())."""
        return self._cache.stats()

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the worker thread pool. Call at server exit."""
        self._executor.shutdown(wait=wait)

    async def aclose(self) -> None:
        """Async shutdown: drain the executor and clear the TU cache.

        Called by app_lifespan finally block (ADR-7, US-M6/AC-2).
        Waits for any in-flight work to finish before clearing state.
        """
        self._executor.shutdown(wait=True)
        self._cache.clear()
