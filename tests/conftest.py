"""Root conftest.py: shared fixtures and libclang initialisation.

Attempts to configure libclang's shared library path from a list of known
system locations before any test imports clang.cindex. This is a no-op when
libclang is already on the dynamic-library search path (e.g. Linux with
system LLVM packages installed).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest_asyncio

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


# ---------------------------------------------------------------------------
# Session-scoped in-process MCP client (ADR-18 / S5)
# ---------------------------------------------------------------------------

# Absolute path to the C++ fixture repository used by integration tests.
_TEST_REPO_ROOT = str(Path(__file__).parent.parent / "test-repo")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mcp_client():  # type: ignore[return]
    """Session-scoped FastMCP client wired to an in-process build_server().

    ADR-18: uses ``fastmcp.Client(server_instance)`` — in-process transport,
    no subprocess, same event loop.  CPP_MCP_ALLOWED_ROOTS must be set before
    entering the Client context so that the lifespan's ``load_config()`` call
    succeeds.

    The env var is saved and restored so parallel test processes are not
    contaminated.
    """
    from fastmcp import Client

    from cpp_mcp.server.app import build_server

    prev = os.environ.get("CPP_MCP_ALLOWED_ROOTS")
    os.environ["CPP_MCP_ALLOWED_ROOTS"] = _TEST_REPO_ROOT
    try:
        server = build_server()
        async with Client(server) as client:
            yield client
    finally:
        if prev is None:
            os.environ.pop("CPP_MCP_ALLOWED_ROOTS", None)
        else:
            os.environ["CPP_MCP_ALLOWED_ROOTS"] = prev
