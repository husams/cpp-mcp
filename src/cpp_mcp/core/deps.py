"""FastMCP dependency resolvers for tool injection.

ADR-3 (v2): dependency injection via FastMCP Depends().
All resolvers read from get_context().lifespan_context, which is populated
by app_lifespan in server/app.py yielding an AppLifespanContext dict.

Tools (added in S3) import these resolvers via:
    session: ClangSession = Depends(get_session)
    allowed_roots: tuple[str, ...] = Depends(get_allowed_roots)
    ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from fastmcp.server.dependencies import get_context

if TYPE_CHECKING:
    pass


class AppLifespanContext(TypedDict):
    """Shape of the dict yielded by app_lifespan to FastMCP lifespan_context."""

    session: Any  # ClangSession at runtime; Any to avoid circular import
    allowed_roots: tuple[str, ...]
    default_flags: tuple[str, ...]
    ast_max_nodes: int
    ast_max_bytes: int


def _lifespan_ctx() -> AppLifespanContext:
    """Read and return the lifespan context dict as AppLifespanContext."""
    raw: dict[str, Any] = get_context().lifespan_context
    # TypedDict is just a dict — cast for type-checker clarity
    return raw  # type: ignore[return-value]


def get_session() -> Any:
    """Resolve ClangSession from lifespan context."""
    return _lifespan_ctx()["session"]


def get_allowed_roots() -> tuple[str, ...]:
    """Resolve allowed_roots tuple from lifespan context."""
    return _lifespan_ctx()["allowed_roots"]


def get_default_flags() -> tuple[str, ...]:
    """Resolve default_flags tuple from lifespan context."""
    return _lifespan_ctx()["default_flags"]


def get_ast_max_nodes() -> int:
    """Resolve ast_max_nodes from lifespan context."""
    return _lifespan_ctx()["ast_max_nodes"]


def get_ast_max_bytes() -> int:
    """Resolve ast_max_bytes from lifespan context."""
    return _lifespan_ctx()["ast_max_bytes"]
