"""Unit tests for IndraDBDriver insert-only counting semantics (ADR-17, S3).

Runs entirely against fake_indradb — no daemon required.

Scenarios covered:
  - First upsert of N nodes returns N (all inserts).
  - Second upsert of identical nodes returns 0 (idempotent; ADR-17).
  - First upsert of N edges returns N (all inserts).
  - Second upsert of identical edges returns 0 (idempotent; ADR-17).
  - Mixed new + duplicate nodes: only new ones counted.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest

import tests.fixtures.fake_indradb as _fake_mod
from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord
from cpp_mcp.graphdb.indradb_driver import IndraDBDriver


def _make_fake_module() -> types.ModuleType:
    """Build a fake 'indradb' sys.modules entry from the fake_indradb fixtures."""
    mod = types.ModuleType("indradb")
    mod.Client = _fake_mod.Client  # type: ignore[attr-defined]
    mod.Vertex = _fake_mod.Vertex  # type: ignore[attr-defined]
    mod.Edge = _fake_mod.Edge  # type: ignore[attr-defined]
    mod.Identifier = _fake_mod.Identifier  # type: ignore[attr-defined]
    mod.SpecificVertexQuery = _fake_mod.SpecificVertexQuery  # type: ignore[attr-defined]
    mod.SpecificEdgeQuery = _fake_mod.SpecificEdgeQuery  # type: ignore[attr-defined]
    mod.BulkInserter = _fake_mod.BulkInserter  # type: ignore[attr-defined]
    return mod


@contextmanager
def _fake_indradb_context() -> Generator[tuple[IndraDBDriver, _fake_mod.Client], None, None]:
    """Context manager: installs fake indradb, connects a driver, yields (driver, client).

    The fake module stays in sys.modules for the entire lifetime of the context so
    that the lazy ``import indradb`` inside upsert_nodes / upsert_edges resolves to
    the fake, not the real package (which may not be installed).
    """
    fake_mod = _make_fake_module()
    old = sys.modules.get("indradb")
    sys.modules["indradb"] = fake_mod  # type: ignore[assignment]
    try:
        driver = IndraDBDriver()
        driver.connect("indradb://localhost:27615")
        client: _fake_mod.Client = driver._client
        yield driver, client
    finally:
        if old is None:
            sys.modules.pop("indradb", None)
        else:
            sys.modules["indradb"] = old


def _node(usr: str, label: str = "Function", **props: Any) -> NodeRecord:
    return NodeRecord(label=label, usr=usr, props=dict(props))


def _edge(src: str, tgt: str, etype: str = "CALLS") -> EdgeRecord:
    return EdgeRecord(source_usr=src, target_usr=tgt, edge_type=etype, props={})


class TestUpsertNodesInsertCount:
    def test_first_upsert_returns_n(self) -> None:
        with _fake_indradb_context() as (driver, client):
            batch = [_node("usr::a"), _node("usr::b"), _node("usr::c")]
            count = driver.upsert_nodes(batch)
            assert count == 3
            assert client.node_count == 3

    def test_second_upsert_returns_zero(self) -> None:
        """Idempotent re-upsert of identical nodes must return 0 (ADR-17)."""
        with _fake_indradb_context() as (driver, client):
            batch = [_node("usr::a"), _node("usr::b")]
            driver.upsert_nodes(batch)
            second_count = driver.upsert_nodes(batch)
            assert second_count == 0
            assert client.node_count == 2  # store unchanged

    def test_mixed_new_and_existing_counts_only_new(self) -> None:
        with _fake_indradb_context() as (driver, client):
            driver.upsert_nodes([_node("usr::a")])
            batch2 = [_node("usr::a"), _node("usr::b")]
            count = driver.upsert_nodes(batch2)
            assert count == 1  # only usr::b is new
            assert client.node_count == 2

    def test_empty_batch_returns_zero(self) -> None:
        with _fake_indradb_context() as (driver, _):
            assert driver.upsert_nodes([]) == 0


class TestUpsertEdgesInsertCount:
    def test_first_upsert_returns_n(self) -> None:
        with _fake_indradb_context() as (driver, client):
            # Nodes must exist first for property writes to have targets.
            driver.upsert_nodes([_node("usr::a"), _node("usr::b"), _node("usr::c")])
            batch = [_edge("usr::a", "usr::b"), _edge("usr::b", "usr::c")]
            count = driver.upsert_edges(batch)
            assert count == 2
            assert client.edge_count == 2

    def test_second_upsert_returns_zero(self) -> None:
        """Idempotent re-upsert of identical edges must return 0 (ADR-17)."""
        with _fake_indradb_context() as (driver, client):
            driver.upsert_nodes([_node("usr::a"), _node("usr::b")])
            batch = [_edge("usr::a", "usr::b")]
            driver.upsert_edges(batch)
            second_count = driver.upsert_edges(batch)
            assert second_count == 0
            assert client.edge_count == 1  # store unchanged

    def test_mixed_new_and_existing_counts_only_new(self) -> None:
        with _fake_indradb_context() as (driver, client):
            driver.upsert_nodes([_node("usr::a"), _node("usr::b"), _node("usr::c")])
            driver.upsert_edges([_edge("usr::a", "usr::b")])
            batch2 = [_edge("usr::a", "usr::b"), _edge("usr::b", "usr::c")]
            count = driver.upsert_edges(batch2)
            assert count == 1  # only usr::b->usr::c is new
            assert client.edge_count == 2

    def test_empty_batch_returns_zero(self) -> None:
        with _fake_indradb_context() as (driver, _):
            assert driver.upsert_edges([]) == 0


@pytest.mark.parametrize(
    "node_batch,edge_batch,expected_nodes,expected_edges",
    [
        # Single file: N nodes + M edges written on first export.
        (
            [_node("usr::fn1"), _node("usr::fn2")],
            [_edge("usr::fn1", "usr::fn2")],
            2,
            1,
        ),
    ],
)
def test_export_then_re_export_returns_zero(
    node_batch: list[NodeRecord],
    edge_batch: list[EdgeRecord],
    expected_nodes: int,
    expected_edges: int,
) -> None:
    """End-to-end: first export returns (N, M), second export returns (0, 0)."""
    with _fake_indradb_context() as (driver, _):
        n1 = driver.upsert_nodes(node_batch)
        e1 = driver.upsert_edges(edge_batch)
        assert n1 == expected_nodes
        assert e1 == expected_edges
        # Re-export — nothing new.
        n2 = driver.upsert_nodes(node_batch)
        e2 = driver.upsert_edges(edge_batch)
        assert n2 == 0, f"Re-export must return 0 nodes written (ADR-17), got {n2}"
        assert e2 == 0, f"Re-export must return 0 edges written (ADR-17), got {e2}"
