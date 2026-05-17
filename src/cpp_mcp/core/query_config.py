"""Query timeout configuration for graph query tools (design §7).

Reads ``CPP_MCP_QUERY_TIMEOUT_SECONDS`` from the environment, clamps to [1, 120],
and defaults to 30 when unset or non-integer.
"""

from __future__ import annotations

import os


def resolve_query_timeout_s() -> int:
    """Return the configured query timeout in seconds, clamped to [1, 120].

    Reads ``CPP_MCP_QUERY_TIMEOUT_SECONDS`` from the environment.

    - If unset or not a valid integer: defaults to 30.
    - If set to a value outside [1, 120]: clamps to the nearest boundary.

    Returns:
        Integer timeout in seconds in the range [1, 120].
    """
    raw = os.environ.get("CPP_MCP_QUERY_TIMEOUT_SECONDS", "30")
    try:
        v = int(raw)
    except ValueError:
        v = 30
    return max(1, min(120, v))
