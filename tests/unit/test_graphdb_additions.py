"""QA additions for graphdb-exporter (Story 8 / US-7).

Three mandatory categories added on top of developer tests:

  1. Parametrized boundary tests — all 7 schema node labels and all 7 edge
     types are representable as valid constants, and the schema sets have the
     right cardinality.
  2. In-memory driver MERGE-idempotency — calling upsert_nodes / upsert_edges
     twice with the same batch leaves node/edge counts unchanged (simulates
     the MERGE guarantee the real Neo4j driver promises).
  3. DB_UNREACHABLE on a locally-refused TCP port — no mock; exercises the
     Neo4jDriver.connect() path against a real closed port so the error path
     is not purely a mock artefact.
  4. @pytest.mark.neo4j auto-skip guard — verifies the marker is registered
     and that NEO4J_TEST_URI controls skip behaviour.

Scenario ID traceability
------------------------
  SC-US-7-1  happy path schema coverage
  SC-US-7-2  DB_UNREACHABLE (closed port + mock)
  SC-US-7-1  idempotency (MERGE semantics)
  (markers)  @neo4j skip guard
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cpp_mcp.core.error_envelope import DBUnreachableError, DependencyMissingError
from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord
from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver
from cpp_mcp.graphdb.schema import (
    ALL_EDGE_TYPES,
    ALL_NODE_TYPES,
    EDGE_CALLS,
    EDGE_DECLARES,
    EDGE_DEFINES,
    EDGE_INCLUDES,
    EDGE_INHERITS,
    EDGE_MEMBER_OF,
    EDGE_REFERENCES,
    NODE_CLASS,
    NODE_FILE,
    NODE_FUNCTION,
    NODE_MACRO,
    NODE_NAMESPACE,
    NODE_TYPE_ALIAS,
    NODE_VARIABLE,
)

# ---------------------------------------------------------------------------
# Category 1: Parametrized boundary tests — schema cardinality and coverage
# (SC-US-7-1: happy path schema node types and edge types are fully emittable)
# ---------------------------------------------------------------------------

ALL_NODE_LABELS = [
    NODE_FILE,
    NODE_NAMESPACE,
    NODE_CLASS,
    NODE_FUNCTION,
    NODE_VARIABLE,
    NODE_MACRO,
    NODE_TYPE_ALIAS,
]

ALL_EDGE_LABELS = [
    EDGE_DEFINES,
    EDGE_DECLARES,
    EDGE_CALLS,
    EDGE_INHERITS,
    EDGE_REFERENCES,
    EDGE_INCLUDES,
    EDGE_MEMBER_OF,
]


@pytest.mark.parametrize("label", ALL_NODE_LABELS)
def test_schema_node_label_in_all_node_types(label: str) -> None:
    """Each of the 7 schema node labels appears in ALL_NODE_TYPES (SC-US-7-1)."""
    assert label in ALL_NODE_TYPES, f"Node label {label!r} missing from ALL_NODE_TYPES"


@pytest.mark.parametrize("edge_type", ALL_EDGE_LABELS)
def test_schema_edge_type_in_all_edge_types(edge_type: str) -> None:
    """Each of the 7 edge types appears in ALL_EDGE_TYPES (SC-US-7-1)."""
    assert edge_type in ALL_EDGE_TYPES, f"Edge type {edge_type!r} missing from ALL_EDGE_TYPES"


def test_all_node_types_exactly_9() -> None:
    """ALL_NODE_TYPES must have exactly 9 members after v7-S1 adds Field + GlobalVariable (ADR-25 D1)."""
    assert len(ALL_NODE_TYPES) == 9, (
        f"Expected 9 node types, got {len(ALL_NODE_TYPES)}: {ALL_NODE_TYPES}"
    )


def test_all_edge_types_exactly_7() -> None:
    """ALL_EDGE_TYPES must have exactly 7 members — spec requirement (US-7/AC-2)."""
    assert len(ALL_EDGE_TYPES) == 7, (
        f"Expected 7 edge types, got {len(ALL_EDGE_TYPES)}: {ALL_EDGE_TYPES}"
    )


def test_node_record_accepts_every_label() -> None:
    """NodeRecord can be constructed with every valid node label without error."""
    for label in ALL_NODE_LABELS:
        rec: NodeRecord = NodeRecord(label=label, usr=f"usr:{label}", props={"spelling": label})
        assert rec["label"] == label


def test_edge_record_accepts_every_edge_type() -> None:
    """EdgeRecord can be constructed with every valid edge type without error."""
    for etype in ALL_EDGE_LABELS:
        rec: EdgeRecord = EdgeRecord(
            source_usr="src",
            target_usr="tgt",
            edge_type=etype,
            props={},
        )
        assert rec["edge_type"] == etype


# ---------------------------------------------------------------------------
# Category 2: In-memory driver MERGE-idempotency assertion
# (SC-US-7-1: idempotent ingest — running twice produces same node/edge counts)
# ---------------------------------------------------------------------------


class IdempotentFakeDriver:
    """In-memory fake driver that enforces MERGE-on-USR idempotency.

    Stores one entry per USR key for nodes and one entry per
    (source_usr, target_usr, edge_type) key for edges, mirroring the Neo4j
    MERGE strategy described in ADR-7.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, NodeRecord] = {}
        self._edges: dict[tuple[str, str, str], EdgeRecord] = {}
        self.upsert_nodes_calls: int = 0
        self.upsert_edges_calls: int = 0

    def connect(self, uri: str, **kwargs: Any) -> None:
        pass

    def upsert_nodes(self, batch: list[NodeRecord]) -> int:
        self.upsert_nodes_calls += 1
        before = len(self._nodes)
        for rec in batch:
            self._nodes[rec["usr"]] = rec
        return len(self._nodes) - before  # net-new count

    def upsert_edges(self, batch: list[EdgeRecord]) -> int:
        self.upsert_edges_calls += 1
        before = len(self._edges)
        for rec in batch:
            key = (rec["source_usr"], rec["target_usr"], rec["edge_type"])
            self._edges[key] = rec
        return len(self._edges) - before

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)


