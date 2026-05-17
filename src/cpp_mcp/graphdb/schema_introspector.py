"""Schema introspector: live graph-schema discovery for Neo4j and IndraDB.

``describe_graph_schema`` calls :func:`select_introspector` to get the right
backend implementation, then calls :meth:`SchemaIntrospector.describe`.

ADR-24: discovery is live per call; no caching.  Writer stamps
``schema_version`` on ``File`` nodes so the reader can detect version skew.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any
from urllib.parse import urlparse

from cpp_mcp.core.error_envelope import (
    DBUnreachableError,
    DependencyMissingError,
    InvalidArgumentError,
)
from cpp_mcp.graphdb.schema_version import SCHEMA_VERSION

logger = logging.getLogger(__name__)

# Scheme frozensets — mirrors graphdb/__init__.py.
_NEO4J_SCHEMES: frozenset[str] = frozenset(
    {"bolt", "bolt+s", "bolt+ssc", "neo4j", "neo4j+s", "neo4j+ssc"}
)
_INDRADB_SCHEMES: frozenset[str] = frozenset({"indradb", "grpc", "indradb+grpc"})

# Label / type name validator — must match before backtick interpolation (AC-Q2-3).
_SAFE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Static notes always present (AC-Q2-2).
_NOTE_SAMPLE = (
    "Property keys are inferred from a sample of nodes/edges; "
    "rare properties may not appear."
)
_NOTE_LIVE = "Counts are live as of this call; concurrent ingest_code runs may shift values."


# ---------------------------------------------------------------------------
# SchemaDescription TypedDict shapes (inline to avoid extra import cost)
# ---------------------------------------------------------------------------


def _node_type_entry(
    name: str,
    count: int,
    property_keys: list[str],
) -> dict[str, Any]:
    return {"name": name, "count": count, "property_keys": property_keys}


def _edge_type_entry(
    name: str,
    count: int,
    property_keys: list[str],
) -> dict[str, Any]:
    return {"name": name, "count": count, "property_keys": property_keys}


def _sort_types(types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by (-count, name) — AC-Q2-5."""
    return sorted(types, key=lambda t: (-t["count"], t["name"]))


# ---------------------------------------------------------------------------
# Protocol (structural typing — no ABC import needed)
# ---------------------------------------------------------------------------


