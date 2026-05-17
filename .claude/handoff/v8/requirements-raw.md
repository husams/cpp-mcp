# cpp-mcp v7 — Stage S2 (raw requirements)

Source PRD: `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` (S2 row in Rollout).
Prior stage: S1 (handoff v7), commit 774cd66, shipped Field/GlobalVariable + MEMBER_OF.access + schema_version=v2.

## S2 scope (additive, non-breaking; schema_version stays "v2")

### S2-A — Type node + canonical type spelling

- New node type `Type` with properties:
  - `spelling` (canonical type string, e.g., `const std::vector<int> &`)
  - `is_const` (bool — top-level const)
  - `is_volatile` (bool)
  - `is_pointer` (bool)
  - `is_reference` (bool)
  - `is_lvalue_reference` / `is_rvalue_reference` (bool, mutually exclusive)
  - `kind` (libclang type kind string for debugging)
- Dedupe `Type` nodes by canonical spelling at exporter (avoid explosion).
- `Type` USR strategy: synthetic stable ID — `type:<sha1(canonical_spelling)>` (no real USR for builtin types).

### S2-B — Type-shape edges

- `POINTS_TO` edge: pointer `Type` → pointee `Type`.
- `REFERS_TO` edge: reference `Type` → referent `Type`.
- Both edges chase one level deep per export; recursion bounded.

### S2-C — Parameter node + HAS_PARAM edge

- New node type `Parameter` with properties:
  - `index` (int, 0-based)
  - `name` (string; empty for unnamed)
  - `default_value` (string spelling, empty if absent)
- New edge `HAS_PARAM` from `Function` → `Parameter`, with edge property `index` (mirrors node property for ordered traversal). Methods (member functions, ctors, dtors) also emit `HAS_PARAM`.

### S2-D — OF_TYPE edge

- New edge `OF_TYPE` from `Parameter` → `Type`.
- Also extend to existing `Variable`, `Field`, `GlobalVariable` nodes — each gets one outgoing `OF_TYPE` → `Type`.

### S2-E — RETURNS edge

- New edge `RETURNS` from `Function` → `Type`.
- Applies to free functions, methods, ctors (treat as RETURNS void or RETURNS class?), dtors (void). Pick a consistent rule and document in ADR.

### S2-F — Function signature properties

- On `Function` nodes, add:
  - `signature` (canonical, e.g., `void foo(int, const std::string &) const noexcept`)
  - `is_constexpr` (bool)
  - `is_noexcept` (bool)
  - `is_deleted` (bool)
  - `is_defaulted` (bool)
  - `cv_qualifiers` (string: `""`, `"const"`, `"volatile"`, `"const volatile"`)
  - `ref_qualifier` (string: `""`, `"&"`, `"&&"`)
- DEFERRED to later stages (do NOT implement in S2): `is_template` (S3), `is_virtual` / `is_override` (S4).
  Document this in ADR.

### S2-G — Class properties (S2-scoped subset)

- On `Class` nodes, add:
  - `is_final` (bool)
  - `is_abstract` (bool — has at least one pure virtual)
  - `record_kind` (string: `class` | `struct` | `union`)
- DEFERRED to later stages: `is_template` (S3).

### S2-H — describe_graph_schema update

- Surface all new node types (`Type`, `Parameter`), new edges (`RETURNS`, `HAS_PARAM`, `OF_TYPE`, `POINTS_TO`, `REFERS_TO`), new properties (Function and Class).
- `schema_version` stays `"v2"`.

### S2-I — Tests

- Unit tests:
  - ≥1 per new node type (`Type`, `Parameter`).
  - ≥1 per new edge (`RETURNS`, `HAS_PARAM`, `OF_TYPE`, `POINTS_TO`, `REFERS_TO`).
  - ≥1 per new Function property (signature, is_constexpr, is_noexcept, is_deleted, is_defaulted, cv_qualifiers, ref_qualifier).
  - ≥1 per new Class property (is_final, is_abstract, record_kind).
  - Type dedup test (multiple uses of same type → one Type node).
  - Round-trip parity.
- Live integration tests:
  - At least one query exercising "return type of function X" (RETURNS edge).
  - At least one query exercising "parameters of function X ordered by index" (HAS_PARAM with order).
  - At least one query exercising "find pointer types pointing to class Y" (POINTS_TO).

### S2-J — ADR

- ADR-26: Type node identity strategy (USR generation, dedup, builtin handling, pointer/reference chain bounds), constructor/destructor RETURNS rule, deferred props list (is_template/is_virtual/is_override).

## Out of scope (defer to later stages)

- S3: Templates (`INSTANTIATES`/`SPECIALIZES`/`TEMPLATE_PARAM`/`TEMPLATE_ARG`/`CONSTRAINED_BY`/`Concept`).
- S4: Virtual dispatch (`OVERRIDES`, `FRIEND_OF`, `INHERITS.virtual/access`).
- S5: Enums (`Enum`/`Enumerator`/`ENUMERATOR_OF`/`UNDERLYING_TYPE`), namespaces (`USES_*`), `ALIAS_OF`.
- S6: IndraDB ordered-traversal verb; full describe rewrite; ADR roll-up.
- `pyproject.toml` version bump (still 0.4.0 until end of S6).

## Completion rule

- Commit on `main` with message: `v7-S2: add Type/Parameter nodes; RETURNS/HAS_PARAM/OF_TYPE/POINTS_TO/REFERS_TO edges; function signature props`.
- Full unit test suite green (currently 1020 unit / 0 fail / 6 skip).
- DO NOT bump `pyproject.toml`.
- DO NOT proceed to S3.

## Backward compat

- v1 graphs continue to load (already proven).
- v2-from-S1 graphs (no Type/Parameter) load without error; read path tolerates missing nodes/edges.
- Public MCP tool signatures (`ingest_code`, `query_graphdb`, `describe_graph_schema`) unchanged.
