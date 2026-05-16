---
run_id: graphdb-multi-v3
stage: architect
date: 2026-05-16
status: final
reads: [requirements.md, scenarios.md, src/cpp_mcp/graphdb/driver.py, src/cpp_mcp/graphdb/__init__.py, src/cpp_mcp/graphdb/neo4j_driver.py, src/cpp_mcp/tools/export_to_graphdb.py, src/cpp_mcp/core/error_envelope.py]
adrs: [adr-12.md (dispatch), adr-13.md (DEPENDENCY_MISSING), adr-14.md (USR→UUID), adr-15.md (property serialization)]
---

# Design: Pluggable GraphDB Backends (Neo4j + IndraDB)

## 1. Scope

Add `IndraDBDriver` as a peer to the existing `Neo4jDriver`, both reached
through the `GraphDriver` Protocol (ADR-7). Backend selection is driven by the
URI scheme of `db_uri`; no new tool arguments. Add a new error code
`DEPENDENCY_MISSING` to distinguish "Python driver package not installed"
from "database unreachable".

Out of scope: embedded backends, Memgraph/FalkorDB, auth, migration tooling,
health-checks, async, benchmarking.

## 2. Reference architecture

```
cpp_export_to_graphdb (tool, on session.executor worker thread)
  │
  ├─► 1. INVALID_ARGUMENT  (empty db_uri / build_path)
  ├─► 2. INVALID_ARGUMENT  (unknown URI scheme — via select_driver)
  ├─► 3. PATH_VIOLATION    (validate_path on build & input)
  ├─► 4. FILE_NOT_FOUND    (path checks)
  │
  ├─► select_driver(db_uri) ── returns un-connected GraphDriver ──┐
  │                                                                │
  │      scheme ∈ {bolt, bolt+s, bolt+ssc, neo4j, …}  → Neo4jDriver()
  │      scheme ∈ {indradb, grpc, indradb+grpc}        → IndraDBDriver()
  │                                                                │
  ├─► driver.connect(db_uri)  ◄───────────────────────────────────┘
  │       │
  │       ├─► lazy import (`neo4j` or `indradb`)
  │       │     ImportError → DependencyMissingError (5. DEPENDENCY_MISSING)
  │       └─► driver-specific connect; failure → DBUnreachableError (6. DB_UNREACHABLE)
  │
  └─► per-file: collect_cpp_files → parse → export_file(driver) → driver.close()
```

The ordering above is enforced by the tool body (`_do_export_to_graphdb`). The
new step "2." inserts unknown-scheme INVALID_ARGUMENT before path checks, per
scenarios "INVALID_ARGUMENT fires before PATH_VIOLATION/FILE_NOT_FOUND".

## 3. Module map (delta vs current tree)

| Path | State | Purpose |
|------|-------|---------|
| `src/cpp_mcp/graphdb/__init__.py` | **modify** | Replace `make_driver` with `select_driver(db_uri) -> GraphDriver`. `select_driver` returns an **unconnected** instance and validates the scheme; raises `InvalidArgumentError` on unknown. Kept module-private `_SCHEME_TO_DRIVER` dispatch table. |
| `src/cpp_mcp/graphdb/driver.py` | unchanged | Protocol + TypedDicts (ADR-7). |
| `src/cpp_mcp/graphdb/neo4j_driver.py` | **modify (1 line)** | `connect()` raises `DependencyMissingError` on `ImportError` (was `DBUnreachableError`). Fix for US-G1/AC-3 miswire. |
| `src/cpp_mcp/graphdb/indradb_driver.py` | **new** | `IndraDBDriver` (see §5). |
| `src/cpp_mcp/graphdb/cognee_driver.py` | unchanged | Out of scope for v3. Still reachable via `cognee://` if someone calls it directly; we do **not** wire it into `select_driver` here because v3 stories scope dispatch to Neo4j + IndraDB only. (Note left in adr-12.) |
| `src/cpp_mcp/core/error_envelope.py` | **modify** | Add `ErrorCode.DEPENDENCY_MISSING`, `DependencyMissingError`, and `_EXC_TO_CODE` row **above** `DBUnreachableError` to prevent shadowing. |
| `src/cpp_mcp/tools/export_to_graphdb.py` | **modify** | Replace `driver = Neo4jDriver()` at line 85 with `driver = select_driver(db_uri); driver.connect(db_uri)`. Move `DependencyMissingError` re-raise alongside existing `DBUnreachableError` re-raise. |
| `pyproject.toml` | **modify** | Split `graphdb` extra into `graphdb-neo4j`, `graphdb-indradb`, and a `graphdb` meta-extra. (US-G4) |
| `tests/bdd/features/export_to_indradb.feature` | **new** | US-G5 BDD. |
| `tests/bdd/test_export_to_indradb.py` | **new** | pytest-bdd step impls. |
| `tests/fixtures/indradb-compose.yml` | **new** | local daemon for `INDRADB_TEST_URI` runs. |
| `tests/unit/test_driver_dispatch.py` | **new** | scheme → class table assertions. |
| `tests/unit/test_pyproject_extras.py` | **new** | extras assertions (US-G4/AC-2). |