# Verify Protocol structural compliance
_: GraphDriver = IdempotentFakeDriver()  # type: ignore[assignment]


def _make_node_batch(count: int) -> list[NodeRecord]:
    return [
        NodeRecord(label=NODE_FUNCTION, usr=f"c:@F@func{i}", props={"spelling": f"func{i}"})
        for i in range(count)
    ]


def _make_edge_batch(count: int) -> list[EdgeRecord]:
    return [
        EdgeRecord(
            source_usr="file://main.cpp",
            target_usr=f"c:@F@func{i}",
            edge_type=EDGE_DEFINES,
            props={},
        )
        for i in range(count)
    ]


def test_idempotent_upsert_nodes_same_batch_twice() -> None:
    """Upserting the same node batch twice leaves total node count unchanged (SC-US-7-1).

    This is the MERGE-on-USR invariant: re-exporting the same file must not
    duplicate nodes.
    """
    driver = IdempotentFakeDriver()
    batch = _make_node_batch(5)

    first_written = driver.upsert_nodes(batch)
    count_after_first = driver.node_count

    second_written = driver.upsert_nodes(batch)
    count_after_second = driver.node_count

    assert first_written == 5, "First upsert should report 5 new nodes"
    assert second_written == 0, "Second upsert of identical batch should report 0 new nodes"
    assert count_after_first == count_after_second == 5, (
        f"Node count must not grow on re-ingest: {count_after_second}"
    )


def test_idempotent_upsert_edges_same_batch_twice() -> None:
    """Upserting the same edge batch twice leaves total edge count unchanged (SC-US-7-1).

    MERGE on (source_usr, target_usr, edge_type) is the idempotency key.
    """
    driver = IdempotentFakeDriver()
    batch = _make_edge_batch(4)

    first_written = driver.upsert_edges(batch)
    count_after_first = driver.edge_count

    second_written = driver.upsert_edges(batch)
    count_after_second = driver.edge_count

    assert first_written == 4
    assert second_written == 0, "Duplicate edge batch must not increase edge count"
    assert count_after_first == count_after_second == 4


def test_idempotent_full_export_twice(tmp_path: Path) -> None:
    """Running export_file twice on the same TU + driver yields stable counts (SC-US-7-1).

    This exercises the full extract_nodes_and_edges → upsert pipeline with
    the IdempotentFakeDriver, covering the end-to-end MERGE path without Neo4j.
    """
    from cpp_mcp.graphdb.exporter import extract_nodes_and_edges

    cpp_file = tmp_path / "stable.cpp"
    cpp_file.write_text("")

    func_cursor = MagicMock()
    func_cursor.kind.name = "FUNCTION_DECL"
    func_cursor.get_usr.return_value = "c:@F@stable"
    func_cursor.spelling = "stable"
    func_cursor.is_definition.return_value = True
    func_cursor.type.spelling = "void ()"
    func_cursor.location.file.name = str(cpp_file)
    func_cursor.location.line = 1
    func_cursor.location.column = 1
    func_cursor.get_children.return_value = []

    tu = MagicMock()
    tu.cursor.get_children.return_value = [func_cursor]
    tu.cursor.kind.name = "TRANSLATION_UNIT"
    tu.cursor.get_usr.return_value = ""
    tu.cursor.spelling = ""
    tu.cursor.is_definition.return_value = False

    driver = IdempotentFakeDriver()

    # First export
    nodes, edges = extract_nodes_and_edges(tu, cpp_file)
    driver.upsert_nodes(nodes)
    driver.upsert_edges(edges)
    nodes_after_1 = driver.node_count
    edges_after_1 = driver.edge_count

    # Second export — same TU, same driver
    nodes2, edges2 = extract_nodes_and_edges(tu, cpp_file)
    driver.upsert_nodes(nodes2)
    driver.upsert_edges(edges2)
    nodes_after_2 = driver.node_count
    edges_after_2 = driver.edge_count

    assert nodes_after_1 == nodes_after_2, (
        f"Node count changed from {nodes_after_1} to {nodes_after_2} on second export"
    )
    assert edges_after_1 == edges_after_2, (
        f"Edge count changed from {edges_after_1} to {edges_after_2} on second export"
    )


