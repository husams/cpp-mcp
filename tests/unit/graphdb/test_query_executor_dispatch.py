"""Unit tests for select_executor URI-scheme dispatch (design §3.1).

Covers:
  - Neo4j schemes return Neo4jQueryExecutor.
  - IndraDB schemes return IndraDbQueryExecutor.
  - Unknown schemes raise InvalidArgumentError.
  - Empty / schemeless URIs raise InvalidArgumentError.
"""

from __future__ import annotations

import pytest


class TestSelectExecutorDispatch:
    """select_executor returns the right type per URI scheme."""

    @pytest.mark.parametrize(
        "uri",
        [
            "bolt://localhost:7687",
            "bolt+s://localhost:7687",
            "bolt+ssc://localhost:7687",
            "neo4j://localhost:7687",
            "neo4j+s://localhost:7687",
            "neo4j+ssc://localhost:7687",
        ],
    )
    def test_neo4j_schemes_return_neo4j_executor(self, uri: str) -> None:
        from cpp_mcp.graphdb.neo4j_query_executor import Neo4jQueryExecutor
        from cpp_mcp.graphdb.query_executor import select_executor

        result = select_executor(uri)
        assert isinstance(result, Neo4jQueryExecutor), (
            f"Expected Neo4jQueryExecutor for {uri!r}, got {type(result).__name__}"
        )

    @pytest.mark.parametrize(
        "uri",
        [
            "indradb://localhost:27615",
            "grpc://localhost:27615",
            "indradb+grpc://localhost:27615",
        ],
    )
    def test_indradb_schemes_return_indradb_executor(self, uri: str) -> None:
        from cpp_mcp.graphdb.indradb_query_executor import IndraDbQueryExecutor
        from cpp_mcp.graphdb.query_executor import select_executor

        result = select_executor(uri)
        assert isinstance(result, IndraDbQueryExecutor), (
            f"Expected IndraDbQueryExecutor for {uri!r}, got {type(result).__name__}"
        )

    @pytest.mark.parametrize(
        "uri",
        [
            "redis://localhost:6379",
            "postgres://localhost:5432",
            "http://localhost:8080",
            "ftp://example.com",
        ],
    )
    def test_unknown_scheme_raises_invalid_argument(self, uri: str) -> None:
        from cpp_mcp.core.error_envelope import InvalidArgumentError
        from cpp_mcp.graphdb.query_executor import select_executor

        with pytest.raises(InvalidArgumentError, match="Unsupported db_uri scheme"):
            select_executor(uri)

    @pytest.mark.parametrize(
        "uri",
        [
            "",
            "localhost:7687",
            "bolt-without-slashes",
        ],
    )
    def test_missing_scheme_raises_invalid_argument(self, uri: str) -> None:
        from cpp_mcp.core.error_envelope import InvalidArgumentError
        from cpp_mcp.graphdb.query_executor import select_executor

        with pytest.raises(InvalidArgumentError):
            select_executor(uri)