## 4. `select_driver` design (US-G3)

```python
# graphdb/__init__.py (sketch — final form in implementation)
from cpp_mcp.core.error_envelope import InvalidArgumentError
from cpp_mcp.graphdb.driver import GraphDriver

_NEO4J_SCHEMES = frozenset({"bolt", "bolt+s", "bolt+ssc",
                            "neo4j", "neo4j+s", "neo4j+ssc"})
_INDRADB_SCHEMES = frozenset({"indradb", "grpc", "indradb+grpc"})


def select_driver(db_uri: str) -> GraphDriver:
    """Return an *unconnected* GraphDriver instance for db_uri's scheme.

    Raises InvalidArgumentError on unknown / empty / missing-scheme input.
    Caller is responsible for invoking driver.connect(db_uri) afterwards.
    """
    if not db_uri or "://" not in db_uri:
        raise InvalidArgumentError(
            f"db_uri must include a scheme (got {db_uri!r}); supported: "
            f"{sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
        )
    scheme = urlparse(db_uri).scheme
    if scheme in _NEO4J_SCHEMES:
        from cpp_mcp.graphdb.neo4j_driver import Neo4jDriver
        return Neo4jDriver()
    if scheme in _INDRADB_SCHEMES:
        from cpp_mcp.graphdb.indradb_driver import IndraDBDriver
        return IndraDBDriver()
    raise InvalidArgumentError(
        f"Unsupported db_uri scheme {scheme!r}; supported: "
        f"{sorted(_NEO4J_SCHEMES | _INDRADB_SCHEMES)}"
    )
```

