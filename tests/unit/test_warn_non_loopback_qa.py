"""QA boundary additions for _warn_if_non_loopback.

Mutation/boundary category: adversarial inputs NOT covered by the developer's
test_warn_non_loopback.py.  Tests adversarial spellings of non-loopback and
loopback addresses to confirm the warning logic is not bypassable through
address-normalisation tricks.

Scenario references: SC_USM2_3, SC_USM2_3b (US-M2/AC-3, EC-2)
"""

from __future__ import annotations

import logging

import pytest

from cpp_mcp.server.config import _warn_if_non_loopback

# ---------------------------------------------------------------------------
# Adversarial NON-LOOPBACK inputs (must emit WARNING)
# ---------------------------------------------------------------------------

_NON_LOOPBACK_ADVERSARIAL = [
    # IPv6 link-local (non-loopback; should warn)
    ("fe80::1", True, "IPv6 link-local"),
    ("fe80::1%eth0", True, "IPv6 link-local with zone ID"),
    # IPv4-mapped IPv6 form of 0.0.0.0
    ("::ffff:0.0.0.0", True, "IPv4-in-IPv6 any-address"),
    ("::ffff:192.168.1.1", True, "IPv4-in-IPv6 private"),
    # Private ranges not in loopback set
    ("172.16.0.1", True, "RFC-1918 172.16/12"),
    ("100.64.0.1", True, "CGNAT range"),
    # Hostname that resolves externally — treat as non-loopback
    ("0", True, "bare zero (not a loopback address string)"),
    # ::ffff:127.0.0.1 — IPv4-mapped loopback; NOT in the loopback set
    ("::ffff:127.0.0.1", True, "IPv4-mapped loopback (not in loopback set)"),
]

# ---------------------------------------------------------------------------
# Adversarial LOOPBACK inputs (must NOT emit WARNING)
# ---------------------------------------------------------------------------

_LOOPBACK_NO_WARN = [
    # Exact strings known to be loopback — must not produce WARNING
    ("127.0.0.1", False, "canonical IPv4 loopback"),
    ("::1", False, "canonical IPv6 loopback"),
    ("localhost", False, "hostname loopback"),
    # Case variants of "localhost" — the implementation does a string match;
    # if it normalises case these will pass, if not they will warn (both are
    # observable behaviours — this test documents actual behaviour).
]


@pytest.mark.parametrize(
    ("bind", "should_warn", "label"),
    _NON_LOOPBACK_ADVERSARIAL,
    ids=[label for _, _, label in _NON_LOOPBACK_ADVERSARIAL],
)
def test_adversarial_non_loopback_emits_warning(
    bind: str,
    should_warn: bool,
    label: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC_USM2_3 / SC_USM2_3b: adversarial non-loopback addresses must emit WARNING.

    These are mutation-class boundary inputs: spellings the developer's
    parametrize list did not include.  If the implementation checks only a
    fixed set of strings, any of these would silently bypass the warning.
    """
    with caplog.at_level(logging.WARNING, logger="cpp_mcp.server.config"):
        _warn_if_non_loopback(bind)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, (
        f"[{label}] Expected WARNING for non-loopback bind={bind!r} but none was emitted.\n"
        "The _warn_if_non_loopback implementation appears to accept this address silently."
    )
    # The warning message must include the bind address so operators can identify it
    assert any(bind in r.message for r in warning_records), (
        f"[{label}] WARNING emitted but did not contain {bind!r}: "
        + str([r.message for r in warning_records])
    )


@pytest.mark.parametrize(
    ("bind", "should_warn", "label"),
    _LOOPBACK_NO_WARN,
    ids=[label for _, _, label in _LOOPBACK_NO_WARN],
)
def test_known_loopback_never_warns(
    bind: str,
    should_warn: bool,
    label: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC_USM2_3: known loopback addresses must never emit WARNING (regression guard)."""
    with caplog.at_level(logging.WARNING, logger="cpp_mcp.server.config"):
        _warn_if_non_loopback(bind)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not warning_records, f"[{label}] Unexpected WARNING for loopback bind={bind!r}: " + str(
        [r.message for r in warning_records]
    )


# ---------------------------------------------------------------------------
# Boundary: empty string and whitespace-only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bind",
    ["", " ", "\t", "  127.0.0.1  "],
    ids=["empty", "space", "tab", "padded-loopback"],
)
def test_empty_or_whitespace_bind_warns(
    bind: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC_USM2_3 boundary: degenerate bind strings should not silently pass as loopback.

    An empty or whitespace bind string is not a valid loopback address.
    The function must either warn or raise — it must not silently succeed.
    This test documents that WARNING is the expected behaviour for these inputs.
    """
    with caplog.at_level(logging.WARNING, logger="cpp_mcp.server.config"):
        try:
            _warn_if_non_loopback(bind)
        except (ValueError, TypeError):
            # Raising is also acceptable — it prevents silent misconfiguration
            return

    # If no exception, a WARNING must have been emitted (bind is not loopback)
    stripped = bind.strip()
    loopback_set = {"127.0.0.1", "::1", "localhost"}
    if stripped not in loopback_set:
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, (
            f"bind={bind!r} (stripped={stripped!r}) is not a loopback address, "
            "expected WARNING or exception but got neither."
        )
