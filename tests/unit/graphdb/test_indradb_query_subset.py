"""Unit tests for IndraDbQueryExecutor._dispatch_query (ADR-23 verb subset).

Tests:
  - Happy path: all 7 allowed verb shapes against a fake IndraDB client.
  - 3 unsupported verbs: QueryUnsupportedError.
  - 2 malformed-JSON cases: QueryParseError.
  - Bad 't' regex: QueryParseError.
  - Bad UUID: QueryParseError.
  - Missing / extra args: QueryParseError.
"""

from __future__ import annotations

import json
import sys
import uuid
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers: inject fake_indradb and build a pre-connected executor
# ---------------------------------------------------------------------------


def _make_executor_with_fake_client() -> Any:
    """Return an IndraDbQueryExecutor with a fake_indradb.Client wired in."""
    import tests.fixtures.fake_indradb as fake_indradb

    sys.modules["indradb"] = fake_indradb  # type: ignore[assignment]

    from cpp_mcp.graphdb.indradb_query_executor import IndraDbQueryExecutor

    executor = IndraDbQueryExecutor()
    # Bypass connect() — set client directly.
    executor._client = fake_indradb.Client()
    return executor, fake_indradb


def _populate_client(client: Any, fake: Any) -> dict[str, Any]:
    """Populate the fake client with a small graph for testing.

    Adds 2 vertices (Function, Variable) and 1 edge (DEFINES).
    Returns a dict with the known ids for assertions.
    """
    v1_id = uuid.uuid4()
    v2_id = uuid.uuid4()
    v1 = fake.Vertex(v1_id, "Function")
    v2 = fake.Vertex(v2_id, "Variable")
    client.create_vertex(v1)
    client.create_vertex(v2)
    client.set_properties(fake.SpecificVertexQuery(v1_id), name="name", value="main")
    client.set_properties(fake.SpecificVertexQuery(v2_id), name="name", value="x")
    edge = fake.Edge(outbound_id=v1_id, t="DEFINES", inbound_id=v2_id)
    client.create_edge(edge)
    return {"v1_id": v1_id, "v2_id": v2_id, "edge": edge}


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestAllowedVerbs:
    """All 7 ADR-23 verbs return results without error."""

    def _exec(self, query_str: str, row_limit: int = 200) -> list[dict[str, Any]]:
        executor, fake = _make_executor_with_fake_client()
        _populate_client(executor._client, fake)
        return executor._dispatch_query(query_str, row_limit)

    def test_all_vertices(self) -> None:
        rows = self._exec('{"query": "all_vertices", "args": {}}')
        assert len(rows) == 2
        assert all("id" in r and "t" in r and "properties" in r for r in rows)

    def test_all_edges(self) -> None:
        rows = self._exec('{"query": "all_edges", "args": {}}')
        assert len(rows) == 1
        assert "outbound_id" in rows[0] and "inbound_id" in rows[0]

    def test_vertex_with_type(self) -> None:
        rows = self._exec('{"query": "vertex_with_type", "args": {"t": "Function"}}')
        assert len(rows) == 1
        assert rows[0]["t"] == "Function"

    def test_edge_with_type(self) -> None:
        rows = self._exec('{"query": "edge_with_type", "args": {"t": "DEFINES"}}')
        assert len(rows) == 1
        assert rows[0]["t"] == "DEFINES"

    def test_vertex_with_property_equal(self) -> None:
        rows = self._exec(
            '{"query": "vertex_with_property_equal", "args": {"name": "name", "value": "main"}}'
        )
        assert len(rows) == 1

    def test_edge_with_property_equal_no_match(self) -> None:
        """edge_with_property_equal with no matching edges returns empty list."""
        rows = self._exec(
            '{"query": "edge_with_property_equal", "args": {"name": "weight", "value": 42}}'
        )
        assert rows == []

    def test_pipe_outbound(self) -> None:
        executor, fake = _make_executor_with_fake_client()
        info = _populate_client(executor._client, fake)
        query = json.dumps(
            {
                "query": "pipe",
                "args": {
                    "vertex_id": str(info["v1_id"]),
                    "direction": "outbound",
                    "t": "DEFINES",
                },
            }
        )
        rows = executor._dispatch_query(query, 200)
        assert len(rows) == 1
        assert rows[0]["id"] == str(info["v2_id"])

    def test_pipe_inbound(self) -> None:
        executor, fake = _make_executor_with_fake_client()
        info = _populate_client(executor._client, fake)
        query = json.dumps(
            {
                "query": "pipe",
                "args": {
                    "vertex_id": str(info["v2_id"]),
                    "direction": "inbound",
                },
            }
        )
        rows = executor._dispatch_query(query, 200)
        assert len(rows) == 1
        assert rows[0]["id"] == str(info["v1_id"])

    def test_row_limit_truncates(self) -> None:
        """row_limit=1 truncates all_vertices (2 items) to 1."""
        rows = self._exec('{"query": "all_vertices", "args": {}}', row_limit=1)
        assert len(rows) == 1

    def test_truncated_flag_set_on_execute(self) -> None:
        """execute() sets truncated=True when results were cut."""
        executor, fake = _make_executor_with_fake_client()
        _populate_client(executor._client, fake)
        result = executor.execute(
            query='{"query": "all_vertices", "args": {}}',
            parameters=None,
            row_limit=1,
            timeout_s=30,
        )
        assert result["truncated"] is True
        assert result["rows_returned"] == 1

    def test_not_truncated_when_all_fit(self) -> None:
        executor, fake = _make_executor_with_fake_client()
        _populate_client(executor._client, fake)
        result = executor.execute(
            query='{"query": "all_vertices", "args": {}}',
            parameters=None,
            row_limit=200,
            timeout_s=30,
        )
        assert result["truncated"] is False
        assert result["rows_returned"] == 2


