"""Error envelope: closed ErrorCode enum, build_error(), and wrap_tool() decorator.

ADR-8: envelope shape is fixed; partial success goes in payload, not envelope.
Message sanitizer ensures no internal paths or tracebacks leak to callers.
"""

from __future__ import annotations

import functools
import inspect
import re
import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Regex matching absolute-path-shaped substrings (POSIX: starts with /).
_ABS_PATH_RE = re.compile(r"/[^\s,\"']+")


class ErrorCode(StrEnum):
    """Closed enum of all error codes emitted by this server (ADR-8)."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INVALID_POSITION = "INVALID_POSITION"
    INVALID_RANGE = "INVALID_RANGE"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PATH_VIOLATION = "PATH_VIOLATION"
    DB_UNREACHABLE = "DB_UNREACHABLE"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    PARSE_ERROR = "PARSE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Domain exceptions  (imported and caught by wrap_tool)
# ---------------------------------------------------------------------------


class PathViolationError(Exception):
    """Raised when a caller-supplied path fails the allowed-roots check."""


class FileNotFoundError_(Exception):
    """Raised post-validation when a validated path does not exist on disk.

    Named with a trailing underscore to avoid shadowing the built-in, but
    wrap_tool catches both this and the built-in FileNotFoundError.
    """


class InvalidPositionError(Exception):
    """Raised when line/col is out of range for the given file."""


class InvalidRangeError(Exception):
    """Raised when start_line > end_line (or similar range inversion)."""


class InvalidArgumentError(Exception):
    """Raised for invalid argument values (e.g. build_path is a file)."""


class DBUnreachableError(Exception):
    """Raised when the graph database cannot be reached."""


class DependencyMissingError(Exception):
    """Raised when an optional Python package required for a backend is not importable.

    Message MUST include the install command so operators know exactly what to run.
    """


class FatalParseError(Exception):
    """Raised when libclang returns zero AST nodes with fatal diagnostics."""


class ConfigError(Exception):
    """Raised at startup when required configuration is missing or invalid."""


# ---------------------------------------------------------------------------
# Message sanitizer
# ---------------------------------------------------------------------------


def _sanitize_message(message: str, echo: tuple[str, ...]) -> str:
    """Replace internal absolute paths not echoed from the caller with <redacted>.

    Only static strings, error codes, and caller-supplied values (echo) are
    allowed in outbound messages per ADR-8.
    """

    def _replace(m: re.Match[str]) -> str:
        candidate = m.group(0)
        # Keep if this path was explicitly provided by the caller.
        for allowed in echo:
            if candidate == allowed or candidate.startswith(allowed):
                return candidate
        return "<redacted>"

    return _ABS_PATH_RE.sub(_replace, message)


# ---------------------------------------------------------------------------
# build_error
# ---------------------------------------------------------------------------


def build_error(
    code: ErrorCode,
    message: str,
    tool: str,
    request_id: str,
    echo: tuple[str, ...] = (),
) -> dict[str, str]:
    """Construct a sanitized error envelope dict per ADR-8.

    Args:
        code: One of the closed ErrorCode values.
        message: Human-readable message (will be sanitized).
        tool: Name of the MCP tool that failed.
        request_id: UUID4 hex string for log correlation.
        echo: Caller-supplied path strings safe to include verbatim.

    Returns:
        Dict matching the wire shape ``{code, message, tool, request_id}``.
    """
    return {
        "code": str(code),
        "message": _sanitize_message(message, echo),
        "tool": tool,
        "request_id": request_id,
    }


# ---------------------------------------------------------------------------
# wrap_tool decorator
# ---------------------------------------------------------------------------

# Maps exception types to their ErrorCode.
_EXC_TO_CODE: list[tuple[type[BaseException], ErrorCode]] = [
    (PathViolationError, ErrorCode.PATH_VIOLATION),
    (InvalidPositionError, ErrorCode.INVALID_POSITION),
    (InvalidRangeError, ErrorCode.INVALID_RANGE),
    (InvalidArgumentError, ErrorCode.INVALID_ARGUMENT),
    (DependencyMissingError, ErrorCode.DEPENDENCY_MISSING),
    (DBUnreachableError, ErrorCode.DB_UNREACHABLE),
    (FatalParseError, ErrorCode.PARSE_ERROR),
    # Built-in FileNotFoundError catches both built-in and post-validation paths.
    (FileNotFoundError, ErrorCode.FILE_NOT_FOUND),
    (FileNotFoundError_, ErrorCode.FILE_NOT_FOUND),
]


def wrap_tool(tool_name: str) -> Callable[[Callable[P, R]], Callable[P, Any]]:
    """Decorator factory: wraps a tool callable with error-envelope handling.

    Generates a ``request_id`` per invocation, catches all known domain
    exceptions and maps them to their ErrorCode, and maps any other exception
    to INTERNAL_ERROR (sanitized; no traceback leaked to caller).

    Supports both synchronous and asynchronous wrapped functions. When the
    decorated function is a coroutine function (``async def``), the returned
    wrapper is also a coroutine function so that exceptions raised inside the
    ``await`` are properly caught and converted to the error envelope instead of
    propagating as raw tracebacks.

    Usage::

        @wrap_tool("cpp_get_definition")
        async def cpp_get_definition(**kwargs: Any) -> dict[str, Any]:
            ...
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, Any]:
        def _make_envelope(exc: BaseException, echo: tuple[str, ...], request_id: str) -> Any:
            for exc_type, code in _EXC_TO_CODE:
                if isinstance(exc, exc_type):
                    return build_error(
                        code,
                        str(exc),
                        tool_name,
                        request_id,
                        echo=echo,
                    )
            import logging

            logging.getLogger(__name__).error(
                "Unhandled exception in tool %s [%s]: %r",
                tool_name,
                request_id,
                exc,
                exc_info=True,
            )
            return build_error(
                ErrorCode.INTERNAL_ERROR,
                "An internal error occurred.",
                tool_name,
                request_id,
                echo=echo,
            )

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                request_id = uuid.uuid4().hex
                echo: tuple[str, ...] = tuple(
                    v for v in kwargs.values() if isinstance(v, str) and v.startswith("/")
                )
                try:
                    return await fn(*args, **kwargs)
                except BaseException as exc:
                    return _make_envelope(exc, echo, request_id)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            request_id = uuid.uuid4().hex
            echo = tuple(v for v in kwargs.values() if isinstance(v, str) and v.startswith("/"))
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                return _make_envelope(exc, echo, request_id)

        return sync_wrapper

    return decorator
