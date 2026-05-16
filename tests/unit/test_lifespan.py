"""Tests for app_lifespan + AppLifespanContext (Story S2, US-M6).

Covers:
  - US-M6/AC-1: lifespan constructs AppLifespanContext with correct keys.
  - US-M6/AC-2 + EC-4: lifespan teardown calls session.aclose(); executor is shut down.
  - US-M6/AC-5 + EC-11: CPP_MCP_ALLOWED_ROOTS unset raises ConfigError inside lifespan.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture()
def allowed_root(tmp_path: Path) -> str:
    root = tmp_path / "src"
    root.mkdir()
    return str(root)


class TestLifespanConstructsContext:
    """US-M6/AC-1: lifespan yields an AppLifespanContext with expected keys."""

    def test_lifespan_yields_all_context_keys(self, allowed_root: str) -> None:
        from fastmcp import FastMCP

        from cpp_mcp.server.app import app_lifespan

        mcp = FastMCP("cpp-mcp-test")

        async def run() -> dict[str, Any]:
            async with app_lifespan(mcp) as ctx:
                return dict(ctx)  # AppLifespanContext is a TypedDict (dict)

        env = {
            "CPP_MCP_ALLOWED_ROOTS": allowed_root,
            "CPP_MCP_CACHE_CAPACITY": "4",
        }
        with patch.dict("os.environ", env, clear=False):
            result = asyncio.run(run())

        assert "session" in result
        assert "allowed_roots" in result
        assert "default_flags" in result
        assert "ast_max_nodes" in result
        assert "ast_max_bytes" in result

    def test_lifespan_allowed_roots_matches_env(self, allowed_root: str) -> None:
        from fastmcp import FastMCP

        from cpp_mcp.server.app import app_lifespan

        mcp = FastMCP("cpp-mcp-test")

        async def run() -> tuple[str, ...]:
            async with app_lifespan(mcp) as ctx:
                return ctx["allowed_roots"]  # type: ignore[index]

        env = {"CPP_MCP_ALLOWED_ROOTS": allowed_root}
        with patch.dict("os.environ", env, clear=False):
            roots = asyncio.run(run())

        assert allowed_root in roots

    def test_lifespan_session_is_clang_session(self, allowed_root: str) -> None:
        from fastmcp import FastMCP

        from cpp_mcp.core.clang_session import ClangSession
        from cpp_mcp.server.app import app_lifespan

        mcp = FastMCP("cpp-mcp-test")

        async def run() -> Any:
            async with app_lifespan(mcp) as ctx:
                return ctx["session"]  # type: ignore[index]

        env = {"CPP_MCP_ALLOWED_ROOTS": allowed_root}
        with patch.dict("os.environ", env, clear=False):
            session = asyncio.run(run())

        assert isinstance(session, ClangSession)


class TestLifespanTeardown:
    """US-M6/AC-2 + EC-4: lifespan teardown calls session.aclose()."""

    def test_aclose_called_on_normal_exit(self, allowed_root: str) -> None:
        from fastmcp import FastMCP

        from cpp_mcp.core.clang_session import ClangSession
        from cpp_mcp.server.app import app_lifespan

        mcp = FastMCP("cpp-mcp-test")
        aclose_called = []

        original_init = ClangSession.__init__

        def patched_init(self: ClangSession, capacity: int = 128) -> None:
            original_init(self, capacity=capacity)
            original_aclose = self.aclose

            async def spy_aclose() -> None:
                aclose_called.append(True)
                await original_aclose()

            self.aclose = spy_aclose  # type: ignore[method-assign]

        async def run() -> None:
            async with app_lifespan(mcp):
                pass  # normal exit

        env = {"CPP_MCP_ALLOWED_ROOTS": allowed_root}
        with (
            patch.object(ClangSession, "__init__", patched_init),
            patch.dict("os.environ", env, clear=False),
        ):
            asyncio.run(run())

        assert aclose_called, "aclose() was not called during lifespan teardown"

    def test_aclose_called_even_on_exception(self, allowed_root: str) -> None:
        """EC-4: executor drains even if an exception escapes the lifespan body."""
        from fastmcp import FastMCP

        from cpp_mcp.core.clang_session import ClangSession
        from cpp_mcp.server.app import app_lifespan

        mcp = FastMCP("cpp-mcp-test")
        aclose_called = []

        original_init = ClangSession.__init__

        def patched_init(self: ClangSession, capacity: int = 128) -> None:
            original_init(self, capacity=capacity)
            original_aclose = self.aclose

            async def spy_aclose() -> None:
                aclose_called.append(True)
                await original_aclose()

            self.aclose = spy_aclose  # type: ignore[method-assign]

        async def run() -> None:
            with pytest.raises(RuntimeError, match="simulated failure"):
                async with app_lifespan(mcp):
                    raise RuntimeError("simulated failure")

        env = {"CPP_MCP_ALLOWED_ROOTS": allowed_root}
        with (
            patch.object(ClangSession, "__init__", patched_init),
            patch.dict("os.environ", env, clear=False),
        ):
            asyncio.run(run())

        assert aclose_called, "aclose() not called when lifespan body raised"


class TestLifespanConfigError:
    """US-M6/AC-5 + EC-11: missing CPP_MCP_ALLOWED_ROOTS raises ConfigError."""

    def test_lifespan_raises_config_error_when_roots_unset(self) -> None:
        from fastmcp import FastMCP

        from cpp_mcp.core.error_envelope import ConfigError
        from cpp_mcp.server.app import app_lifespan

        mcp = FastMCP("cpp-mcp-test")

        async def run() -> None:
            async with app_lifespan(mcp):
                pass

        # Remove CPP_MCP_ALLOWED_ROOTS entirely
        env_without_roots: dict[str, str] = {}
        with (
            patch.dict("os.environ", env_without_roots, clear=True),
            pytest.raises(ConfigError, match="CPP_MCP_ALLOWED_ROOTS"),
        ):
            asyncio.run(run())
