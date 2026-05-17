# Requirements — cpp-mcp v7 Stage S1

run_id: cpp-mcp-v7-s1
schema target: 0.4.0 (no pyproject.toml bump in S1; 0.5.0 reserved for end of S6)
stage: S1 of 6
upstream PRD: ~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md
charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md

---

## Story S1-1: Variable node split — Field and GlobalVariable

As a graph consumer, I want class data members emitted as `Field` nodes and all other variables emitted as `GlobalVariable` nodes, so that I can write schema-typed queries that distinguish struct/class members from namespace- or file-scope variables without post-filtering.

Acceptance criteria:
  - Given a C++ source file with a class or struct containing a non-static data member, when the exporter runs, then the graph contains a node of type `Field` (not `Variable`) for that member.
  - Given a C++ source file with a namespace-scope variable, a file-scope static, or an extern declaration, when the exporter runs, then the graph contains a node of type `GlobalVariable` (not `Variable`) for that symbol.
  - Given a C++ source file with a static class data member, when the exporter runs, then the node is classified as `GlobalVariable` (static members are not instance fields), not `Field`.
  - Given a graph exported with schema_version 1 (all nodes typed `Variable`), when `query_graphdb` or `describe_graph_schema` runs against that legacy graph, then no error is raised and results are returned (missing v2 fields tolerated on read).
  - Given a live IndraDB integration test fixture, when the fixture includes both a class data member and a namespace-scope variable, then the exported graph contains at least one `Field` node and at least one `GlobalVariable` node distinguishable by type.

Priority: P0 — core S1 deliverable; all downstream stories in this stage depend on this split.

Dependencies:
  - ADR-25 (variable split transition path: deprecate `Variable` vs. keep as parent label) — architect must resolve before developer dispatch.

Open questions:
  - OQ-1: Should `Variable` label be entirely removed from the graph (transition path a), or retained as an additional label alongside `Field`/`GlobalVariable` (transition path b)? The cleaner choice may differ between Neo4j (multi-label native) and IndraDB (single vertex type). Do not resolve here — decision lives in ADR-25.
  - OQ-2: How should `Field` vs `GlobalVariable` classification apply to anonymous structs/unions used as members? Treat their fields as `Field`, or as a separate pass?

References:
  - requirements-raw.md §1
  - wiki: pages/planning/cpp-mcp-v7-full-ast-schema.md §"New node types"
  - CHARTER.md invariants I1
  - ADR slot: adr-25.md (next free per CHARTER)

---

## Story S1-2: MEMBER_OF edge access property

As a graph consumer, I want the `MEMBER_OF` edge to carry an `access` property (`public` | `protected` | `private`), so that I can filter class members by visibility without re-parsing source or fetching supplementary data.

Acceptance criteria:
  - Given a class with members declared under `public:`, `protected:`, and `private:` sections, when the exporter runs, then each `MEMBER_OF` edge from those members carries `access` matching the declared section.
  - Given a struct (not class) with no explicit access specifier on a member, when the exporter runs, then the `MEMBER_OF` edge for that member carries `access: public` (C++ default for struct).
  - Given a class (not struct) with no explicit access specifier on a member, when the exporter runs, then the `MEMBER_OF` edge for that member carries `access: private` (C++ default for class).
  - Given a live IndraDB integration test, when queried for "find private fields of class X", then the query using `access: private` returns only private members and excludes public/protected members.
  - Given a graph exported with schema_version 1 (no `access` property on `MEMBER_OF`), when `query_graphdb` runs against that legacy graph, then no error is raised (read path tolerates absent property).

Priority: P0 — required for coverage matrix question #2 (`+access filter`); dependent on S1-1 (MEMBER_OF edges only exist after Field nodes are emitted correctly).

Dependencies:
  - S1-1 (Field nodes must exist before this property is meaningful)

Open questions:
  - OQ-3: What is the correct default for `access` on a `union` member? C++ spec says union members are public by default, but libclang may not surface this uniformly. Need to verify libclang behavior and document in implementation notes.
  - OQ-4: `MEMBER_OF` currently connects any member (method, nested type, field) to its containing class. Should `access` be emitted on ALL `MEMBER_OF` edges or only those to `Field` nodes? Raw requirements imply all member types; confirm with architect.

References:
  - requirements-raw.md §2
  - wiki: pages/planning/cpp-mcp-v7-full-ast-schema.md §"New / refined edge types" (`MEMBER_OF`) and §"New properties on existing nodes"

---

## Story S1-3: New properties on Field and GlobalVariable nodes

