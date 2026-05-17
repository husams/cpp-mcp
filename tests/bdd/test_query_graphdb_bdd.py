"""BDD step-definitions for v6 query_graphdb + describe_graph_schema scenarios.

Covers scenarios from tests/bdd/features/query_graphdb.feature which maps to:
  scenarios.md AC-Q1-1, AC-Q1-4..AC-Q1-10, AC-Q2-8, OQ-Q1-2, OQ-Q2-1

All scenarios run without a live daemon (fake_indradb or monkeypatching).
Live-daemon scenarios are in tests/integration/.
"""

from __future__ import annotations

import importlib
import sys
import types
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

import tests.fixtures.fake_indradb as _fake_indradb_module

scenarios("features/query_graphdb.feature")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_fake_indradb_sys_module() -> types.ModuleType:
    """Return a minimal sys.modules["indradb"] shim backed by fake_indradb."""
    mod = types.ModuleType("indradb")
    for attr in (
        "Client",
        "Vertex",
        "Edge",
        "Identifier",
        "NamedProperty",
        "VertexProperties",
        "EdgeProperties",
        "SpecificVertexQuery",
        "SpecificEdgeQuery",
        "BulkInserter",
        "AllVertexQuery",
        "AllEdgeQuery",
        "VertexWithPropertyValueQuery",
        "EdgeWithPropertyValueQuery",
        "PipeQuery",
    ):
        setattr(mod, attr, getattr(_fake_indradb_module, attr, None))
    return mod


def _make_executor() -> tuple[Any, Any]:
    """Return (IndraDbQueryExecutor, fake_indradb_module) with a fake client."""
    fake_mod = _make_fake_indradb_sys_module()
    sys.modules["indradb"] = fake_mod  # type: ignore[assignment]
    from cpp_mcp.graphdb.indradb_query_executor import IndraDbQueryExecutor

    executor = IndraDbQueryExecutor()
    executor._client = _fake_indradb_module.Client()
    return executor, _fake_indradb_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def executor_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    """Attach an executor + fake module to the shared ctx bag."""
    exec_, fake = _make_executor()
    ctx["executor"] = exec_
    ctx["fake"] = fake
    return ctx


@pytest.fixture()
def dispatch_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    """Attach an executor for dispatch tests to the shared ctx bag."""
    exec_, fake = _make_executor()
    ctx["executor"] = exec_
    ctx["fake"] = fake
    ctx["raised"] = None
    return ctx


# ---------------------------------------------------------------------------
# Given steps — executor / fake client setup
# ---------------------------------------------------------------------------


@given("an IndraDB executor backed by the fake client", target_fixture="executor_ctx")
def given_indradb_executor_fake(ctx: dict[str, Any]) -> dict[str, Any]:
    exec_, fake = _make_executor()
    ctx["executor"] = exec_
    ctx["fake"] = fake
    ctx["raised"] = None
    return ctx


@given(parsers.parse("{n:d} Function vertices are inserted into the fake client"))
def given_function_vertices(n: int, executor_ctx: dict[str, Any]) -> None:
    fake = executor_ctx["fake"]
    client = executor_ctx["executor"]._client
    for _ in range(n):
        client.create_vertex(fake.Vertex(uuid.uuid4(), "Function"))


@given(parsers.parse("{n:d} Namespace vertices are inserted into the fake client"))
def given_namespace_vertices(n: int, executor_ctx: dict[str, Any]) -> None:
    fake = executor_ctx["fake"]
    client = executor_ctx["executor"]._client
    for _ in range(n):
        client.create_vertex(fake.Vertex(uuid.uuid4(), "Namespace"))


# ---------------------------------------------------------------------------
# Given steps — env var setup
# ---------------------------------------------------------------------------


@given(
    parsers.parse('the env var CPP_MCP_QUERY_TIMEOUT_SECONDS is set to "{value}"'),
    target_fixture="ctx",
)
def given_timeout_env_set(
    value: str, monkeypatch: pytest.MonkeyPatch, ctx: dict[str, Any]
) -> dict[str, Any]:
    monkeypatch.setenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", value)
    return ctx


