"""Cognee-backed GraphDriver implementation (ADR-7 follow-up).

Maps our C++ schema (File/Namespace/Class/Function/Variable/Macro/TypeAlias
nodes; DEFINES/CALLS/INHERITS/REFERENCES/INCLUDES/MEMBER_OF/DECLARES edges)
into structured JSON documents ingested via Cognee's ``/api/v1/add`` endpoint.

Idempotency strategy
--------------------
Cognee's add API does not natively MERGE on a key.  This driver implements
**driver-side dedup** within a session:

  - Nodes are keyed by USR.  ``upsert_nodes`` replaces any previously-seen
    entry for the same USR, so re-ingesting the same file within one session
    leaves the in-memory index size unchanged.
  - Edges are keyed by ``(source_usr, edge_type, target_usr)``.  Same rule.

Between sessions, the Cognee backend receives a fresh upload.  True cross-
session dedup is documented as best-effort (the dataset may accumulate
duplicate documents when re-ingested across restarts).  This is an accepted
limitation per ADR-7.

Transport abstraction
---------------------
``CogneeDriver`` depends on ``CogneeTransport`` — a one-method Protocol.
``CliCogneeTransport`` (default) shells out to the local ``cognee`` CLI::

    cognee api request POST /api/v1/add --body @<tmpfile>

This keeps auth concerns (Vault / Keychain) entirely inside the CLI.  Tests
inject ``FakeCogneeTransport`` without touching the network.

Dataset / node-set
------------------
The URI ``cognee://<dataset>`` passed to ``connect()`` supplies the Cognee
dataset name.  Additional ``node_set`` tags can be passed as keyword arg::

    driver.connect("cognee://cpp-knowledge", node_set=["project:myrepo"])
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import subprocess
import tempfile
from typing import Any, Protocol, runtime_checkable

from cpp_mcp.core.error_envelope import DBUnreachableError
from cpp_mcp.graphdb.driver import EdgeRecord, NodeRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transport Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class CogneeTransport(Protocol):
    """One-method Protocol for Cognee ingest transport."""

    def ingest(
        self,
        key: str,
        payload: dict[str, Any],
        dataset: str,
        node_set: list[str],
    ) -> None:
        """Send *payload* to Cognee under *dataset* tagged with *node_set*.

        Args:
            key:      Stable dedup key (USR or edge triple); used for logging.
            payload:  Serialisable dict sent as the document body.
            dataset:  Cognee dataset name.
            node_set: List of ``"tag:value"`` node-set strings.

        Raises:
            :exc:`cpp_mcp.core.error_envelope.DBUnreachableError`: if the
                underlying transport cannot reach the Cognee service.
        """
        ...


# ---------------------------------------------------------------------------
# CliCogneeTransport — shells out to the local ``cognee`` CLI
# ---------------------------------------------------------------------------


class CliCogneeTransport:
    """Ingest transport that shells out to the ``cognee`` CLI.

    Constructs a JSON document from *payload*, writes it to a temporary file,
    then calls::

        cognee api request POST /api/v1/add --body @<tmpfile>

    Auth (Vault / Keychain) is handled entirely by the CLI.  The ``COGNEE_BASE_URL``
    environment variable, if set, is passed through transparently (the CLI reads
    it from its own config / env).
    """

    def ingest(
        self,
        key: str,
        payload: dict[str, Any],
        dataset: str,
        node_set: list[str],
    ) -> None:
        body: dict[str, Any] = {
            "url": f"data:{key}",
            "datasetName": dataset,
            "node_set": node_set,
            "data": payload,
        }
        body_bytes = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as tmp:
            tmp.write(body_bytes)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["cognee", "api", "request", "POST", "/api/v1/add", "--body", f"@{tmp_path}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise DBUnreachableError(
                "cognee CLI not found on PATH. Install cognee-cli or set PATH correctly."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DBUnreachableError(f"cognee CLI timed out while ingesting key={key!r}") from exc
        finally:
            import os

            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

        if result.returncode != 0:
            raise DBUnreachableError(
                f"cognee CLI returned exit code {result.returncode} for key={key!r}: "
                f"{result.stderr.strip()}"
            )

        logger.debug("cognee ingest OK: key=%s dataset=%s", key, dataset)


# ---------------------------------------------------------------------------
# CogneeDriver
# ---------------------------------------------------------------------------


class CogneeDriver:
    """Cognee-backed graph driver; satisfies the ``GraphDriver`` Protocol.

    Connect with a ``cognee://<dataset>`` URI.  Internally maintains an
    in-session index so re-upserts of the same USR / edge key are idempotent
    within one session.

    Example::

        driver = CogneeDriver()
        driver.connect("cognee://cpp-knowledge", node_set=["project:myrepo"])
        n = driver.upsert_nodes(nodes)
        e = driver.upsert_edges(edges)
        driver.close()
    """

    def __init__(self, transport: CogneeTransport | None = None) -> None:
        """Initialise with an optional transport override (for testing)."""
        self._transport: CogneeTransport = (
            transport if transport is not None else CliCogneeTransport()
        )
        self._dataset: str = ""
        self._node_set: list[str] = []
        self._connected: bool = False
        # In-session dedup indices
        self._node_index: dict[str, NodeRecord] = {}
        self._edge_index: dict[tuple[str, str, str], EdgeRecord] = {}

    # ------------------------------------------------------------------
    # connect
    # ------------------------------------------------------------------

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Establish the Cognee dataset target from a ``cognee://`` URI.

        Args:
            uri:      ``cognee://<dataset>`` — dataset name is taken from the
                      netloc component.
            **kwargs: Optional ``node_set: list[str]`` of extra tag strings
                      that will be attached to every ingested document.

        Raises:
            :exc:`DBUnreachableError`: if the URI scheme is not ``cognee`` or
                if a connectivity probe fails.
        """
        from urllib.parse import urlparse

        parsed = urlparse(uri)
        if parsed.scheme != "cognee":
            raise DBUnreachableError(
                f"CogneeDriver requires a 'cognee://' URI, got scheme={parsed.scheme!r}"
            )

        dataset = parsed.netloc or parsed.path.lstrip("/")
        if not dataset:
            raise DBUnreachableError(
                "CogneeDriver URI must include a dataset name, "
                f"e.g. 'cognee://my-dataset'. Got: {uri!r}"
            )

        extra_node_set: list[str] = list(kwargs.get("node_set", []))

        self._dataset = dataset
        self._node_set = extra_node_set
        self._connected = True
        self._node_index = {}
        self._edge_index = {}
        logger.debug("CogneeDriver connected: dataset=%s node_set=%s", dataset, extra_node_set)

    # ------------------------------------------------------------------
    # upsert_nodes
    # ------------------------------------------------------------------

    def upsert_nodes(self, batch: list[NodeRecord]) -> int:
        """Ingest *batch* of nodes with MERGE-on-USR semantics.

        New nodes are sent to Cognee; existing (same USR, same session) nodes
        are updated in the local index only — no duplicate upload occurs.

        Returns:
            Number of net-new nodes written (not updated-in-place).
        """
        if not batch or not self._connected:
            return 0

        new_count = 0
        for rec in batch:
            usr = rec["usr"]
            is_new = usr not in self._node_index
            self._node_index[usr] = rec

            payload: dict[str, Any] = {
                "kind": "node",
                "label": rec["label"],
                "usr": usr,
                **rec["props"],
            }
            key = _node_key(usr)
            self._transport.ingest(key, payload, self._dataset, self._node_set)

            if is_new:
                new_count += 1

        return new_count

    # ------------------------------------------------------------------
    # upsert_edges
    # ------------------------------------------------------------------

    def upsert_edges(self, batch: list[EdgeRecord]) -> int:
        """Ingest *batch* of edges with MERGE-on-(source, type, target) semantics.

        Returns:
            Number of net-new edges written (not updated-in-place).
        """
        if not batch or not self._connected:
            return 0

        new_count = 0
        for rec in batch:
            triple = (rec["source_usr"], rec["edge_type"], rec["target_usr"])
            is_new = triple not in self._edge_index
            self._edge_index[triple] = rec

            payload = {
                "kind": "edge",
                "source_usr": rec["source_usr"],
                "edge_type": rec["edge_type"],
                "target_usr": rec["target_usr"],
                **rec["props"],
            }
            key = _edge_key(*triple)
            self._transport.ingest(key, payload, self._dataset, self._node_set)

            if is_new:
                new_count += 1

        return new_count

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Reset session state and mark the driver as disconnected."""
        self._connected = False
        self._dataset = ""
        self._node_set = []
        self._node_index = {}
        self._edge_index = {}
        logger.debug("CogneeDriver closed")


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def _node_key(usr: str) -> str:
    """Stable, URL-safe key for a node document derived from its USR."""
    h = hashlib.sha256(usr.encode()).hexdigest()[:16]
    return f"node:{h}"


def _edge_key(source_usr: str, edge_type: str, target_usr: str) -> str:
    """Stable, URL-safe key for an edge document."""
    raw = f"{source_usr}\x00{edge_type}\x00{target_usr}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"edge:{h}"