Key properties:
- **No I/O.** Just scheme dispatch.
- **No package import** until the matched branch runs (`neo4j` / `indradb` are
  loaded lazily inside the driver's `connect`, not here). This preserves the
  default-install constraint C-G5.
- **`InvalidArgumentError`** (not `ValueError`) so the existing
  `wrap_tool` envelope mapping returns `INVALID_ARGUMENT` without a new
  handler.
- The current `make_driver(uri, **kwargs)` function (which also connects)
  is **removed**; no external caller depends on it (verified by grep). See
  adr-12 §Alternatives.

## 5. `IndraDBDriver` design (US-G2)

### 5.1 Class shape

```python
class IndraDBDriver:
    def __init__(self) -> None:
        self._client: Any = None   # indradb.Client
        self._closed: bool = False

    def connect(self, uri: str, **kwargs: Any) -> None: ...
    def upsert_nodes(self, batch: list[NodeRecord]) -> int: ...
    def upsert_edges(self, batch: list[EdgeRecord]) -> int: ...
    def close(self) -> None: ...
```

### 5.2 `connect(uri, **kwargs)`

```python
try:
    import indradb  # lazy
except ImportError as exc:
    raise DependencyMissingError(
        'indradb Python driver is not installed. '
        'Install with: pip install "cpp-mcp[graphdb-indradb]"'
    ) from exc

host = _strip_scheme(uri)  # "indradb://host:port" → "host:port"
try:
    self._client = indradb.Client(host=host, **kwargs)
    self._client.ping()    # eager connectivity check; mirrors Neo4j.verify_connectivity()
except Exception as exc:
    raise DBUnreachableError(
        f"Cannot reach graph database at {uri!r}: {exc}"
    ) from exc
```

`_strip_scheme` handles all three accepted schemes by removing the
`<scheme>://` prefix and returning `host:port`. If port is absent, defaults to
`27615` (IndraDB default per upstream).

### 5.3 Vertex identifier — USR → UUID

See **adr-14**. Each vertex is identified by `uuid.uuid5(NS_CPPMCP_USR, usr)`
where `NS_CPPMCP_USR` is a fixed UUIDv4 literal pinned in adr-14. This makes
`(usr) → uuid` a pure function — deterministic across runs (US-G2/AC-3) and
the basis for idempotent upsert (US-G2/AC-4).

### 5.4 `upsert_nodes(batch)` — idempotency

Implementation per node:
1. `vid = uuid.uuid5(NS_CPPMCP_USR, rec["usr"])`
2. `vtype = indradb.Identifier(rec["label"])` (label = vertex type)
3. Call `client.create_vertex(indradb.Vertex(vid, vtype))` — IndraDB's
   `create_vertex` is **upsert-like for the same id+type**; same id with
   different type would conflict, but our schema fixes `label` per USR.
4. For each `(k, v)` in `rec["props"] | {"usr": usr}`:
   - If `v` is a JSON scalar (str/int/float/bool/None) → write directly.
   - Else → JSON-encode with a debug log (per adr-15).
   - `client.set_properties(SpecificVertexQuery(vid), name=k, value=v_json)`

Idempotency:
- Same USR → same UUID → `create_vertex` is a no-op the 2nd time (or returns
  False; either way, vertex count stable).
- `set_properties` is overwrite-semantics; running twice yields the same
  property values.

Returns: number of records processed (matches Neo4j's "1 per record" idiom).

### 5.5 `upsert_edges(batch)` — idempotency

Per edge:
1. `src_vid = uuid.uuid5(NS_CPPMCP_USR, rec["source_usr"])`
2. `tgt_vid = uuid.uuid5(NS_CPPMCP_USR, rec["target_usr"])`
3. `etype = indradb.Identifier(rec["edge_type"])`
4. `edge = indradb.Edge(outbound_id=src_vid, t=etype, inbound_id=tgt_vid)`
5. `client.create_edge(edge)` — IndraDB edges keyed by `(outbound, type, inbound)`,
   so the same triple twice is a no-op.
6. For each prop, `set_properties(SpecificEdgeQuery(edge), name=k, value=v_json)`.

Returns: number of records processed.

### 5.6 `close()` — idempotent

```python
if self._closed:
    return
try:
    if self._client is not None:
        with contextlib.suppress(Exception):
            # indradb.Client wraps a grpc channel; close it if exposed,
            # else release reference and let gc finalize.
            close_fn = getattr(self._client, "close", None)
            if callable(close_fn):
                close_fn()
finally:
    self._client = None
    self._closed = True
```

Calling twice is safe — second call short-circuits on `_closed`.

### 5.7 Threading

`upsert_nodes` / `upsert_edges` run on `session.executor` (a single worker
thread). The IndraDB Python client is sync; no async loop interaction. No
shared state across drivers (each call to the tool creates a fresh driver
instance via `select_driver`).

## 6. Error code & exception wiring (US-G1)

See **adr-13**.

- New: `ErrorCode.DEPENDENCY_MISSING = "DEPENDENCY_MISSING"`.
- New: `DependencyMissingError(Exception)` in `core/error_envelope.py`.
- `_EXC_TO_CODE` entry inserted **before** `DBUnreachableError`:
  ```python
  (DependencyMissingError, ErrorCode.DEPENDENCY_MISSING),
  (DBUnreachableError,     ErrorCode.DB_UNREACHABLE),
  ```
  Order matters because Python's `isinstance` short-circuits on the first
  match — putting `DependencyMissingError` above `DBUnreachableError` means
  even if a future refactor makes one inherit from the other, classification
  stays correct.
- Both `Neo4jDriver.connect` and `IndraDBDriver.connect` raise
  `DependencyMissingError` on `ImportError`. This fixes the v2 miswire at
  `neo4j_driver.py:51-54`.
- The export tool re-raises `DependencyMissingError` from `driver.connect`
  alongside `DBUnreachableError`, before path/parse work — DEPENDENCY_MISSING
  fires before any DB I/O (scenarios "DEPENDENCY_MISSING fires before any
  database I/O attempt"). Note that `DependencyMissingError` is raised
  *inside* `connect()` itself, before any socket open.

## 7. Packaging (US-G4)

```toml
[project.optional-dependencies]
graphdb-neo4j = ["neo4j>=5,<6"]
graphdb-indradb = ["indradb>=3.0,<4"]
graphdb = ["cpp-mcp[graphdb-neo4j]", "cpp-mcp[graphdb-indradb]"]
```

- The existing `graphdb = ["neo4j>=5.0"]` extra is replaced by a meta-extra.
  This is technically a **rename**; downstream installers using
  `pip install cpp-mcp[graphdb]` keep working and now additionally get
  IndraDB. We accept that this pulls IndraDB into installs that previously
  only needed Neo4j; this is documented in the runbook (US-G6/AC-2). Users
  who want Neo4j-only must switch to `cpp-mcp[graphdb-neo4j]`.
- `tests/unit/test_pyproject_extras.py` parses `pyproject.toml` with
  `tomllib` (stdlib, Py3.11+) and asserts the three extras and their pins
  (US-G4/AC-2).

## 8. Test strategy summary (handed to senior-developer for elaboration)

| Layer | Story | Key scenarios |
|-------|-------|---------------|
| Unit  | US-G1 | `test_envelope_codes` extended; `test_dependency_missing_neo4j_miswire` ensures `Neo4jDriver().connect()` w/o `neo4j` raises `DependencyMissingError`. |
| Unit  | US-G3 | `test_driver_dispatch` — scheme→class table; unknown scheme → `InvalidArgumentError`; empty / no-`://` → same. |
| Unit  | US-G4 | `test_pyproject_extras` — parse `pyproject.toml`, assert three extras & pins. |
| Unit  | US-G2 | `test_indradb_driver` — fake `indradb` module installed via `sys.modules` fixture; verify UUID determinism, idempotency counters, prop serialization, close-twice. |
| BDD   | US-G5 | `features/export_to_indradb.feature` — fake-driver scenarios unconditional; `@indradb` tag gates live-daemon scenarios on `INDRADB_TEST_URI`. |

The fake IndraDB driver lives in `tests/fixtures/fake_indradb.py` and is the
test surrogate for both unit and BDD layers (mirrors `tests/fixtures/`
patterns already in the repo).

## 9. Open-question resolutions (recorded inline; see ADRs)

| OQ | Resolution | Recorded |
|----|------------|----------|
| OQ-G1 | Sync only for v3. Async deferred — Protocol stays sync. | adr-12 |
| OQ-G2 | JSON-encode non-scalar props; emit `logger.debug` (not warning — too noisy in batch). | adr-15 |
| OQ-G3 | Lazy import inside each driver's `connect()`. Mirrors current Neo4j pattern; `select_driver` does no import. | adr-12 |
| OQ-G4 | `DependencyMissingError` is classified as a **setup error** (actionable install hint), not a runtime/auth failure. Metrics tag (if/when added) should be `errors{class="setup"}`. | adr-13 |
| OQ-G5 | Daemon health-check before export — out of v3 scope; tracked here for future. | — |

## 10. Validation against compatibility constraints

| C-Gx | How this design satisfies it |
|------|------------------------------|
| C-G1 | Tool name, args, types unchanged. `db_uri: str` is still the sole target identifier. |
| C-G2 | Neo4jDriver code path is preserved exactly except for the `ImportError → DependencyMissingError` line. All other Neo4j tests continue to pass. |
| C-G3 | Envelope shape unchanged. `DEPENDENCY_MISSING` is **additive**. |
| C-G4 | `select_driver` is pure scheme-dispatch; no env vars consulted. |
| C-G5 | `select_driver` does no import of `neo4j` / `indradb`. Lazy imports live inside each driver's `connect()`. |
| C-G6 | `connect()` raises `DependencyMissingError` *before* opening any socket — verified by scenario "DEPENDENCY_MISSING fires before any database I/O attempt". |
| C-G7 | Existing 472 tests untouched (Neo4j path semantic-identical); 1 new optional skip for live IndraDB. |
| C-G8 | Executor model preserved — driver instantiation and connect happen inside `_do_export_to_graphdb`, which already runs on `session.executor`. |

## 11. References

- ADR-7 (`v1/adr-7.md`) — `GraphDriver` Protocol.
- ADR-8 (`v1/adr-8.md`) — error envelope.
- ADR-12 (`adr-12.md` this run) — dispatch design.
- ADR-13 (`adr-13.md` this run) — `DEPENDENCY_MISSING` error code.
- ADR-14 (`adr-14.md` this run) — USR → IndraDB UUID mapping.
- ADR-15 (`adr-15.md` this run) — property serialization.
- IndraDB Python client API surface: `indradb.Client(host=...)`,
  `Vertex(id, t)`, `Edge(outbound_id, t, inbound_id)`, `Identifier`,
  `BulkInserter`, `SpecificVertexQuery`, `set_properties`. Source:
  `https://indradb.github.io/python-client/indradb/` (fetched 2026-05-16).
