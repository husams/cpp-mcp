"""Tests for main() entry point behaviour (Story S2, US-M1).

Covers:
  - US-M1/AC-5 + SC_USM1_5b: ConfigError exits with rc=1, stderr non-empty,
    no traceback in stderr, stdout empty.
  - US-M1/AC-5 + SC_USM1_5a: stdin EOF exits with rc=0.

Tests use subprocess.Popen so that mcp.run() (blocking) can be exercised
without running an actual event loop inside pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _python() -> str:
    """Return the Python executable from the active venv."""
    return sys.executable


class TestMainConfigError:
    """US-M1/AC-5 + SC_USM1_5b: ConfigError -> rc=1, stderr, no Traceback, no stdout."""

    def test_main_exits_1_on_config_error_with_no_traceback(self, tmp_path: Path) -> None:
        env = {k: v for k, v in os.environ.items() if k != "CPP_MCP_ALLOWED_ROOTS"}

        result = subprocess.run(
            [_python(), "-m", "cpp_mcp"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1, (
            f"Expected rc=1, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.stderr.strip(), "Expected non-empty stderr on ConfigError"
        assert "Traceback" not in result.stderr, f"Traceback leaked to stderr: {result.stderr!r}"
        assert result.stdout == "", f"Expected empty stdout, got: {result.stdout!r}"

    def test_config_error_message_contains_roots_hint(self, tmp_path: Path) -> None:
        """ConfigError message should mention CPP_MCP_ALLOWED_ROOTS."""
        env = {k: v for k, v in os.environ.items() if k != "CPP_MCP_ALLOWED_ROOTS"}

        result = subprocess.run(
            [_python(), "-m", "cpp_mcp"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert "ALLOWED_ROOTS" in result.stderr or "CONFIG_ERROR" in result.stderr, (
            f"ConfigError hint missing from stderr: {result.stderr!r}"
        )


class TestMainStdinEOF:
    """US-M1/AC-5 + SC_USM1_5a: stdin EOF -> process exits with rc=0."""

    def test_main_exits_0_on_stdin_eof(self, tmp_path: Path) -> None:
        # Create a real allowed_root so ConfigError doesn't trigger first.
        root = tmp_path / "src"
        root.mkdir()

        env = dict(os.environ)
        env["CPP_MCP_ALLOWED_ROOTS"] = str(root)

        # Close stdin immediately; FastMCP stdio transport should exit cleanly.
        proc = subprocess.Popen(
            [_python(), "-m", "cpp_mcp"],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            # Pass empty bytes as stdin → immediate EOF to the server.
            _stdout, stderr = proc.communicate(input=b"", timeout=15)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.communicate()
            raise AssertionError("Process did not exit within 15s after stdin EOF") from exc

        assert proc.returncode == 0, (
            f"Expected rc=0 after stdin EOF, got {proc.returncode}. stderr={stderr.decode()!r}"
        )