As a graph consumer, I want `Field` and `GlobalVariable` nodes to carry `is_static`, `is_const`, `is_constexpr`, and `storage_class` properties, so that I can filter variables by storage and qualification without re-parsing.

Acceptance criteria:
  - Given a variable declared `const`, when exported, then the corresponding node has `is_const: true`.
  - Given a variable declared `constexpr`, when exported, then the node has `is_constexpr: true` (and `is_const: true` because constexpr implies const in C++).
  - Given a variable declared `static` at namespace scope, when exported, then the node has `is_static: true` and `storage_class: static`.
  - Given a variable declared `extern`, when exported, then the node has `storage_class: extern`.
  - Given a variable declared `thread_local`, when exported, then the node has `storage_class: thread_local`.
  - Given a non-static class data member (`Field` node), when exported, then `is_static: false`; the value of `storage_class` for this case is defined by ADR-25 or implementation notes (open question OQ-5 below).
  - Given a plain local variable with no storage-class specifier, when exported, then `storage_class: none` (or as resolved in OQ-5).
  - Given a graph exported with schema_version 1 (no such properties), when `query_graphdb` runs, then no error is raised.
  - Given unit tests, there is at least one test per new property (`is_static`, `is_const`, `is_constexpr`, `storage_class`) covering both true and false/explicit values.

Priority: P0 — required for full S1 schema; companion to S1-1 and S1-2.

Dependencies:
  - S1-1 (nodes must be typed before properties can be validated per-type)

Open questions:
  - OQ-5: What is the correct `storage_class` value for a non-static class data member (`Field`)? Instance fields have no storage-class keyword in C++. Options: emit `none`, omit the property entirely, or emit `auto`. Implementation must choose one and document; architect or developer to resolve and note in implementation-notes.md.
  - OQ-6: Should `is_static: true` on a `Field` node ever be valid (static data members are classified as `GlobalVariable` per S1-1), or should the exporter enforce the invariant and raise/warn if a static member ends up typed `Field`? Architect to decide and reflect in design.

References:
  - requirements-raw.md §3
  - wiki: pages/planning/cpp-mcp-v7-full-ast-schema.md §"New properties on existing nodes" (`Variable`/`Field`)

---

## Story S1-4: schema_version bump and describe_graph_schema update

As a tool operator, I want `describe_graph_schema` to return `schema_version: 2` and reflect all S1 changes (new node types, updated edge property, new node properties), so that clients can detect the schema version and adapt queries accordingly.

Acceptance criteria:
  - Given a graph exported after S1 changes, when `describe_graph_schema` is called, then the response includes `schema_version: 2`.
  - Given a graph exported after S1 changes, when `describe_graph_schema` is called, then the response lists `Field` and `GlobalVariable` as node types (and either excludes `Variable` or documents its retention per ADR-25).
  - Given a graph exported after S1 changes, when `describe_graph_schema` is called, then the response documents `access` as a property of the `MEMBER_OF` edge.
  - Given a graph exported after S1 changes, when `describe_graph_schema` is called, then the response documents `is_static`, `is_const`, `is_constexpr`, and `storage_class` as properties of `Field` and `GlobalVariable` nodes.
  - Given a graph exported with schema_version 1, when `describe_graph_schema` is called, then no error is raised (backward-compatible read).
  - Given the 7 existing MCP tool signatures (`ingest_code`, `query_graphdb`, `describe_graph_schema`, and others), when S1 is deployed, then none of their public input or output shapes change (only the schema of the emitted graph changes).

Priority: P0 — required so downstream tools and integration tests can verify S1 is active.

Dependencies:
  - S1-1, S1-2, S1-3 (schema description can only be complete once node types and properties are defined)

Open questions:
  - OQ-7: If ADR-25 retains `Variable` as a label, should `describe_graph_schema` list it alongside `Field`/`GlobalVariable`, or only list the leaf types? Defer to architect.

References:
  - requirements-raw.md §4
  - wiki: pages/planning/cpp-mcp-v7-full-ast-schema.md §"Acceptance criteria" AC-1 and AC-5

---

## Story S1-5: Unit test coverage for S1 changes

As a developer, I want every new node type, edge property, and node property introduced in S1 to have dedicated unit tests, so that regressions are caught before integration.

