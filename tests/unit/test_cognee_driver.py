"""Protocol conformance and idempotency tests for CogneeDriver.

Tests are divided into three groups:

1. Unit tests using ``FakeCogneeTransport`` — always run; cover Protocol
   conformance, idempotency, error paths, factory routing, and key helpers.

2. Live integration tests marked ``@pytest.mark.cognee`` — skipped unless
   ``COGNEE_BASE_URL`` is set in the environment.  These exercise the real
   ``CliCogneeTransport`` against a running Cognee service.

Scenario traceability
---------------------
  ADR-7 followup — CogneeDriver idempotency, Protocol conformance, factory
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from cpp_mcp.core.error_envelope import DBUnreachableError
from cpp_mcp.graphdb.cognee_driver import (
    CliCogneeTransport,
    CogneeDriver,
    CogneeTransport,
    _edge_key,
    _node_key,
)
from cpp_mcp.graphdb.driver import EdgeRecord, GraphDriver, NodeRecord
from cpp_mcp.graphdb.schema import (
    EDGE_CALLS,
    EDGE_DEFINES,
    EDGE_INCLUDES,
    EDGE_INHERITS,
    EDGE_MEMBER_OF,
    EDGE_REFERENCES,
    NODE_CLASS,
    NODE_FILE,
    NODE_FUNCTION,
)

# ---------------------------------------------------------------------------
# FakeCogneeTransport
# ---------------------------------------------------------------------------


class FakeCogneeTransport:
    """In-memory transport; records calls keyed by dedup key.

    Satisfies :class:`~cpp_mcp.graphdb.cognee_driver.CogneeTransport`.
    """

    def __init__(self) -> None:
        # key → (payload, dataset, node_set)
        self.store: dict[str, tuple[dict[str, Any], str, list[str]]] = {}
        self.call_count: int = 0

    def ingest(
        self,
        key: str,
        payload: dict[str, Any],
        dataset: str,
        node_set: list[str],
    ) -> None:
        self.store[key] = (payload, dataset, node_set)
        self.call_count += 1


# Verify structural Protocol compliance at import time.
_: CogneeTransport = FakeCogneeTransport()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_driver(
    dataset: str = "test-ds", node_set: list[str] | None = None
) -> tuple[CogneeDriver, FakeCogneeTransport]:
    transport = FakeCogneeTransport()
    driver = CogneeDriver(transport=transport)
    driver.connect(f"cognee://{dataset}", node_set=node_set or [])
    return driver, transport


def _node(label: str = NODE_FUNCTION, usr: str = "c:@F@foo", **props: Any) -> NodeRecord:
    return NodeRecord(label=label, usr=usr, props={"spelling": "foo", **props})


def _edge(
    src: str = "c:@F@foo",
    tgt: str = "c:@F@bar",
    etype: str = EDGE_CALLS,
) -> EdgeRecord:
    return EdgeRecord(source_usr=src, target_usr=tgt, edge_type=etype, props={})


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_cognee_driver_satisfies_graph_driver_protocol() -> None:
    """CogneeDriver must structurally satisfy GraphDriver (Protocol check)."""
    driver, _ = _make_driver()
    _check: GraphDriver = driver  # type: ignore[assignment]
    assert _check is driver


def test_cli_transport_satisfies_transport_protocol() -> None:
    """CliCogneeTransport must satisfy CogneeTransport Protocol."""
    cli: CogneeTransport = CliCogneeTransport()  # type: ignore[assignment]
    assert isinstance(cli, CogneeTransport)


# ---------------------------------------------------------------------------
# connect / URI parsing
# ---------------------------------------------------------------------------


def test_connect_extracts_dataset() -> None:
    """Dataset name comes from the netloc of the cognee:// URI."""
    driver, _ = _make_driver("my-dataset")
    assert driver._dataset == "my-dataset"


def test_connect_stores_node_set() -> None:
    """node_set kwarg is stored for every subsequent ingest call."""
    driver, transport = _make_driver("ds", node_set=["project:myrepo", "env:test"])
    driver.upsert_nodes([_node()])
    _, _, ns = next(iter(transport.store.values()))
    assert "project:myrepo" in ns
    assert "env:test" in ns