@given(
    "the env var CPP_MCP_QUERY_TIMEOUT_SECONDS is unset",
    target_fixture="ctx",
)
def given_timeout_env_unset(
    monkeypatch: pytest.MonkeyPatch, ctx: dict[str, Any]
) -> dict[str, Any]:
    monkeypatch.delenv("CPP_MCP_QUERY_TIMEOUT_SECONDS", raising=False)
    return ctx


# ---------------------------------------------------------------------------
# Given steps — module / server setup
# ---------------------------------------------------------------------------


@given(
    "the module cpp_mcp.graphdb.indradb_query_executor is imported with fake indradb",
    target_fixture="ctx",
)
def given_executor_module_imported(ctx: dict[str, Any]) -> dict[str, Any]:
    fake_mod = _make_fake_indradb_sys_module()
    sys.modules["indradb"] = fake_mod  # type: ignore[assignment]
    import cpp_mcp.graphdb.indradb_query_executor as m

    ctx["executor_module"] = m
    return ctx


@given("the MCP server is built via build_server", target_fixture="ctx")
def given_mcp_server_built(ctx: dict[str, Any]) -> dict[str, Any]:
    from cpp_mcp.server.app import build_server

    ctx["mcp"] = build_server()
    return ctx


@given(
    parsers.parse(
        'an IndraDB schema introspector with a fake client containing a File vertex'
        ' stamped with schema version "{version}"'
    ),
    target_fixture="ctx",
)
def given_schema_introspector_stale(version: str, ctx: dict[str, Any]) -> dict[str, Any]:
    vid = uuid.uuid4()

    class _NamedProp:
        def __init__(self, name: str, value: Any) -> None:
            self.name = name
            self.value = value

    class _Vertex:
        def __init__(self, _id: uuid.UUID, t: str) -> None:
            self.id = _id
            self.t = t

    class _VertexProps:
        def __init__(self, vertex: _Vertex, props: list[_NamedProp]) -> None:
            self.vertex = vertex
            self.props = props

    class _PropertiesQuery:
        def __init__(self, source: Any) -> None:
            self.source = source

    class _SpecificVQ:
        def __init__(self, _vid: uuid.UUID) -> None:
            self.vid = _vid
            self.vids = [_vid]

        def properties(self) -> _PropertiesQuery:
            return _PropertiesQuery(self)

    class _AllVertexQ:
        pass

    _AllVertexQ.__name__ = "AllVertexQuery"
    _AllVertexQ.__qualname__ = "AllVertexQuery"

    class _AllEdgeQ:
        pass

    _AllEdgeQ.__name__ = "AllEdgeQuery"
    _AllEdgeQ.__qualname__ = "AllEdgeQuery"

    file_vertex = _Vertex(vid, "File")
    file_props = [_NamedProp("schema_version", version)]

    class _FakeClient:
        def ping(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get(self, query: Any) -> list[list[Any]]:
            if isinstance(query, _PropertiesQuery):
                if isinstance(query.source, _SpecificVQ):
                    return [[_VertexProps(file_vertex, file_props)]]
                return [[]]
            if hasattr(query, "__class__") and query.__class__.__name__ == "AllVertexQuery":
                return [[file_vertex]]
            if hasattr(query, "__class__") and query.__class__.__name__ == "AllEdgeQuery":
                return [[]]
            return [[]]

    fake_client = _FakeClient()
    fake_mod = types.ModuleType("indradb")
    fake_mod.AllVertexQuery = _AllVertexQ  # type: ignore[attr-defined]
    fake_mod.AllEdgeQuery = _AllEdgeQ  # type: ignore[attr-defined]

    class _ClientCls:
        def __new__(cls, *args: Any, **kwargs: Any) -> Any:
            return fake_client

    fake_mod.Client = _ClientCls  # type: ignore[attr-defined]
    fake_mod.SpecificVertexQuery = _SpecificVQ  # type: ignore[attr-defined]

    ctx["fake_client"] = fake_client
    ctx["fake_mod"] = fake_mod
    ctx["stale_version"] = version
    return ctx


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when("I execute all_vertices with no row_limit override (default 200)")
def when_execute_all_vertices_default(executor_ctx: dict[str, Any]) -> None:
    result = executor_ctx["executor"].execute(
        query='{"query": "all_vertices", "args": {}}',
        parameters=None,
        row_limit=200,
        timeout_s=30,
    )
    executor_ctx["result"] = result


@when(parsers.parse("I execute all_vertices with row_limit {limit:d}"))
def when_execute_all_vertices_with_limit(limit: int, executor_ctx: dict[str, Any]) -> None:
    result = executor_ctx["executor"].execute(
        query='{"query": "all_vertices", "args": {}}',
        parameters=None,
        row_limit=limit,
        timeout_s=30,
    )
    executor_ctx["result"] = result


@when(parsers.parse('I dispatch the query string "{query_str}"'))
def when_dispatch_query(query_str: str, executor_ctx: dict[str, Any]) -> None:
    from cpp_mcp.core.error_envelope import QueryParseError, QueryUnsupportedError

    try:
        executor_ctx["executor"]._dispatch_query(query_str, 200)
        executor_ctx["raised"] = None
    except (QueryParseError, QueryUnsupportedError) as exc:
        executor_ctx["raised"] = exc


@when("I dispatch the unsupported verb query")
def when_dispatch_unsupported_verb(executor_ctx: dict[str, Any]) -> None:
    import json as _json

    from cpp_mcp.core.error_envelope import QueryParseError, QueryUnsupportedError

    bad_query = _json.dumps({"query": "shortest_path", "args": {"from": "v1", "to": "v2"}})
    try:
        executor_ctx["executor"]._dispatch_query(bad_query, 200)
        executor_ctx["raised"] = None
    except (QueryParseError, QueryUnsupportedError) as exc:
        executor_ctx["raised"] = exc


@when("the server resolves the effective timeout")
def when_resolve_timeout(ctx: dict[str, Any]) -> None:
    from cpp_mcp.core import query_config

    importlib.reload(query_config)
    ctx["resolved_timeout"] = query_config.resolve_query_timeout_s()


@when("the module namespace is inspected for set_ or delete symbols")
def when_inspect_module(ctx: dict[str, Any]) -> None:
    m = ctx["executor_module"]
    ctx["write_symbols"] = [n for n in dir(m) if n.startswith(("set_", "delete"))]


@when("the tool registry is inspected")
def when_inspect_tool_registry(ctx: dict[str, Any]) -> None:
    import asyncio

    tools = asyncio.run(ctx["mcp"].list_tools())
    ctx["tool_names"] = [t.name for t in tools]


@when("describe is called on the introspector")
def when_describe_introspector(ctx: dict[str, Any]) -> None:
    from cpp_mcp.graphdb.schema_introspector import IndraDbSchemaIntrospector

    with patch.dict(sys.modules, {"indradb": ctx["fake_mod"]}):
        introspector = IndraDbSchemaIntrospector()
        introspector._client = ctx["fake_client"]
        ctx["describe_result"] = introspector.describe(sample_size=10)


# ---------------------------------------------------------------------------
# Then steps — row_limit / truncation
# ---------------------------------------------------------------------------


@then(parsers.parse("rows_returned equals {n:d}"))
def then_rows_returned_equals(n: int, executor_ctx: dict[str, Any]) -> None:
    assert executor_ctx["result"]["rows_returned"] == n


@then("truncated is false")
def then_truncated_false(executor_ctx: dict[str, Any]) -> None:
    assert executor_ctx["result"]["truncated"] is False


@then("truncated is true")
def then_truncated_true(executor_ctx: dict[str, Any]) -> None:
    assert executor_ctx["result"]["truncated"] is True


@then(parsers.parse("the rows list has length {n:d}"))
def then_rows_length(n: int, executor_ctx: dict[str, Any]) -> None:
    assert len(executor_ctx["result"]["rows"]) == n


@then("the result does not contain a code key")
def then_no_code_key(executor_ctx: dict[str, Any]) -> None:
    assert "code" not in executor_ctx["result"], (
        "Must not return an error envelope on truncation"
    )


# ---------------------------------------------------------------------------
# Then steps — dispatch errors
# ---------------------------------------------------------------------------


@then(parsers.parse('a QueryParseError is raised matching "{fragment}"'))
def then_query_parse_error(fragment: str, executor_ctx: dict[str, Any]) -> None:
    from cpp_mcp.core.error_envelope import QueryParseError

    exc = executor_ctx["raised"]
    assert exc is not None, "Expected QueryParseError to be raised, but no exception was raised"
    assert isinstance(exc, QueryParseError), (
        f"Expected QueryParseError, got {type(exc).__name__}"
    )
    assert fragment in str(exc), f"Expected {fragment!r} in exception message: {exc!r}"


@then(parsers.parse('a QueryUnsupportedError is raised matching "{fragment}"'))
def then_query_unsupported_error(fragment: str, executor_ctx: dict[str, Any]) -> None:
    from cpp_mcp.core.error_envelope import QueryUnsupportedError

    exc = executor_ctx["raised"]
    assert exc is not None, "Expected QueryUnsupportedError to be raised, but none raised"
    assert isinstance(exc, QueryUnsupportedError), (
        f"Expected QueryUnsupportedError, got {type(exc).__name__}"
    )
    assert fragment in str(exc), f"Expected {fragment!r} in exception message: {exc!r}"


# ---------------------------------------------------------------------------
# Then steps — timeout
# ---------------------------------------------------------------------------


@then(parsers.parse("the effective timeout is {n:d} second"))
def then_timeout_seconds_singular(n: int, ctx: dict[str, Any]) -> None:
    assert ctx["resolved_timeout"] == n


@then(parsers.parse("the effective timeout is {n:d} seconds"))
def then_timeout_seconds_plural(n: int, ctx: dict[str, Any]) -> None:
    assert ctx["resolved_timeout"] == n


# ---------------------------------------------------------------------------
# Then steps — module purity
# ---------------------------------------------------------------------------


@then("no such write symbols are present")
def then_no_write_symbols(ctx: dict[str, Any]) -> None:
    write_symbols = ctx["write_symbols"]
    assert write_symbols == [], (
        f"IndraDB query executor exports write symbols: {write_symbols}"
    )


# ---------------------------------------------------------------------------
# Then steps — tool registration
# ---------------------------------------------------------------------------


@then(parsers.parse("exactly {n:d} tools are registered"))
def then_exactly_n_tools(n: int, ctx: dict[str, Any]) -> None:
    tool_names = ctx["tool_names"]
    assert len(tool_names) == n, f"Expected {n} tools, got {len(tool_names)}: {tool_names}"


@then(parsers.parse("the tool named {name} is present"))
def then_tool_present(name: str, ctx: dict[str, Any]) -> None:
    assert name in ctx["tool_names"], f"Tool {name!r} not found in: {ctx['tool_names']}"


@then(parsers.parse("no registered tool name starts with {prefix}"))
def then_no_prefix(prefix: str, ctx: dict[str, Any]) -> None:
    prefixed = [n for n in ctx["tool_names"] if n.startswith(prefix)]
    assert prefixed == [], f"Tools with {prefix!r} prefix found: {prefixed}"


# ---------------------------------------------------------------------------
# Then steps — schema version mismatch
# ---------------------------------------------------------------------------


@then("the notes list contains a string indicating schema version mismatch")
def then_notes_mismatch(ctx: dict[str, Any]) -> None:
    from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

    result = ctx["describe_result"]
    stale = ctx["stale_version"]
    notes = result.get("notes", [])
    mismatch_notes = [
        n
        for n in notes
        if "mismatch" in n.lower()
        or stale in n
        or "schema_version" in n.lower()
        or "schema version" in n.lower()
    ]
    assert mismatch_notes, (
        f"Expected schema-version mismatch note; SCHEMA_VERSION={SCHEMA_VERSION!r}, "
        f"stale={stale!r}, notes={notes!r}"
    )