Acceptance criteria:
  - Given the full unit test suite, when it runs after S1, then all 880 pre-existing tests continue to pass (zero regressions).
  - Given S1 changes, when the unit test suite runs, then there is at least one test asserting a `Field` node is emitted for a non-static class data member.
  - Given S1 changes, when the unit test suite runs, then there is at least one test asserting a `GlobalVariable` node is emitted for a namespace-scope variable.
  - Given S1 changes, when the unit test suite runs, then there are tests covering `MEMBER_OF.access` for all three values: `public`, `protected`, `private`.
  - Given S1 changes, when the unit test suite runs, then there is at least one test per new property: `is_static`, `is_const`, `is_constexpr`, `storage_class` (covering at minimum one true and one false/alternate value each).
  - Given S1 changes, when an exporter round-trip test runs (export → re-import → compare graph), then the resulting graph is equivalent to the pre-export graph.

Priority: P0 — tests are the exit gate; no developer dispatch without this story complete.

Dependencies:
  - S1-1, S1-2, S1-3, S1-4

Open questions: none

References:
  - requirements-raw.md §5
  - CHARTER.md §"Cross-stage invariants" I3

---

## Story S1-6: Live integration test extension

As a developer, I want the existing live IndraDB integration test layer extended with at least one `Field`-vs-`GlobalVariable` case and one `access` filter case, so that S1 behavior is verified end-to-end against a live graph backend.

Acceptance criteria:
  - Given the live IndraDB test harness, when S1 tests run, then at least one test fixture contains both a class data member and a namespace-scope variable, and the test asserts both `Field` and `GlobalVariable` node types are present in the exported graph.
  - Given the live IndraDB test harness, when the access filter test runs, then a query using `access: private` against a class with mixed-visibility members returns only private members.
  - Given the live integration tests, when they run after S1, then all pre-existing integration tests (18 passing in v4) continue to pass.

Priority: P0 — required per completion rule in requirements-raw.md and parity with v6 live-test precedent.

Dependencies:
  - S1-1, S1-2, S1-3, S1-5

Open questions: none

References:
  - requirements-raw.md §6
  - project_v4_live_verification.md (existing live test baseline)

---

## Story S1-7: ADR-25 — Variable split transition path

As the team, I want a documented Architecture Decision Record (ADR-25) for the `Variable` → `Field`/`GlobalVariable` split transition path, so that the chosen approach is traceable and the rationale is preserved for future stages.

Acceptance criteria:
  - Given the handoff directory, when architect dispatch completes, then `adr-25.md` exists at `/Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md`.
  - Given ADR-25, when reviewed, then it documents at minimum: (a) deprecate `Variable` / stop emitting vs. (b) keep `Variable` as parent label with additional labels, including trade-offs for both Neo4j and IndraDB backends.
  - Given ADR-25, when the developer reads it, then the Status field is NOT `proposed` (it must be `accepted` or `rejected` before developer dispatch — per CHARTER.md invariant I2).

Priority: P0 — CHARTER invariant I2 blocks developer dispatch until ADR is resolved.

Dependencies:
  - Architect stage (this story is owned by architect, not developer)

Open questions:
  - OQ-1 (repeated): see S1-1 open questions — this ADR resolves them.

References:
  - CHARTER.md §"Cross-stage invariants" I2, §"Failure taxonomy" ADR_UNRESOLVED
  - requirements-raw.md §7

---

## Deferred to later stages (explicitly out of scope for S1)

The following items appear in the broader v7 PRD but are NOT part of S1. They must not be implemented in this stage.

- **S2**: `Type` node; `RETURNS`, `OF_TYPE`, `HAS_PARAM` edges; function `signature` property and related function/class properties.
- **S3**: Template support — `INSTANTIATES`, `SPECIALIZES`, `TEMPLATE_PARAM`, `TEMPLATE_ARG`, `CONSTRAINED_BY` edges; `Concept` node.
- **S4**: Virtual dispatch — `OVERRIDES`, `FRIEND_OF` edges; `is_virtual`/`access` properties on `INHERITS`.
- **S5**: Enums (`Enum`, `Enumerator` nodes; `ENUMERATOR_OF`, `UNDERLYING_TYPE` edges); namespace directives (`USES_NAMESPACE`, `USES_DECLARATION`); `ALIAS_OF` edge.
- **S6**: IndraDB ordered-traversal verb; `describe_graph_schema` v2 full rewrite; ADR roll-up across all stages.
- **Version bump**: `pyproject.toml` version remains `0.4.0` after S1. `0.5.0` is reserved for end of S6.

---

## Non-functional constraints

- NC-1: All 7 existing MCP tool public input/output shapes are unchanged after S1.
- NC-2: v1 graphs (schema_version 1) must remain loadable and queryable; read path must tolerate missing v2 fields without error.
- NC-3: `pyproject.toml` version must NOT be bumped in S1 (stays at 0.4.0).
- NC-4: Commit message must be exactly: `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`
- NC-5: No S2–S6 code may land in this commit.
