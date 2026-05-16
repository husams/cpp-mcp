# ADR-15: Property serialization for IndraDB (resolves OQ-G2)
Status: accepted
Date: 2026-05-16
Run: graphdb-multi-v3

## Context

`NodeRecord.props` and `EdgeRecord.props` are typed as `dict[str, Any]`
(see `src/cpp_mcp/graphdb/driver.py`). In practice the C++ exporter
(`graphdb/exporter.py`) emits JSON-scalar values today: strings (`name`,
`path`, `spelling`), ints (`line`, `col`), and bools. However the Protocol
admits `Any`, and future exporter changes could introduce nested dicts /
lists (e.g. parameter signatures, attribute lists).

IndraDB's `NamedProperty` stores values as JSON. The Python client
serialises scalars natively but raises on arbitrary Python objects. Neo4j's
property model is similar (scalars + arrays of scalars; nested objects must
be JSON-encoded). The `Neo4jDriver` today gets away with this because all
in-flight props are scalars; no defensive serialization exists.

We must decide what `IndraDBDriver` does when a future prop value is
non-scalar.

## Decision

Inside `IndraDBDriver.upsert_nodes` / `upsert_edges`, each `(key, value)`
pair from `props` is normalised by a small helper:

```python
import json
import logging

logger = logging.getLogger(__name__)

_SCALAR = (str, int, float, bool, type(None))

def _normalise_prop(key: str, value: Any) -> Any:
    if isinstance(value, _SCALAR):
        return value
    try:
        encoded = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        logger.debug(
            "indradb prop %r is not JSON-serialisable; storing repr()", key
        )
        return repr(value)
    return encoded
```

Behaviour:
- **JSON scalars** pass through unchanged.
- **Lists / dicts / tuples / other JSON-encodable** → encoded as a JSON
  string (`json.dumps(..., sort_keys=True, default=str)`). `sort_keys=True`
  preserves idempotency: re-export of the same dict yields the same byte
  string. `default=str` survives stray `pathlib.Path` values.
- **Unencodable** (rare; circular refs, custom objects without `__str__`-
  friendly repr) → `repr(value)`. Logged at `debug` level (not warning —
  the C++ exporter is a tight loop and we do not want logger amplification).
- **No raise.** The export tool must not fail on prop weirdness; the
  Protocol contract is that `upsert_*` writes the batch best-effort.

OQ resolution recorded:
- **OQ-G2**: JSON-encode non-scalar props; log at `debug`. Documented in
  `implementation-notes.md` once the developer fills it in.

The same helper is **not** applied to `Neo4jDriver` in this run — Neo4j's
own driver raises a clearer error on non-scalars, and we have no observed
failure case to fix. Scope kept minimal.

## Alternatives considered

1. **Drop non-scalar props with a warning** — rejected. Silent data loss is
   worse than a JSON string the operator can decode. Warning-level logging
   would also spam in tight loops.

2. **Raise on non-scalar** — rejected. Breaks the contract that `upsert_*`
   writes the batch; turns a benign exporter improvement into a tool
   failure. Also asymmetric with Neo4j path which would also fail today —
   we are not regressing parity by being lenient here.

3. **Apply the same helper to `Neo4jDriver` for parity** — deferred. No
   current failure justifies the change; doing it now expands blast radius
   for v3 unnecessarily. Tracked as a follow-up if exporter starts emitting
   non-scalars.

4. **Recursively encode each leaf and store as nested IndraDB properties**
   — rejected. IndraDB doesn't support nested property graphs natively; we
   would have to invent a key-flattening convention (`props.foo.bar`),
   making round-trip ambiguous.

## Consequences

Positive:
- IndraDB driver is robust against future exporter changes without further
  Protocol changes.
- Idempotency preserved: `sort_keys=True` makes the encoded string a
  deterministic function of input.

Negative / follow-ups:
- Round-trip asymmetry: a `dict` prop in input comes back as a JSON string
  on read. Callers who need structured access must `json.loads(...)` it.
  This is acceptable because no current consumer reads props back
  structurally — the export is one-way to graph storage.
- `Neo4jDriver` and `IndraDBDriver` differ in tolerance for non-scalars
  until follow-up; documented in `implementation-notes.md`.

## References

- `requirements.md` US-G2/AC-6 (props stored as vertex properties).
- `scenarios.md` OQ-G2 (open question → resolved here).
- `src/cpp_mcp/graphdb/driver.py` (`NodeRecord.props: dict[str, Any]`).
- IndraDB API: `NamedProperty(name, value)` with JSON-scalar value. Source:
  `https://indradb.github.io/python-client/indradb/` (fetched 2026-05-16).
- adr-12 (dispatch), adr-14 (vertex id).
