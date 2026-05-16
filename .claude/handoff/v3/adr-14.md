# ADR-14: USR → IndraDB vertex UUID mapping
Status: accepted
Date: 2026-05-16
Run: graphdb-multi-v3

## Context

`GraphDriver.NodeRecord.usr` is a libclang Unified Symbol Resolution string
(e.g. `"c:@F@foo#"`). Neo4j's `Neo4jDriver` uses the USR string directly as
a property and MERGEs on it — Cypher labels work with arbitrary string keys.

IndraDB models a vertex as `indradb.Vertex(id: UUID, t: Identifier)` — the
identifier is a UUID, not an arbitrary string. We therefore need a function
`usr → uuid.UUID` that is:

- **Deterministic** (US-G2/AC-3): same USR → same UUID, across processes and
  across runs.
- **Collision-resistant**: distinct USRs must map to distinct UUIDs with
  cryptographically negligible probability.
- **Stateless**: no lookup table to maintain, no DB round-trip to derive the
  ID. Bulk upserts must be computable from the input alone.

This is load-bearing for US-G2/AC-4 (idempotent `upsert_nodes`) and
US-G2/AC-5 (idempotent `upsert_edges`) — the latter must look up the
endpoint UUIDs from the source/target USRs deterministically.

## Decision

Use **UUIDv5** with a fixed project namespace:

```python
# src/cpp_mcp/graphdb/indradb_driver.py
import uuid

# Project-scoped namespace for cpp-mcp USR → vertex-id derivation.
# Generated once and pinned here for cross-run stability.
NS_CPPMCP_USR = uuid.UUID("8f6e2c1b-7d3a-4f59-9a4b-1c0d2e5f8a91")

def usr_to_vid(usr: str) -> uuid.UUID:
    return uuid.uuid5(NS_CPPMCP_USR, usr)
```

Properties:
- `uuid.uuid5(namespace, name)` is defined in RFC 4122 as SHA-1 over
  `namespace + name`. Pure function — no state, no I/O.
- Two USR strings collide only if SHA-1 collides — cryptographically
  negligible for the input domain.
- The namespace UUID literal is **pinned in this ADR**. Changing it would
  invalidate every previously-written vertex in any user's IndraDB. It is
  treated as a stable wire format constant.

Storage of the original USR string:
- Each vertex also gets a `usr` property (`set_properties` with the original
  string). This (a) makes the USR readable back from the DB without inverse
  hashing (which is impossible) and (b) matches the Neo4j convention of
  having `usr` as a vertex property (current `neo4j_driver.py:84`).

## Alternatives considered

1. **Random `uuid.uuid4()` per vertex** — rejected. Breaks idempotency; the
   2nd export creates fresh vertices. Fails US-G2/AC-3, AC-4, AC-5.

2. **MD5 hex truncated to UUID** — rejected. (a) MD5 is broken for collision
   resistance; (b) "truncate to UUID" requires an ad-hoc layout that isn't
   `uuid.UUID`-canonical, increasing the chance of off-by-one bugs in
   round-trip; (c) `uuid5` is the stdlib idiom.

3. **SHA-256 truncated to 128 bits** — considered. Slightly more
   collision-resistant than SHA-1-based `uuid5`, but (a) not a UUID by
   construction (no version/variant bits → some IndraDB consumers reject
   non-canonical UUIDs), (b) stdlib has no helper, and (c) `uuid5`'s
   collision probability is already negligible for our input volume
   (millions of USRs, not 2^64).

4. **Maintain a USR→UUID mapping table inside IndraDB** — rejected.
   Requires a round-trip on every node and every edge endpoint, breaks
   statelessness, requires conflict resolution on concurrent writers. Not
   needed when a pure function suffices.

5. **Use the USR string as the vertex `t` (type) identifier instead of a
   label** — rejected. IndraDB's `Identifier` is for type/kind grouping,
   not unique IDs; reusing it as a primary key obscures the schema and
   prevents querying by label.

## Consequences

Positive:
- Pure, stateless, deterministic — testable without IndraDB.
- Idempotency of `upsert_nodes` / `upsert_edges` reduces to "IndraDB's
  `create_vertex` / `create_edge` is no-op on existing identical record",
  which the upstream API guarantees.
- Edges can reference source/target USRs without first reading vertex IDs
  back.

Negative / follow-ups:
- The namespace UUID `8f6e2c1b-7d3a-4f59-9a4b-1c0d2e5f8a91` is now a wire
  format constant. **Do not change it.** A future migration (e.g. to wider
  hashes) requires an ADR superseding this one and a re-export of every
  existing IndraDB database.
- Round-tripping the USR string requires reading the `usr` property —
  there's no inverse function from UUID back to USR. Acceptable; we never
  needed an inverse.

## References

- `requirements.md` US-G2/AC-3, AC-4, AC-5.
- `src/cpp_mcp/graphdb/driver.py` (`NodeRecord.usr`).
- `src/cpp_mcp/graphdb/neo4j_driver.py:84` (USR as property convention).
- Python stdlib: `uuid.uuid5(namespace, name)` (RFC 4122 §4.3).
- IndraDB API: `Vertex(id, t)` with `id: UUID`. Source:
  `https://indradb.github.io/python-client/indradb/` (fetched 2026-05-16).
- adr-12 (dispatch).
