"""Root conftest.py: shared fixtures and libclang initialisation.

Attempts to configure libclang's shared library path from a list of known
system locations before any test imports clang.cindex. This is a no-op when
libclang is already on the dynamic-library search path (e.g. Linux with
system LLVM packages installed).
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# libclang auto-discovery
# ---------------------------------------------------------------------------

_LIBCLANG_CANDIDATES: list[str] = [
    # macOS Xcode (default toolchain)
    "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib",
    # macOS Xcode (Frameworks — older layout)
    "/Applications/Xcode.app/Contents/Frameworks",
    # macOS Swift Playgrounds (secondary)
    "/Applications/Swift Playground.app/Contents/Developer/Toolchains/"
    "XcodeDefault.xctoolchain/usr/lib",
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
            return
        except Exception:
            continue  # Try next candidate.


_configure_libclang()