class SchemaIntrospector:
    """Structural protocol satisfied by Neo4j and IndraDB introspectors.

    Implementations must provide:
      - ``backend: str`` — ``"neo4j"`` or ``"indradb"``
      - ``connect(uri, **kwargs) -> None``
      - ``describe(sample_size) -> dict[str, Any]``
      - ``close() -> None``
    """

    backend: str

    def connect(self, uri: str, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    def describe(self, sample_size: int) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# select_introspector — pure scheme dispatch, no I/O
# ---------------------------------------------------------------------------


def select_introspector(db_uri: str) -> SchemaIntrospector:
    """Return an *unconnected* introspector for *db_uri*'s scheme.

    Args:
        db_uri: Backend URI including scheme.

    Returns:
        An unconnected :class:`SchemaIntrospector` instance.

    Raises:
        :exc:`~cpp_mcp.core.error_envelope.InvalidArgumentError`: empty URI,
            missing ``://``, or unknown scheme.
    """
    if not db_uri or "://" not in db_uri:
        raise InvalidArgumentError(
            f"db_uri must include a scheme (got {db_uri!r}); "
            f"supported: {sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
        )
    scheme = urlparse(db_uri).scheme
    if scheme in _NEO4J_SCHEMES:
        return Neo4jSchemaIntrospector()
    if scheme in _INDRADB_SCHEMES:
        return IndraDbSchemaIntrospector()
    raise InvalidArgumentError(
        f"Unsupported db_uri scheme {scheme!r}; "
        f"supported: {sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
    )


# ---------------------------------------------------------------------------
# Neo4j implementation
# ---------------------------------------------------------------------------


class Neo4jSchemaIntrospector(SchemaIntrospector):
    """Neo4j schema introspector using ``CALL db.labels()`` / ``CALL db.relationshipTypes()``.

    No ``apoc.*`` calls (AC-Q2-3).  Label/type names are validated against
    ``^[A-Za-z_][A-Za-z0-9_]*$`` before backtick interpolation to prevent injection.
    """

    backend: str = "neo4j"

    def __init__(self) -> None:
        self._driver: Any = None

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open a Bolt connection (lazy neo4j import).

        Raises:
            :exc:`DependencyMissingError`: neo4j not installed.
            :exc:`DBUnreachableError`: connection fails.
        """
        try:
            import neo4j
        except ImportError as exc:
            raise DependencyMissingError(
                "neo4j Python driver is not installed. "
                "Install with: uv sync --extra graphdb-neo4j  "
                'or: pip install "cpp-mcp[graphdb-neo4j]"'
            ) from exc

        try:
            driver = neo4j.GraphDatabase.driver(uri, **kwargs)
            driver.verify_connectivity()
            self._driver = driver
        except Exception as exc:
            raise DBUnreachableError(
                f"Cannot reach graph database at {uri!r}: {exc}"
            ) from exc

    def describe(self, sample_size: int) -> dict[str, Any]:
        """Run live schema queries and return the AC-Q2-2 result dict."""
        if self._driver is None:
            raise DBUnreachableError("Neo4j driver not connected")

        with self._driver.session() as sess:
            node_types = self._describe_nodes(sess, sample_size)
            edge_types = self._describe_edges(sess, sample_size)

        total_nodes = sum(t["count"] for t in node_types)
        total_edges = sum(t["count"] for t in edge_types)

        notes = list(self._build_notes(node_types))

        return {
            "schema_version": SCHEMA_VERSION,
            "backend": self.backend,
            "node_types": _sort_types(node_types),
            "edge_types": _sort_types(edge_types),
            "totals": {"vertices": total_nodes, "edges": total_edges},
            "notes": notes,
        }

    def _describe_nodes(self, sess: Any, sample_size: int) -> list[dict[str, Any]]:
        labels_result = sess.run("CALL db.labels() YIELD label RETURN label")
        labels = [rec["label"] for rec in labels_result]

        node_types: list[dict[str, Any]] = []
        for label in labels:
            if not _SAFE_NAME_RE.match(label):
                logger.warning("Skipping unsafe label name %r", label)
                continue
            count_result = sess.run(
                f"MATCH (n:`{label}`) RETURN count(n) AS c, "
                f"collect(distinct keys(n))[0..$sample] AS sample",
                sample=sample_size,
            )
            rec = count_result.single()
            if rec is None:
                continue
            count = int(rec["c"])
            # Flatten list-of-lists of keys into a sorted unique set.
            raw_keys: list[Any] = rec["sample"] or []
            prop_keys: set[str] = set()
            for entry in raw_keys:
                if isinstance(entry, list):
                    prop_keys.update(str(k) for k in entry)
                else:
                    prop_keys.add(str(entry))
            node_types.append(_node_type_entry(label, count, sorted(prop_keys)))

        return node_types

    def _describe_edges(self, sess: Any, sample_size: int) -> list[dict[str, Any]]:
        types_result = sess.run(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
        )
        rel_types = [rec["relationshipType"] for rec in types_result]

        edge_types: list[dict[str, Any]] = []
        for rel_type in rel_types:
            if not _SAFE_NAME_RE.match(rel_type):
                logger.warning("Skipping unsafe relationship type name %r", rel_type)
                continue
            count_result = sess.run(
                f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS c, "
                f"collect(distinct keys(r))[0..$sample] AS sample",
                sample=sample_size,
            )
            rec = count_result.single()
            if rec is None:
                continue
            count = int(rec["c"])
            raw_keys = rec["sample"] or []
            prop_keys: set[str] = set()
            for entry in raw_keys:
                if isinstance(entry, list):
                    prop_keys.update(str(k) for k in entry)
                else:
                    prop_keys.add(str(entry))
            edge_types.append(_edge_type_entry(rel_type, count, sorted(prop_keys)))

        return edge_types

    def _build_notes(self, node_types: list[dict[str, Any]]) -> list[str]:
        """Build the notes list: two static + optional schema-version notes."""
        notes = [_NOTE_SAMPLE, _NOTE_LIVE]
        # Schema-version mismatch detection is done at the IndraDB level where
        # property access is explicit.  For Neo4j, we'd need an extra query
        # to sample File nodes — done in describe() via the node_types already built.
        file_entry = next((t for t in node_types if t["name"] == "File"), None)
        # Neo4j property-key sampling doesn't give us the values; we'd need an
        # extra MATCH to fetch schema_version values from File samples.
        # We surface only the static notes from Neo4j (no extra round-trip in S4).
        # Schema-version note is fully supported for IndraDB below.
        _ = file_entry  # reserved for future expansion
        return notes

    def close(self) -> None:
        """Release Neo4j driver resources."""
        if self._driver is not None:
            with contextlib.suppress(Exception):
                self._driver.close()
            self._driver = None


# ---------------------------------------------------------------------------
# IndraDB implementation
# ---------------------------------------------------------------------------


class IndraDbSchemaIntrospector(SchemaIntrospector):
    """IndraDB schema introspector using AllVertexQuery / AllEdgeQuery.

    Iterates all vertices/edges, groups by ``t``, samples up to ``sample_size``
    per type to infer property keys via ``get_properties``.
    """

    backend: str = "indradb"

    def __init__(self) -> None:
        self._client: Any = None

    def connect(self, uri: str, **kwargs: Any) -> None:
        """Open an IndraDB gRPC connection (lazy import).

        Raises:
            :exc:`DependencyMissingError`: indradb not installed.
            :exc:`DBUnreachableError`: connection fails.
        """
        try:
            import indradb  # type: ignore[import-untyped]
        except ImportError as exc:
            raise DependencyMissingError(
                "indradb Python driver is not installed. "
                "Install with: uv sync --extra graphdb-indradb  "
                'or: pip install "cpp-mcp[graphdb-indradb]"'
            ) from exc

        from cpp_mcp.graphdb.indradb_driver import _strip_scheme

        host = _strip_scheme(uri)
        try:
            client = indradb.Client(host=host, **kwargs)
            client.ping()
            self._client = client
        except Exception as exc:
            raise DBUnreachableError(
                f"Cannot reach graph database at {uri!r}: {exc}"
            ) from exc

    def describe(self, sample_size: int) -> dict[str, Any]:
        """Run live schema queries and return the AC-Q2-2 result dict."""
        if self._client is None:
            raise DBUnreachableError("IndraDB client not connected")

        import indradb  # safe: module in sys.modules after connect()

        # Gather all vertices grouped by type.
        vertex_groups: dict[str, list[Any]] = {}
        for batch in self._client.get(indradb.AllVertexQuery()):
            for vertex in batch:
                t = vertex.t
                vertex_groups.setdefault(t, []).append(vertex)

        # Gather all edges grouped by type.
        edge_groups: dict[str, list[Any]] = {}
        for batch in self._client.get(indradb.AllEdgeQuery()):
            for edge in batch:
                t = edge.t
                edge_groups.setdefault(t, []).append(edge)

        # Build node_types by sampling property keys.
        node_types: list[dict[str, Any]] = []
        for type_name, vertices in vertex_groups.items():
            count = len(vertices)
            sample = vertices[:sample_size]
            prop_keys = self._vertex_property_keys(sample)
            node_types.append(_node_type_entry(type_name, count, sorted(prop_keys)))

        # Build edge_types by sampling property keys.
        edge_types: list[dict[str, Any]] = []
        for type_name, edges in edge_groups.items():
            count = len(edges)
            sample = edges[:sample_size]
            prop_keys = self._edge_property_keys(sample)
            edge_types.append(_edge_type_entry(type_name, count, sorted(prop_keys)))

        total_nodes = sum(t["count"] for t in node_types)
        total_edges = sum(t["count"] for t in edge_types)

        notes = self._build_notes(vertex_groups, node_types)

        return {
            "schema_version": SCHEMA_VERSION,
            "backend": self.backend,
            "node_types": _sort_types(node_types),
            "edge_types": _sort_types(edge_types),
            "totals": {"vertices": total_nodes, "edges": total_edges},
            "notes": notes,
        }

    def _vertex_property_keys(self, vertices: list[Any]) -> set[str]:
        """Return the union of property keys across the sample.

        S5 confirmed: ``client.get(query.properties())`` yields batches of
        ``VertexProperties`` objects, each with ``.vertex`` and ``.props``
        (list of ``NamedProperty`` with ``.name``/``.value``).
        """
        if not vertices or self._client is None:
            return set()
        import indradb  # safe: in sys.modules

        keys: set[str] = set()
        for vertex in vertices:
            vid = vertex.id
            for prop_batch in self._client.get(
                indradb.SpecificVertexQuery(vid).properties()
            ):
                for vp in prop_batch:  # vp: VertexProperties
                    for np in vp.props:  # np: NamedProperty
                        keys.add(np.name)
        return keys

    def _edge_property_keys(self, edges: list[Any]) -> set[str]:
        """Return the union of property keys across the sample.

        S5 confirmed: ``client.get(query.properties())`` yields batches of
        ``EdgeProperties`` objects, each with ``.edge`` and ``.props``
        (list of ``NamedProperty`` with ``.name``/``.value``).
        """
        if not edges or self._client is None:
            return set()
        import indradb  # safe: in sys.modules

        keys: set[str] = set()
        for edge in edges:
            specific = indradb.SpecificEdgeQuery(edge)
            for prop_batch in self._client.get(specific.properties()):
                for ep in prop_batch:  # ep: EdgeProperties
                    for np in ep.props:  # np: NamedProperty
                        keys.add(np.name)
        return keys

    def _build_notes(
        self,
        vertex_groups: dict[str, list[Any]],
        node_types: list[dict[str, Any]],
    ) -> list[str]:
        """Static notes + optional schema-version skew note (ADR-24)."""
        notes = [_NOTE_SAMPLE, _NOTE_LIVE]

        file_vertices = vertex_groups.get("File", [])
        if not file_vertices:
            return notes

        if self._client is None:
            return notes

        import indradb  # safe: in sys.modules

        # Sample File nodes and collect distinct schema_version values.
        # S5 confirmed: each prop_batch item is a VertexProperties with .vertex and
        # .props (list of NamedProperty with .name/.value).
        observed_versions: set[str | None] = set()
        for vertex in file_vertices:
            vid = vertex.id
            found_any_prop = False
            found_schema_version = False
            for prop_batch in self._client.get(
                indradb.SpecificVertexQuery(vid).properties()
            ):
                for vp in prop_batch:  # vp: VertexProperties
                    for np in vp.props:  # np: NamedProperty
                        found_any_prop = True
                        if np.name == "schema_version":
                            observed_versions.add(str(np.value))
                            found_schema_version = True
            if found_any_prop and not found_schema_version:
                # Vertex has properties but no schema_version — pre-v6 stamp
                observed_versions.add(None)

        if not observed_versions:
            # No properties read at all
            return notes

        has_null = None in observed_versions
        non_null = {v for v in observed_versions if v is not None}

        if has_null and not non_null:
            # All File nodes lack schema_version stamp — pre-v6 graph.
            notes.append(
                f"Graph was ingested under a pre-v6 schema (no schema_version stamp); "
                f"current code is {SCHEMA_VERSION}. Re-run ingest_code to re-stamp."
            )
        elif non_null and any(v != SCHEMA_VERSION for v in non_null):
            # At least one File node has a version that differs from current.
            mismatched = sorted(v for v in non_null if v != SCHEMA_VERSION)
            for observed in mismatched:
                notes.append(
                    f"Graph contains File nodes with schema_version={observed}; "
                    f"current code is {SCHEMA_VERSION}; "
                    f"counts and property keys may differ. Re-run ingest_code to re-stamp."
                )
        # If all non-null versions == SCHEMA_VERSION: no note.

        return notes

    def close(self) -> None:
        """Release IndraDB client resources."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                close_fn = getattr(self._client, "close", None)
                if callable(close_fn):
                    close_fn()
            self._client = None
