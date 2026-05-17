"""Unit tests for resolve_query_timeout_s (design §7).

Covers:
  - Default 30 when env var unset.
  - Valid integer in [1, 120]: returned as-is.
  - Values below 1: clamped to 1.
  - Values above 120: clamped to 120.
  - Non-integer env var: defaults to 30.
"""

from __future__ import annotations

import pytest


class TestResolveQueryTimeoutS:
    """Tests for core.query_config.resolve_query_timeout_s."""

    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", raising=False)
        from cpp_mcp.core.query_config import resolve_query_timeout_s

        assert resolve_query_timeout_s() == 30

    @pytest.mark.parametrize("value", [1, 30, 60, 120])
    def test_valid_value_returned(
        self, monkeypatch: pytest.MonkeyPatch, value: int
    ) -> None:
        monkeypatch.setenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", str(value))
        import importlib

        from cpp_mcp.core import query_config

        importlib.reload(query_config)
        assert query_config.resolve_query_timeout_s() == value

    @pytest.mark.parametrize("raw", ["0", "-10", "-1"])
    def test_below_minimum_clamped_to_1(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", raw)
        from cpp_mcp.core.query_config import resolve_query_timeout_s

        assert resolve_query_timeout_s() == 1

    @pytest.mark.parametrize("raw", ["121", "200", "9999"])
    def test_above_maximum_clamped_to_120(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", raw)
        from cpp_mcp.core.query_config import resolve_query_timeout_s

        assert resolve_query_timeout_s() == 120

    @pytest.mark.parametrize("raw", ["abc", "30.5", "", "none"])
    def test_non_integer_defaults_to_30(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", raw)
        from cpp_mcp.core.query_config import resolve_query_timeout_s

        assert resolve_query_timeout_s() == 30
