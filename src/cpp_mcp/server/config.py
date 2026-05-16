"""Server configuration: parses environment variables at startup.

Required:
  CPP_MCP_ALLOWED_ROOTS — colon-separated list of absolute directory paths.

Optional (with defaults):
  CPP_MCP_DEFAULT_FLAGS   — space-separated; tokenized via shlex.split.
                            Default: "-std=c++20 -I. -x c++"
  CPP_MCP_CACHE_CAPACITY  — positive integer. Default: 128.
  CPP_MCP_AST_MAX_NODES   — positive integer. Default: 5000.
  CPP_MCP_AST_MAX_BYTES   — positive integer. Default: 1048576 (1 MiB).

Raises ConfigError (a subclass of Exception) if validation fails.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass

from cpp_mcp.core.error_envelope import ConfigError

_DEFAULT_FLAGS = "-std=c++20 -I. -x c++"
_DEFAULT_CACHE_CAPACITY = 128
_DEFAULT_AST_MAX_NODES = 5000
_DEFAULT_AST_MAX_BYTES = 1_048_576


@dataclass(frozen=True)
class ServerConfig:
    """Immutable server configuration parsed from environment variables."""

    allowed_roots: tuple[str, ...]
    default_flags: tuple[str, ...]
    cache_capacity: int
    ast_max_nodes: int
    ast_max_bytes: int


def _parse_positive_int(value: str, var_name: str) -> int:
    """Parse *value* as a positive integer; raise ConfigError on failure."""
    try:
        parsed = int(value)
    except ValueError:
        raise ConfigError(
            f"CONFIG_ERROR: {var_name} must be a positive integer, got {value!r}"
        ) from None
    if parsed <= 0:
        raise ConfigError(f"CONFIG_ERROR: {var_name} must be positive, got {parsed}")
    return parsed


def load_config(env: dict[str, str] | None = None) -> ServerConfig:
    """Parse environment variables and return a frozen :class:`ServerConfig`.

    Args:
        env: Optional mapping to use instead of ``os.environ`` (for testing).

    Raises:
        ConfigError: ``CPP_MCP_ALLOWED_ROOTS`` is unset, empty, contains a
            non-absolute path, or contains a path that does not exist.
    """
    source = env if env is not None else dict(os.environ)

    # --- CPP_MCP_ALLOWED_ROOTS (required) ---
    raw_roots = source.get("CPP_MCP_ALLOWED_ROOTS", "").strip()
    if not raw_roots:
        raise ConfigError("CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS is required")

    roots: list[str] = []
    for entry in raw_roots.split(":"):
        entry = entry.strip()
        if not entry:
            continue
        if not os.path.isabs(entry):
            raise ConfigError(
                f"CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS entry is not absolute: {entry!r}"
            )
        if not os.path.isdir(entry):
            raise ConfigError(
                f"CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS entry does not exist or is not a"
                f" directory: {entry!r}"
            )
        roots.append(entry)

    if not roots:
        raise ConfigError("CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS contained no valid entries")

    # --- CPP_MCP_DEFAULT_FLAGS (optional) ---
    raw_flags = source.get("CPP_MCP_DEFAULT_FLAGS", _DEFAULT_FLAGS)
    default_flags: tuple[str, ...] = tuple(shlex.split(raw_flags))

    # --- CPP_MCP_CACHE_CAPACITY (optional) ---
    raw_cap = source.get("CPP_MCP_CACHE_CAPACITY", str(_DEFAULT_CACHE_CAPACITY))
    cache_capacity = _parse_positive_int(raw_cap, "CPP_MCP_CACHE_CAPACITY")

    # --- CPP_MCP_AST_MAX_NODES (optional) ---
    raw_nodes = source.get("CPP_MCP_AST_MAX_NODES", str(_DEFAULT_AST_MAX_NODES))
    ast_max_nodes = _parse_positive_int(raw_nodes, "CPP_MCP_AST_MAX_NODES")

    # --- CPP_MCP_AST_MAX_BYTES (optional) ---
    raw_bytes = source.get("CPP_MCP_AST_MAX_BYTES", str(_DEFAULT_AST_MAX_BYTES))
    ast_max_bytes = _parse_positive_int(raw_bytes, "CPP_MCP_AST_MAX_BYTES")

    return ServerConfig(
        allowed_roots=tuple(roots),
        default_flags=default_flags,
        cache_capacity=cache_capacity,
        ast_max_nodes=ast_max_nodes,
        ast_max_bytes=ast_max_bytes,
    )
