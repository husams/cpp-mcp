"""Unit tests for _warn_if_non_loopback() in server/config.py.

Verifies that WARNING is emitted for non-loopback bind addresses and
suppressed for loopback addresses. (US-M2/AC-3, EC-2, design §4.5)
"""

from __future__ import annotations

import logging

import pytest

from cpp_mcp.server.config import _warn_if_non_loopback


@pytest.mark.parametrize(
    ("bind", "warns"),
    [
        ("127.0.0.1", False),
        ("::1", False),
        ("localhost", False),
        ("0.0.0.0", True),
        ("::", True),
        ("192.168.1.10", True),
        ("10.0.0.1", True),
    ],
)
def test_warn_if_non_loopback(bind: str, warns: bool, caplog: pytest.LogCaptureFixture) -> None:
    """WARNING is emitted iff bind address is not in loopback set."""
    with caplog.at_level(logging.WARNING, logger="cpp_mcp.server.config"):
        _warn_if_non_loopback(bind)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    if warns:
        assert warning_records, f"Expected WARNING for bind={bind!r} but none was emitted"
        # The warning message must mention the bind address
        assert any(bind in r.message for r in warning_records), (
            f"WARNING message did not contain bind address {bind!r}: "
            + str([r.message for r in warning_records])
        )
    else:
        assert not warning_records, f"Unexpected WARNING for loopback bind={bind!r}: " + str(
            [r.message for r in warning_records]
        )