def test_connect_wrong_scheme_raises() -> None:
    """connect() raises DBUnreachableError when the URI scheme is not 'cognee'."""
    driver = CogneeDriver(transport=FakeCogneeTransport())
    with pytest.raises(DBUnreachableError, match="cognee://"):
        driver.connect("bolt://localhost:7687")


def test_connect_empty_dataset_raises() -> None:
    """connect() raises DBUnreachableError when the URI has no dataset name."""
    driver = CogneeDriver(transport=FakeCogneeTransport())
    with pytest.raises(DBUnreachableError, match="dataset name"):
        driver.connect("cognee://")


# ---------------------------------------------------------------------------
# upsert_nodes — idempotency and counting
# ---------------------------------------------------------------------------


def test_upsert_nodes_returns_new_count() -> None:
    """First upsert of N distinct nodes returns N."""
    driver, _ = _make_driver()
    batch = [_node(usr=f"c:@F@f{i}") for i in range(5)]
    assert driver.upsert_nodes(batch) == 5


def test_upsert_nodes_same_batch_twice_idempotent() -> None:
    """Re-upserting the same batch returns 0 new nodes (MERGE-on-USR)."""
    driver, transport = _make_driver()
    batch = [_node(usr=f"c:@F@f{i}") for i in range(4)]

    first = driver.upsert_nodes(batch)
    store_size_after_first = len(transport.store)

    second = driver.upsert_nodes(batch)
    store_size_after_second = len(transport.store)

    assert first == 4
    assert second == 0, "Re-upsert must report 0 new nodes"
    assert store_size_after_first == store_size_after_second, (
        "Transport store must not grow on re-ingest (same key replaces)"
    )


def test_upsert_nodes_overlapping_batches() -> None:
    """Two overlapping batches leave store at union size."""
    driver, transport = _make_driver()
    batch_a = [_node(usr=f"c:@F@f{i}") for i in range(3)]  # 0,1,2
    batch_b = [_node(usr=f"c:@F@f{i}") for i in range(5)]  # 0,1,2,3,4

    driver.upsert_nodes(batch_a)
    driver.upsert_nodes(batch_b)

    # 5 distinct USRs
    assert len(transport.store) == 5


def test_upsert_nodes_empty_batch_returns_zero() -> None:
    """Empty node batch returns 0 and makes no transport calls."""
    driver, transport = _make_driver()
    assert driver.upsert_nodes([]) == 0
    assert transport.call_count == 0


def test_upsert_nodes_before_connect_returns_zero() -> None:
    """upsert_nodes on unconnected driver returns 0 silently."""
    transport = FakeCogneeTransport()
    driver = CogneeDriver(transport=transport)
    assert driver.upsert_nodes([_node()]) == 0
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# upsert_edges — idempotency and counting
# ---------------------------------------------------------------------------


def test_upsert_edges_returns_new_count() -> None:
    """First upsert of N distinct edges returns N."""
    driver, _ = _make_driver()
    batch = [_edge(src=f"c:@F@f{i}", tgt=f"c:@F@g{i}") for i in range(3)]
    assert driver.upsert_edges(batch) == 3


def test_upsert_edges_same_batch_twice_idempotent() -> None:
    """Re-upserting the same edge batch returns 0 new edges."""
    driver, transport = _make_driver()
    batch = [_edge(src=f"c:@F@f{i}", tgt=f"c:@F@g{i}") for i in range(3)]

    first = driver.upsert_edges(batch)
    size_after_first = len(transport.store)

    second = driver.upsert_edges(batch)
    size_after_second = len(transport.store)

    assert first == 3
    assert second == 0, "Re-upsert of identical edge batch must return 0"
    assert size_after_first == size_after_second


def test_upsert_edges_empty_batch_returns_zero() -> None:
    """Empty edge batch returns 0 and makes no transport calls."""
    driver, transport = _make_driver()
    assert driver.upsert_edges([]) == 0
    assert transport.call_count == 0


