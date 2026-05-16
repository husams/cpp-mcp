"""Unit tests for IndraDBDriver (S2 / US-G2).

All tests use the in-memory fake from tests/fixtures/fake_indradb.py
installed via monkeypatch.  No real IndraDB daemon is required.

Coverage:
- US-G2/AC-1: methods exist; structural Protocol shape.
- US-G2/AC-2: connect accepts indradb://, grpc://, indradb+grpc:// URIs.
- US-G2/AC-2 fail: connect raises DBUnreachableError when ping fails.
- US-G2/AC-8: connect raises DependencyMissingError when indradb absent.
- US-G2/AC-3: USR → UUID determinism across two driver instances.
- US-G2/AC-4: upsert_nodes idempotent — vertex count stable on repeat.
- US-G2/AC-5: upsert_edges idempotent — edge count stable on repeat.
- US-G2/AC-6: round-trip label + props preserved in the fake store.
- ADR-15: non-scalar prop is JSON-encoded; unencodable triggers debug log.
- US-G2/AC-7: close() twice does not raise.
"""

from __future__ import annotations

import importlib
import logging
import sys
import types
import uuid
from typing import Any

import pytest

from cpp_mcp.core.error_envelope import DBUnreachableError, DependencyMissingError
from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord

# ---------------------------------------------------------------------------
# Helpers: build a fresh fake_indradb module-like object
# ---------------------------------------------------------------------------


def _make_fake_module() -> types.ModuleType:
    """Return a freshly-imported fake_indradb module."""
    # Import from the fixtures package; Python caches it under its real name.
    import tests.fixtures.fake_indradb as _fake

    return _fake  # type: ignore[return-value]