# ---------------------------------------------------------------------------
# Unsupported verbs → QueryUnsupportedError
# ---------------------------------------------------------------------------


class TestUnsupportedVerbs:
    """Verbs outside the ADR-23 allowlist raise QueryUnsupportedError."""

    @pytest.mark.parametrize(
        "verb",
        ["all", "match", "cypher"],
    )
    def test_unsupported_verb_raises(self, verb: str) -> None:
        from cpp_mcp.core.error_envelope import QueryUnsupportedError

        executor, _fake = _make_executor_with_fake_client()
        query = json.dumps({"query": verb, "args": {}})
        with pytest.raises(QueryUnsupportedError, match="Unsupported query verb"):
            executor._dispatch_query(query, 200)


# ---------------------------------------------------------------------------
# Malformed JSON → QueryParseError
# ---------------------------------------------------------------------------


class TestMalformedJson:
    """Non-JSON or non-object inputs raise QueryParseError."""

    @pytest.mark.parametrize(
        "bad_input",
        [
            "not json at all",
            "MATCH (n) RETURN n",  # Cypher sent to IndraDB URI
        ],
    )
    def test_non_json_raises_parse_error(self, bad_input: str) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        with pytest.raises(QueryParseError, match="valid JSON"):
            executor._dispatch_query(bad_input, 200)

    def test_json_array_raises_parse_error(self) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        with pytest.raises(QueryParseError):
            executor._dispatch_query("[1, 2, 3]", 200)


# ---------------------------------------------------------------------------
# Bad 't' regex → QueryParseError
# ---------------------------------------------------------------------------


class TestBadTypeIdentifier:
    @pytest.mark.parametrize(
        "bad_t",
        ["123bad", "has space", "has-hyphen", "", "has.dot"],
    )
    def test_invalid_t_raises_parse_error(self, bad_t: str) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        query = json.dumps({"query": "vertex_with_type", "args": {"t": bad_t}})
        with pytest.raises(QueryParseError, match=r"Invalid type identifier|must match"):
            executor._dispatch_query(query, 200)


# ---------------------------------------------------------------------------
# Bad UUID → QueryParseError
# ---------------------------------------------------------------------------


class TestBadUuid:
    @pytest.mark.parametrize(
        "bad_id",
        ["not-a-uuid", "12345", "", "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"],
    )
    def test_invalid_uuid_raises_parse_error(self, bad_id: str) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        query = json.dumps(
            {"query": "pipe", "args": {"vertex_id": bad_id, "direction": "outbound"}}
        )
        with pytest.raises(QueryParseError):
            executor._dispatch_query(query, 200)


# ---------------------------------------------------------------------------
# Missing / extra args → QueryParseError
# ---------------------------------------------------------------------------


class TestArgValidation:
    def test_missing_required_arg_raises(self) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        # vertex_with_type requires 't'
        with pytest.raises(QueryParseError, match="Missing required args"):
            executor._dispatch_query('{"query": "vertex_with_type", "args": {}}', 200)

    def test_extra_arg_raises(self) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        # all_vertices takes no args
        with pytest.raises(QueryParseError, match="Unexpected args"):
            executor._dispatch_query('{"query": "all_vertices", "args": {"extra": "oops"}}', 200)

    def test_pipe_bad_direction_raises(self) -> None:
        from cpp_mcp.core.error_envelope import QueryParseError

        executor, _fake = _make_executor_with_fake_client()
        vid = str(uuid.uuid4())
        with pytest.raises(QueryParseError, match="direction"):
            executor._dispatch_query(
                json.dumps({"query": "pipe", "args": {"vertex_id": vid, "direction": "sideways"}}),
                200,
            )