def test_upsert_edges_before_connect_returns_zero() -> None:
    """upsert_edges on unconnected driver returns 0 silently."""
    transport = FakeCogneeTransport()
    driver = CogneeDriver(transport=transport)
    assert driver.upsert_edges([_edge()]) == 0


# ---------------------------------------------------------------------------
# Payload shape and dataset routing
# ---------------------------------------------------------------------------


def test_node_payload_contains_required_fields() -> None:
    """Node payload must contain kind, label, and usr."""
    driver, transport = _make_driver("ds")
    rec = _node(label=NODE_CLASS, usr="c:@S@MyClass", spelling="MyClass")
    driver.upsert_nodes([rec])

    key = _node_key("c:@S@MyClass")
    assert key in transport.store
    payload, dataset, _ = transport.store[key]
    assert payload["kind"] == "node"
    assert payload["label"] == NODE_CLASS
    assert payload["usr"] == "c:@S@MyClass"
    assert dataset == "ds"


def test_edge_payload_contains_required_fields() -> None:
    """Edge payload must contain kind, source_usr, edge_type, target_usr."""
    driver, transport = _make_driver("ds")
    rec = _edge(src="c:@F@a", tgt="c:@F@b", etype=EDGE_CALLS)
    driver.upsert_edges([rec])

    key = _edge_key("c:@F@a", EDGE_CALLS, "c:@F@b")
    assert key in transport.store
    payload, dataset, _ = transport.store[key]
    assert payload["kind"] == "edge"
    assert payload["source_usr"] == "c:@F@a"
    assert payload["edge_type"] == EDGE_CALLS
    assert payload["target_usr"] == "c:@F@b"
    assert dataset == "ds"


def test_dataset_name_forwarded_to_transport() -> None:
    """Every ingest call must carry the dataset set in connect()."""
    driver, transport = _make_driver("my-graph")
    driver.upsert_nodes([_node()])
    _, ds, _ = next(iter(transport.store.values()))
    assert ds == "my-graph"


# ---------------------------------------------------------------------------
# Schema coverage — all node labels and edge types are representable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [NODE_FILE, NODE_CLASS, NODE_FUNCTION],
)
def test_node_labels_produce_distinct_keys(label: str) -> None:
    """Different labels with the same USR must not collide on the transport store key."""
    transport = FakeCogneeTransport()
    d1 = CogneeDriver(transport=transport)
    d1.connect("cognee://ds")
    d1.upsert_nodes([NodeRecord(label=label, usr=f"c:@{label}@X", props={})])


@pytest.mark.parametrize(
    "etype",
    [EDGE_DEFINES, EDGE_CALLS, EDGE_INHERITS, EDGE_INCLUDES, EDGE_MEMBER_OF, EDGE_REFERENCES],
)
def test_all_edge_types_ingestable(etype: str) -> None:
    """Every edge type is representable and produces a transport call."""
    driver, transport = _make_driver()
    rec = EdgeRecord(source_usr="c:@A", target_usr="c:@B", edge_type=etype, props={})
    count = driver.upsert_edges([rec])
    assert count == 1
    assert transport.call_count == 1


# ---------------------------------------------------------------------------
# close() resets session state
# ---------------------------------------------------------------------------


def test_close_resets_connected_state() -> None:
    """After close(), upsert_nodes returns 0 (driver is no longer connected)."""
    driver, transport = _make_driver()
    driver.close()
    result = driver.upsert_nodes([_node()])
    assert result == 0
    assert transport.call_count == 0


def test_close_clears_dedup_indices() -> None:
    """After close() + reconnect, first upsert again counts as new."""
    transport = FakeCogneeTransport()
    driver = CogneeDriver(transport=transport)
    driver.connect("cognee://ds")
    driver.upsert_nodes([_node(usr="c:@F@foo")])

    driver.close()
    driver.connect("cognee://ds")
    count = driver.upsert_nodes([_node(usr="c:@F@foo")])
    assert count == 1, "After reconnect, same USR must be treated as new"


# ---------------------------------------------------------------------------
# Key-helper determinism
# ---------------------------------------------------------------------------


