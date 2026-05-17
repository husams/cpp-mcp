# ADR-25: Variable split transition path — deprecate `Variable` on write; tolerate on read

Status: accepted
Date: 2026-05-17
Stage: cpp-mcp v7 — S1
Supersedes: none (extends ADR-7 schema, ADR-24 schema-version stamping)

---

## Context

Stage S1 of v7 splits the `Variable` node into `Field` (non-static class data
member) and `GlobalVariable` (all other variables). OQ-1 in
`requirements.md`/`scenarios.md` asks whether `Variable` should:

  - (a) be removed from the write path entirely, OR
  - (b) be retained as an additional/parent label alongside `Field`/`GlobalVariable`.

Evidence from the codebase (`src/cpp_mcp/graphdb/`, **not** `graphdb_export/`
as the CHARTER states — see "Charter path typo" below):

  - `neo4j_driver.py:90` emits one label per node:
    `MERGE (n:`{label}` {usr: $usr}) SET n += $props`. Multi-label is **not**
    implemented; option (b) would require driver changes and a label
    selection strategy that is out of scope for S1.
  - `indradb_driver.py:155` constructs `indradb.Vertex(vid, label)` — a single
    string vertex type. IndraDB has no native multi-label concept; option (b)
    would require either emitting parallel "shadow" vertices or storing the
    extra label as a property — neither matches the Neo4j semantic and both
    invalidate the existing introspector grouping (`vertex.t` → group key in
    `schema_introspector.py:336`).
  - `schema_introspector.py` reads node types from `db.labels()` (Neo4j) or
    by grouping on `vertex.t` (IndraDB); both surfaces are inherently
    single-label.
  - NC-2 already requires the read path to tolerate legacy v1 graphs typed
    `Variable`. The introspector is live (ADR-24), so any legacy `Variable`
    nodes still in the store will surface in `describe_graph_schema` output
    without any code change.