def _install_fake(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Install the fake_indradb module as 'indradb' and return it."""
    fake = _make_fake_module()
    monkeypatch.setitem(sys.modules, "indradb", fake)
    # Re-import the driver so the lazy import sees the fake.
    import cpp_mcp.graphdb.indradb_driver as drv_mod

    importlib.reload(drv_mod)
    return fake


# ---------------------------------------------------------------------------
# Fixture: driver + connected client via the fake
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_driver(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Yield (IndraDBDriver instance, fake_indradb module) with the fake wired in."""
    fake = _install_fake(monkeypatch)
    from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

    driver = IndraDBDriver()
    driver.connect("indradb://localhost:27615")
    yield driver, fake
    driver.close()


# ---------------------------------------------------------------------------
# US-G2/AC-1: Protocol shape — structural check
# ---------------------------------------------------------------------------


class TestProtocolShape:
    def test_has_connect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        assert callable(IndraDBDriver.connect)

    def test_has_upsert_nodes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        assert callable(IndraDBDriver.upsert_nodes)

    def test_has_upsert_edges(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        assert callable(IndraDBDriver.upsert_edges)

    def test_has_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        assert callable(IndraDBDriver.close)

    def test_structural_protocol_satisfied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """IndraDBDriver must have all four methods required by GraphDriver Protocol."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        for method in ("connect", "upsert_nodes", "upsert_edges", "close"):
            assert hasattr(driver, method) and callable(getattr(driver, method)), (
                f"IndraDBDriver missing required Protocol method: {method!r}"
            )


# ---------------------------------------------------------------------------
# US-G2/AC-2: connect with all accepted URI schemes
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.parametrize(
        "uri",
        [
            "indradb://localhost:27615",
            "grpc://localhost:27615",
            "indradb+grpc://localhost:27615",
        ],
    )
    def test_connect_accepted_schemes(self, monkeypatch: pytest.MonkeyPatch, uri: str) -> None:
        """connect() must succeed for all three accepted URI schemes."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        driver.connect(uri)
        # Confirm the client was set (fake Client tracks host)
        assert driver._client is not None
        driver.close()

    def test_connect_default_port_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """connect() must apply port 27615 when none is specified in the URI."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        driver.connect("indradb://localhost")
        assert driver._client is not None
        assert driver._client.host == "localhost:27615"
        driver.close()

    def test_connect_raises_db_unreachable_when_ping_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """connect() must raise DBUnreachableError when the fake client ping raises."""
        fake = _install_fake(monkeypatch)

        # Patch Client to set _fail_on_ping=True on construction.
        original_client = fake.Client

        class FailingClient(original_client):  # type: ignore[misc]
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self._fail_on_ping = True

        monkeypatch.setattr(fake, "Client", FailingClient)

        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        with pytest.raises(DBUnreachableError, match="Cannot reach graph database"):
            driver.connect("indradb://localhost:27615")


# ---------------------------------------------------------------------------
# US-G2/AC-8: DependencyMissingError when indradb absent
# ---------------------------------------------------------------------------


class TestDependencyMissing:
    def test_connect_raises_dependency_missing_when_indradb_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """connect() must raise DependencyMissingError when indradb is not importable."""
        monkeypatch.setitem(sys.modules, "indradb", None)  # type: ignore[arg-type]
        # Force re-import so connect() sees the patched sys.modules.
        import cpp_mcp.graphdb.indradb_driver as drv_mod

        importlib.reload(drv_mod)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        with pytest.raises(DependencyMissingError, match="pip install"):
            driver.connect("indradb://localhost:27615")

    def test_dependency_missing_message_contains_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "indradb", None)  # type: ignore[arg-type]
        import cpp_mcp.graphdb.indradb_driver as drv_mod

        importlib.reload(drv_mod)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        with pytest.raises(DependencyMissingError, match="graphdb-indradb"):
            driver.connect("indradb://localhost:27615")


# ---------------------------------------------------------------------------
# US-G2/AC-3: USR → UUID determinism
# ---------------------------------------------------------------------------


class TestUUIDDeterminism:
    def test_same_usr_same_uuid_across_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """uuid5(NS_CPPMCP_USR, usr) must be identical for two independent driver instances."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import NS_CPPMCP_USR, IndraDBDriver

        usr = "c:@F@foo#"
        vid_a = uuid.uuid5(NS_CPPMCP_USR, usr)
        vid_b = uuid.uuid5(NS_CPPMCP_USR, usr)
        assert vid_a == vid_b

        # Also confirm that two freshly-constructed drivers would produce the same UUID.
        driver_a = IndraDBDriver()
        driver_a.connect("indradb://localhost:27615")
        driver_b = IndraDBDriver()
        driver_b.connect("indradb://localhost:27615")

        batch: list[NodeRecord] = [{"label": "Function", "usr": usr, "props": {}}]
        driver_a.upsert_nodes(batch)
        driver_b.upsert_nodes(batch)

        # Both should have stored the same UUID vertex in their independent clients.
        assert driver_a._client.node_count == 1
        assert driver_b._client.node_count == 1
        # The vertex UUID in both clients must match.
        ids_a = list(driver_a._client._vertices.keys())
        ids_b = list(driver_b._client._vertices.keys())
        assert ids_a == ids_b
        driver_a.close()
        driver_b.close()

    def test_ns_cppmcp_usr_constant_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NS_CPPMCP_USR must equal the ADR-14 pinned literal."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import NS_CPPMCP_USR

        assert uuid.UUID("8f6e2c1b-7d3a-4f59-9a4b-1c0d2e5f8a91") == NS_CPPMCP_USR


# ---------------------------------------------------------------------------
# US-G2/AC-4: upsert_nodes idempotency
# ---------------------------------------------------------------------------


class TestUpsertNodesIdempotency:
    def test_vertex_count_stable_after_two_identical_calls(self, fake_driver: Any) -> None:
        """Upserting the same node twice must not increase the vertex count."""
        driver, _fake = fake_driver
        batch: list[NodeRecord] = [
            {"label": "Function", "usr": "c:@F@bar#", "props": {"line": 10}},
        ]
        driver.upsert_nodes(batch)
        count_after_first = driver._client.node_count
        driver.upsert_nodes(batch)
        count_after_second = driver._client.node_count
        assert count_after_first == count_after_second == 1

    def test_upsert_nodes_returns_batch_length(self, fake_driver: Any) -> None:
        driver, _ = fake_driver
        batch: list[NodeRecord] = [
            {"label": "Class", "usr": "c:@C@MyClass", "props": {}},
            {"label": "Function", "usr": "c:@F@method", "props": {}},
        ]
        result = driver.upsert_nodes(batch)
        assert result == 2


# ---------------------------------------------------------------------------
# US-G2/AC-5: upsert_edges idempotency
# ---------------------------------------------------------------------------


class TestUpsertEdgesIdempotency:
    def test_edge_count_stable_after_two_identical_calls(self, fake_driver: Any) -> None:
        """Upserting the same edge twice must not increase the edge count."""
        driver, _ = fake_driver
        # Pre-insert nodes so edge endpoints exist.
        nodes: list[NodeRecord] = [
            {"label": "Function", "usr": "c:@F@src", "props": {}},
            {"label": "Function", "usr": "c:@F@tgt", "props": {}},
        ]
        driver.upsert_nodes(nodes)
        edges: list[EdgeRecord] = [
            {
                "source_usr": "c:@F@src",
                "target_usr": "c:@F@tgt",
                "edge_type": "CALLS",
                "props": {},
            }
        ]
        driver.upsert_edges(edges)
        count_after_first = driver._client.edge_count
        driver.upsert_edges(edges)
        count_after_second = driver._client.edge_count
        assert count_after_first == count_after_second == 1

    def test_upsert_edges_returns_batch_length(self, fake_driver: Any) -> None:
        driver, _ = fake_driver
        nodes: list[NodeRecord] = [
            {"label": "Function", "usr": "c:@F@a", "props": {}},
            {"label": "Function", "usr": "c:@F@b", "props": {}},
        ]
        driver.upsert_nodes(nodes)
        edges: list[EdgeRecord] = [
            {
                "source_usr": "c:@F@a",
                "target_usr": "c:@F@b",
                "edge_type": "CALLS",
                "props": {},
            }
        ]
        result = driver.upsert_edges(edges)
        assert result == 1


# ---------------------------------------------------------------------------
# US-G2/AC-6: round-trip label + props
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_label_stored_as_vertex_type(self, fake_driver: Any) -> None:
        driver, _ = fake_driver
        batch: list[NodeRecord] = [
            {"label": "Class", "usr": "c:@C@Foo", "props": {}},
        ]
        driver.upsert_nodes(batch)
        from cpp_mcp.graphdb.indradb_driver import NS_CPPMCP_USR

        vid = uuid.uuid5(NS_CPPMCP_USR, "c:@C@Foo")
        vertex = driver._client._vertices[vid]
        assert vertex.t.name == "Class"

    def test_props_stored_on_vertex(self, fake_driver: Any) -> None:
        driver, _ = fake_driver
        batch: list[NodeRecord] = [
            {"label": "Function", "usr": "c:@F@baz#", "props": {"line": 42, "col": 7}},
        ]
        driver.upsert_nodes(batch)
        from cpp_mcp.graphdb.indradb_driver import NS_CPPMCP_USR

        vid = uuid.uuid5(NS_CPPMCP_USR, "c:@F@baz#")
        stored = driver._client.get_vertex_props(vid)
        assert stored["line"] == 42
        assert stored["col"] == 7
        assert stored["usr"] == "c:@F@baz#"  # USR always persisted (ADR-14)


# ---------------------------------------------------------------------------
# ADR-15: property serialisation
# ---------------------------------------------------------------------------


class TestPropSerialisation:
    def test_scalar_prop_stored_as_is(self, fake_driver: Any) -> None:
        driver, _ = fake_driver
        batch: list[NodeRecord] = [
            {"label": "Function", "usr": "c:@F@s", "props": {"count": 5}},
        ]
        driver.upsert_nodes(batch)
        from cpp_mcp.graphdb.indradb_driver import NS_CPPMCP_USR

        vid = uuid.uuid5(NS_CPPMCP_USR, "c:@F@s")
        assert driver._client.get_vertex_props(vid)["count"] == 5

    def test_dict_prop_json_encoded(self, fake_driver: Any) -> None:
        """Non-scalar (dict) props must be stored as a JSON string (ADR-15)."""
        driver, _ = fake_driver
        batch: list[NodeRecord] = [
            {"label": "Function", "usr": "c:@F@d", "props": {"meta": {"a": 1}}},
        ]
        driver.upsert_nodes(batch)
        import json

        from cpp_mcp.graphdb.indradb_driver import NS_CPPMCP_USR

        vid = uuid.uuid5(NS_CPPMCP_USR, "c:@F@d")
        stored = driver._client.get_vertex_props(vid)["meta"]
        assert isinstance(stored, str)
        assert json.loads(stored) == {"a": 1}

    def test_unencodable_prop_triggers_debug_log(
        self, fake_driver: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ADR-15: unencodable props must trigger a logger.debug call."""
        driver, _ = fake_driver
        # Build a circular reference that json.dumps cannot encode.
        d: dict[str, Any] = {}
        d["self"] = d

        with caplog.at_level(logging.DEBUG, logger="cpp_mcp.graphdb.indradb_driver"):
            batch: list[NodeRecord] = [
                {"label": "Function", "usr": "c:@F@circ", "props": {"bad": d}},
            ]
            driver.upsert_nodes(batch)

        # At least one debug record must mention the key name.
        debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("bad" in msg for msg in debug_msgs), (
            f"Expected a debug log mentioning 'bad'; got: {debug_msgs}"
        )


# ---------------------------------------------------------------------------
# US-G2/AC-7: close() idempotency
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_twice_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calling close() twice must not raise any exception."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        driver.connect("indradb://localhost:27615")
        driver.close()
        driver.close()  # must not raise

    def test_close_without_connect_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calling close() on a never-connected driver must not raise."""
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        driver.close()

    def test_client_none_after_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake(monkeypatch)
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver

        driver = IndraDBDriver()
        driver.connect("indradb://localhost:27615")
        driver.close()
        assert driver._client is None