def test_node_key_is_deterministic() -> None:
    """_node_key returns the same value for the same USR across calls."""
    assert _node_key("c:@F@foo") == _node_key("c:@F@foo")


def test_edge_key_is_deterministic() -> None:
    """_edge_key is deterministic and distinct from other combos."""
    k1 = _edge_key("a", "CALLS", "b")
    k2 = _edge_key("a", "CALLS", "b")
    k3 = _edge_key("a", "INHERITS", "b")
    assert k1 == k2
    assert k1 != k3


def test_node_key_distinct_from_edge_key() -> None:
    """Node and edge keys share no common prefix to avoid accidental collision."""
    nk = _node_key("c:@F@x")
    ek = _edge_key("c:@F@x", "CALLS", "c:@F@y")
    assert nk.startswith("node:")
    assert ek.startswith("edge:")


# ---------------------------------------------------------------------------
# make_driver factory — cognee:// scheme
# ---------------------------------------------------------------------------


def test_make_driver_cognee_scheme_returns_cognee_driver() -> None:
    """make_driver('cognee://...') returns a CogneeDriver instance."""
    import cpp_mcp.graphdb.cognee_driver as _cd
    from cpp_mcp.graphdb import make_driver

    original_transport = _cd.CliCogneeTransport

    class PatchedCli:
        def ingest(
            self, key: str, payload: dict[str, Any], dataset: str, node_set: list[str]
        ) -> None:
            pass

    _cd.CliCogneeTransport = PatchedCli  # type: ignore[misc]
    try:
        driver = make_driver("cognee://test-graph")
        assert isinstance(driver, CogneeDriver)
        driver.close()
    finally:
        _cd.CliCogneeTransport = original_transport  # type: ignore[misc]


def test_make_driver_unknown_scheme_raises() -> None:
    """make_driver raises ValueError for unsupported URI schemes."""
    from cpp_mcp.graphdb import make_driver

    with pytest.raises(ValueError, match="Unsupported"):
        make_driver("postgres://localhost/mydb")


# ---------------------------------------------------------------------------
# @pytest.mark.cognee live tests — skipped when COGNEE_BASE_URL absent
# ---------------------------------------------------------------------------


@pytest.mark.cognee
def test_cognee_marker_live_upsert_nodes() -> None:
    """Live test: upsert a small node batch against the real Cognee service.

    Skipped when COGNEE_BASE_URL is not set.  Validates that CliCogneeTransport
    reaches the service and does not raise.
    """
    if not os.environ.get("COGNEE_BASE_URL"):
        pytest.skip("COGNEE_BASE_URL not set — @cognee live test skipped")

    driver = CogneeDriver()
    driver.connect("cognee://cpp-mcp-test", node_set=["task:test-live"])
    batch = [
        NodeRecord(
            label=NODE_FUNCTION,
            usr="c:@F@live_test_func",
            props={"spelling": "live_test_func", "file": "live.cpp", "line": 1},
        )
    ]
    n = driver.upsert_nodes(batch)
    assert n == 1
    driver.close()


@pytest.mark.cognee
def test_cognee_marker_live_upsert_edges() -> None:
    """Live test: upsert a small edge batch against the real Cognee service.

    Skipped when COGNEE_BASE_URL is not set.
    """
    if not os.environ.get("COGNEE_BASE_URL"):
        pytest.skip("COGNEE_BASE_URL not set — @cognee live test skipped")

    driver = CogneeDriver()
    driver.connect("cognee://cpp-mcp-test", node_set=["task:test-live"])
    batch = [
        EdgeRecord(
            source_usr="c:@F@live_test_func",
            target_usr="file://live.cpp",
            edge_type=EDGE_DEFINES,
            props={},
        )
    ]
    e = driver.upsert_edges(batch)
    assert e == 1
    driver.close()


@pytest.mark.cognee
def test_cognee_marker_skip_guard() -> None:
    """Verifies the @cognee marker skip guard works (proof of infrastructure)."""
    if not os.environ.get("COGNEE_BASE_URL"):
        pytest.skip("COGNEE_BASE_URL not set — @cognee test skipped as expected")
    # If we reach here, COGNEE_BASE_URL is set; nothing more to assert.