Additional gaps discovered during architectural review (must be resolved
inside this ADR because OQ-1's choice cascades):

  1. **PARM_DECL classification.** `exporter.py:106` currently maps
     `PARM_DECL → Variable`. Parameters are neither fields nor globals; S2
     introduces a dedicated `Parameter` node. S1 must say what to emit for
     parameters in the interim.
  2. **`schema_version` value format.** Code uses `SCHEMA_VERSION: str = "v1"`
     (string). Requirements/scenarios write "schema_version: 2" (suggestive
     of int). Pick one and keep the wire format stable.
  3. **OQ-2..OQ-7** (six dependent open questions across the five S1 stories).

Forces:

  - F1 (minimal change): Two backend drivers and a live introspector all
    assume single-label / single-type. Option (b) is a multi-week refactor.
  - F2 (forward-compatibility): S2 will add `Type`, `Parameter`; S5 adds
    `Enum`, `Enumerator`. Each splits or augments existing node kinds. The
    transition pattern set in S1 will be reused.
  - F3 (queryability): The whole point of the split is to let consumers
    write schema-typed queries (`MATCH (f:Field)…` / `WHERE v.t = "Field"`).
    Option (b) keeps the parent `Variable` label but defeats most of the
    queryability gain because every query still has to choose between the
    parent label and a leaf label.
  - F4 (backward read): v1 graphs in production must remain
    queryable/introspectable (NC-2). The split must not affect the read path.

---

## Decision

### D1 (resolves OQ-1, OQ-7)

**Deprecate `Variable` on the write path.** From S1 onward the exporter emits
`Field`, `GlobalVariable`, and (transitionally) `Variable` only for `PARM_DECL`
cursors (see D2). `NODE_VARIABLE` constant is retained in
`graphdb/schema.py` as a read-side compatibility label and remains in
`ALL_NODE_TYPES` so that schema validation and downstream callers that
import the constant don't break.

Rationale: option (b) requires driver-level multi-label support neither
backend has. The single-label constraint is a hard architectural fact, not
a preference. Option (a) is the only one consistent with both backends
without a multi-week refactor outside S1 scope.

Read path: the introspector is live (ADR-24). If a deployed graph still
contains nodes typed `Variable`, `describe_graph_schema` surfaces them as a
node type entry alongside `Field`/`GlobalVariable`. This is the correct
behavior; no special-case code is needed. **OQ-7 resolved**: do not add
suppression logic for legacy `Variable` entries — they appear naturally and
truthfully reflect the live graph's state.

### D2 (resolves the PARM_DECL gap surfaced by review)

**PARM_DECL continues to emit as `Variable` in S1.** Parameters are neither
fields nor globals; the correct target is `Parameter` (S2). For S1 we keep
the existing emission so that downstream call-edge construction and
REFERENCES wiring (which already rely on PARM_DECL node presence) keep
working. In S2 the `Variable` constant is removed from the write path
entirely as part of the `Parameter` introduction.

Consequence: after S1, a fresh export against a TU with parameters will
contain `Variable` nodes whose `usr` resolves to a PARM_DECL. This is
expected and not a defect. Tests in S1 must assert that field/global
PARM_DECL classification does **not** produce a `Variable` for fields or
namespace-scope variables, but tests must **not** assert "no Variable
nodes" globally.

### D3 (resolves OQ-2)

**Fields of anonymous structs/unions embedded as class members are emitted
as `Field`** and the `MEMBER_OF` edge targets the **nearest named
enclosing class/struct**. libclang exposes anonymous record members as if
declared in the enclosing scope (`FIELD_DECL` cursors with the enclosing
class as semantic parent); the exporter walks via lexical parent today and
the named-enclosing rule is a one-line lookup. Document in
`implementation-notes.md`.

### D4 (resolves OQ-3)

**Union members default to `access: public`** per ISO C++. libclang
`CX_CXXPublic` is the expected access value for union members. Implementer
must verify against the installed libclang version during development and
record the verification in `implementation-notes.md`; if libclang returns
`CX_CXXInvalidAccessSpecifier` for unions, the exporter applies a
union-specific override to `public`.

### D5 (resolves OQ-4)

**Emit `access` on ALL `MEMBER_OF` edges** (fields, methods, constructors,
destructors, nested types). Uniform property surface; future-proof for S4
which adds `is_virtual` and an `access` property on `INHERITS`. The
`exporter.py:312` block that decides MEMBER_OF already reads the cursor and
can read `cursor.access_specifier` in the same pass at zero cost.

### D6 (resolves OQ-5)

**`storage_class` on a non-static `Field` node = `"none"`.** Keeps the
property mono-typed (always a non-empty string), matches scenario
S1-3-SC7, and avoids "absent property" branches in query code.
Alternatives considered:

  - omit the property — forces query code to handle `null` everywhere,
    breaks `describe_graph_schema` property-key sampling consistency.
  - `"auto"` — semantically incorrect (auto is a deduced storage-class
    keyword in C++, not "no storage class").

### D7 (resolves OQ-6)

**Enforce the invariant at classification time:** static class data
members are typed `GlobalVariable` *unconditionally*. There is no code path
that produces `is_static: true` on a `Field` node — the classifier itself
prevents it. If a future libclang quirk causes a static member to slip
through, the exporter logs a `logger.warning` and re-classifies to
`GlobalVariable`. No exception is raised (the export must complete).

### D8 (schema_version format — surfaced by review)

**`SCHEMA_VERSION` becomes `"v2"`** (string), preserving the existing
wire format. Requirements/scenarios prose says "schema_version: 2" — the
developer must read this as the integer-looking string `"v2"`, not the
int `2`. design.md flags this so QA does not write tests asserting
`response["schema_version"] == 2`.

---

## Classifier (canonical rule for D1+D2+D7)

```
cursor.kind.name           classification
─────────────────────      ───────────────────────────────────────────────
FIELD_DECL                 if cursor.is_static_member(): GlobalVariable
                           else:                          Field
VAR_DECL                   GlobalVariable
                           (covers namespace-scope, file-scope static, extern,
                            thread_local, static class data members in their
                            out-of-class definition form)
PARM_DECL                  Variable   (transitional; → Parameter in S2)
```

libclang exposes `is_static_member()` on `Cursor`. If unavailable on the
pinned libclang version, fall back to `cursor.storage_class ==
StorageClass.STATIC` for FIELD_DECL cursors.

---

## Alternatives considered

### Alt-A: Keep `Variable` as parent label (multi-label)

Rejected. Neither backend supports multi-label as currently wired:
`neo4j_driver.py:90` uses a single backtick-quoted label; `indradb.Vertex`
takes a single `t` string. Implementing multi-label would require
(i) extending `NodeRecord` to carry a label list, (ii) rewriting the Neo4j
MERGE to compose multiple labels, (iii) deciding an IndraDB shadow-vertex
strategy or a `labels` JSON property, (iv) rewriting the introspector
grouping logic. Out of S1 scope and contradicts the wiki PRD's "split"
language.

### Alt-B: Emit only `Field` and `GlobalVariable`, drop `Variable` constant entirely (including from PARM_DECL)

Rejected for S1 because PARM_DECL has no correct destination until `Parameter`
exists (S2). The two least-bad options are: drop parameter nodes (breaks
existing REFERENCES wiring that targets parameters), or misclassify them
as `GlobalVariable` (semantically wrong, pollutes the very query the
split is meant to enable). Deferring the parameter cleanup to S2 keeps the
S1 commit minimal and reversible.

### Alt-C: Emit `Variable` and `Field`/`GlobalVariable` simultaneously (duplicate nodes)

Rejected. Doubles vertex count, doubles ingestion time, breaks USR
uniqueness (USR per cursor is unique; duplicate vertices would collide on
upsert). No backend benefit.

---

## Consequences

### Positive

  - Both backends require only `_KIND_TO_NODE_TYPE` rewrites plus
    `is_static_member()` branching in `exporter.py`; driver code is
    untouched.
  - `query_graphdb` consumers immediately get type-discriminated queries
    (`access:private`, `Field` vs `GlobalVariable`) without post-filtering.
  - Forward path for S2 (`Parameter`), S5 (`Enum`/`Enumerator`) is
    established: split → deprecate → live introspector surfaces both old
    and new types until graphs are re-ingested.
  - NC-2 (v1 read compatibility) is satisfied by construction: nothing on
    the read path special-cases the new labels; legacy `Variable` nodes
    are simply listed as one more type in `describe_graph_schema`.

### Negative

  - PARM_DECL transiently produces `Variable` nodes even in S1-exported
    graphs. Test fixtures and assertions must account for this.
  - `SCHEMA_VERSION` constant change from `"v1"` to `"v2"` triggers the
    IndraDB skew note (`schema_introspector.py:464`) for any pre-existing
    v1 graph — this is the desired behavior but operators must understand
    the new note text.
  - Schema introspector for Neo4j currently doesn't query File-node
    `schema_version` values (`schema_introspector.py:262-268`). Skew
    detection on Neo4j therefore won't fire automatically for legacy
    graphs — same blind spot as v1, not regressed by S1. Filed as
    follow-up for S6 introspector rewrite.

### Follow-ups (out of scope for S1)

  - F-1 (S2): `Parameter` node type; remove `NODE_VARIABLE` from write
    path entirely; remap `PARM_DECL`.
  - F-2 (S6): Neo4j introspector reads `schema_version` from File nodes
    so skew detection works across backends.
  - F-3 (S1 implementation): developer verifies libclang
    `is_static_member()` availability on pinned libclang; documents
    fallback in `implementation-notes.md`.
  - F-4 (S1 implementation): developer verifies libclang access-specifier
    behavior for union members; documents in `implementation-notes.md`.

---

## References

  - `requirements.md` (S1-1..S1-7, OQ-1..OQ-7, NC-1..NC-5)
  - `scenarios.md` (S1-1-SC1..S1-6-SC3)
  - `src/cpp_mcp/graphdb/exporter.py:94-326` (current classifier and
    MEMBER_OF block)
  - `src/cpp_mcp/graphdb/neo4j_driver.py:73-97` (single-label MERGE)
  - `src/cpp_mcp/graphdb/indradb_driver.py:140-167` (single-type Vertex)
  - `src/cpp_mcp/graphdb/schema_introspector.py:121-128, 332-373`
    (live grouping by single label / vertex type)
  - `src/cpp_mcp/graphdb/schema_version.py` (`SCHEMA_VERSION = "v1"`)
  - ADR-7 (schema baseline), ADR-17 (insert counting), ADR-24
    (live schema discovery + version stamp)
  - Wiki: `pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New node types"
  - CHARTER.md invariant I2 (no `Status: proposed` at developer dispatch)

## Charter path typo (filed for record)

CHARTER.md and the architect dispatch reference
`src/cpp_mcp/graphdb_export/`. The actual path is
`src/cpp_mcp/graphdb/`. This ADR and design.md use the real path.