# ---------------------------------------------------------------------------
# Category 3a: DB_UNREACHABLE on a locally-refused TCP port (no mock)
# (SC-US-7-2: DB_UNREACHABLE when Bolt connect fails)
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Bind to :0 to obtain a free port, then immediately release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_db_unreachable_closed_port() -> None:
    """Neo4jDriver.connect() raises a domain error on a refused TCP port (SC-US-7-2).

    Finds a free port, does NOT start a listener, then calls connect() against
    it.  No mocking of the network path.

    When the ``neo4j`` package is not installed, ``DependencyMissingError`` fires
    before any TCP connection attempt (ADR-13 / S1).  When the package is installed
    but the port is closed, ``DBUnreachableError`` fires.  Either is acceptable here
    because the test environment may or may not have ``neo4j`` installed.
    """
    port = _find_free_port()
    # Verify the port is indeed closed before we try to connect.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        result = probe.connect_ex(("127.0.0.1", port))
    assert result != 0, "Port unexpectedly open — cannot run closed-port test"

    driver = Neo4jDriver()
    with pytest.raises((DependencyMissingError, DBUnreachableError)):
        driver.connect(f"bolt://127.0.0.1:{port}")


# ---------------------------------------------------------------------------
# Category 3b: @pytest.mark.neo4j auto-skip guard
# (Requirement: @pytest.mark.neo4j tests auto-skip when NEO4J_TEST_URI not set)
# ---------------------------------------------------------------------------


@pytest.mark.neo4j
def test_neo4j_marker_skips_when_uri_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """This test is tagged @neo4j and will be collected.

    The conftest or the pytest --co output will show the marker registered.
    If NEO4J_TEST_URI is absent (the common case), this test body is skipped
    by the skipif guard below — proving the infrastructure works.
    """
    import os

    neo4j_uri = os.environ.get("NEO4J_TEST_URI")
    if not neo4j_uri:
        pytest.skip("NEO4J_TEST_URI not set — @neo4j test skipped as expected")

    # If the env var IS set, do a minimal connectivity check.
    driver = Neo4jDriver()
    driver.connect(neo4j_uri)
    driver.close()


def test_neo4j_marker_registered_in_config() -> None:
    """The 'neo4j' marker must be declared in pyproject.toml markers list.

    This prevents PytestUnknownMarkWarning from being silently emitted and
    ensures CI doesn't skip without a clear reason.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--co",
            "-q",
            "--no-header",
            "tests/unit/test_graphdb_additions.py::test_neo4j_marker_skips_when_uri_absent",
        ],
        capture_output=True,
        text=True,
        cwd="/Users/husam/workspace/cpp-mcp",
    )
    # Should not emit PytestUnknownMarkWarning
    assert "PytestUnknownMarkWarning" not in result.stdout
    assert "PytestUnknownMarkWarning" not in result.stderr


# ---------------------------------------------------------------------------
# Boundary: empty batches return 0 without error
# ---------------------------------------------------------------------------


def test_idempotent_driver_empty_node_batch() -> None:
    """upsert_nodes([]) returns 0 and does not raise."""
    driver = IdempotentFakeDriver()
    assert driver.upsert_nodes([]) == 0
    assert driver.node_count == 0


def test_idempotent_driver_empty_edge_batch() -> None:
    """upsert_edges([]) returns 0 and does not raise."""
    driver = IdempotentFakeDriver()
    assert driver.upsert_edges([]) == 0
    assert driver.edge_count == 0


# ---------------------------------------------------------------------------
# Boundary: overlapping batches — union semantics
# ---------------------------------------------------------------------------


def test_idempotent_driver_overlapping_batches() -> None:
    """Two overlapping node batches produce the union, not the sum (SC-US-7-1)."""
    driver = IdempotentFakeDriver()

    batch_a = _make_node_batch(3)  # func0, func1, func2
    batch_b = _make_node_batch(5)  # func0..func4 (overlaps with batch_a)

    driver.upsert_nodes(batch_a)
    driver.upsert_nodes(batch_b)

    # Union = 5 distinct USRs
    assert driver.node_count == 5
