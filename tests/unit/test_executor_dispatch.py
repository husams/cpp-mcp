"""Unit tests verifying every tool dispatches work via session.executor.submit.

SC_USM7_2: each tool calls executor.submit exactly once per invocation so
libclang work is always confined to the single worker thread (ADR-7).

Strategy: call each tool's underlying function (`tool.fn`) with an explicit
``session`` that carries a spy on ``executor.submit``.  The spy returns a
``Future`` whose ``.result()`` returns a minimal success dict, so the tool
function completes without requiring libclang to be installed.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_future(value: Any) -> Future[Any]:
    """Return an already-resolved Future."""
    f: Future[Any] = Future()
    f.set_result(value)
    return f


def _make_session_spy() -> tuple[MagicMock, MagicMock]:
    """Return (session_mock, submit_spy).

    session_mock.executor.submit is configured as the spy.
    The spy returns a Future that resolves to a minimal dict so tool
    code that does ``.result()`` on the return value gets a valid payload.
    """
    submit_spy = MagicMock(
        side_effect=lambda *args, **kwargs: _make_future(
            {
                "definition_found": False,
                "file": None,
                "line": None,
                "col": None,
                "usr": "",
                "flags_source": "default",
                "cache_hit": False,
                "request_id": "spy",
                # extra keys tolerated by other tools
                "type_spelling": "",
                "canonical_spelling": "",
                "size_bytes": 0,
                "alignment_bytes": 0,
                "is_const": False,
                "is_volatile": False,
                "is_pointer": False,
                "references": [],
                "ast": {},
                "nodes": [],
                "edges": [],
                "includes": [],
                "symbols": [],
                "macros": [],
                "conditionals": [],
                "files_processed": 0,
                "nodes_written": 0,
                "edges_written": 0,
                "errors": [],
            }
        )
    )
    executor_mock = MagicMock()
    executor_mock.submit = submit_spy
    session_mock = MagicMock()
    session_mock.executor = executor_mock
    return session_mock, submit_spy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registered_tools() -> list[Any]:
    from cpp_mcp.server.app import build_server

    mcp = build_server()
    return asyncio.run(mcp.list_tools())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecutorDispatch:
    """SC_USM7_2: every registered tool submits work to session.executor once."""

    def _get_tool_fn(self, registered_tools: list[Any], name: str) -> Any:
        for t in registered_tools:
            if t.name == name:
                return t.fn
        raise KeyError(f"Tool {name!r} not found in registered tools")

    def test_cpp_get_definition_calls_executor_submit(self, registered_tools: list[Any]) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_get_definition")
        session, spy = _make_session_spy()
        fn(
            file_path="/tmp/fake.cpp",
            line=1,
            col=1,
            build_path=None,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
        )
        spy.assert_called_once()

    def test_cpp_get_references_calls_executor_submit(self, registered_tools: list[Any]) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_get_references")
        session, spy = _make_session_spy()
        fn(
            file_path="/tmp/fake.cpp",
            line=1,
            col=1,
            build_path=None,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
        )
        spy.assert_called_once()

    def test_cpp_get_type_info_calls_executor_submit(self, registered_tools: list[Any]) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_get_type_info")
        session, spy = _make_session_spy()
        fn(
            file_path="/tmp/fake.cpp",
            line=1,
            col=1,
            build_path=None,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
        )
        spy.assert_called_once()

    def test_cpp_get_ast_calls_executor_submit(self, registered_tools: list[Any]) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_get_ast")
        session, spy = _make_session_spy()
        fn(
            file_path="/tmp/fake.cpp",
            build_path=None,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
            ast_max_nodes=500,
            ast_max_bytes=65536,
        )
        spy.assert_called_once()

    def test_cpp_get_header_info_calls_executor_submit(self, registered_tools: list[Any]) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_get_header_info")
        session, spy = _make_session_spy()
        fn(
            file_path="/tmp/fake.cpp",
            build_path=None,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
        )
        spy.assert_called_once()

    def test_cpp_get_preprocessor_state_calls_executor_submit(
        self, registered_tools: list[Any]
    ) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_get_preprocessor_state")
        session, spy = _make_session_spy()
        fn(
            file_path="/tmp/fake.cpp",
            build_path=None,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
        )
        spy.assert_called_once()

    def test_cpp_export_to_graphdb_calls_executor_submit(self, registered_tools: list[Any]) -> None:
        fn = self._get_tool_fn(registered_tools, "cpp_export_to_graphdb")
        session, spy = _make_session_spy()
        fn(
            file_path_or_dir="/tmp/fake.cpp",
            build_path="/tmp/build",
            db_uri="bolt://localhost:7687",
            recursive=False,
            session=session,
            allowed_roots=("/tmp",),
            default_flags=("-std=c++17",),
        )
        spy.assert_called_once()
