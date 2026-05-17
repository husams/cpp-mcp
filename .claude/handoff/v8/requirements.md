# Requirements — cpp-mcp v7 Stage S2

Stage: S2 of 6 (S1 shipped at commit 774cd66; schema_version="v2"; 1020 unit / 0 fail / 6 skip)
Target: additive enrichment of v2 schema; no pyproject version bump; no S3+ work.
Commit message on close: `v7-S2: add Type/Parameter nodes; RETURNS/HAS_PARAM/OF_TYPE/POINTS_TO/REFERS_TO edges; function signature props`

---

## Story S2-A — Type node

As a graph consumer, I want a first-class `Type` node in the graph, so that I can query return types, parameter types, and variable types without re-parsing source.

Acceptance criteria:
- Given a C++ source file is ingested, when a canonical type (e.g., `const std::string &`, `int *`, `void`) is encountered, then a `Type` node is created with properties: `spelling` (canonical string), `is_const` (bool, top-level only), `is_volatile` (bool), `is_pointer` (bool), `is_reference` (bool), `is_lvalue_reference` (bool), `is_rvalue_reference` (bool), `kind` (libclang type kind string).
- Given two separate declarations share the same canonical type spelling, when both are ingested, then exactly one `Type` node exists for that spelling (dedup by spelling).
- Given a `Type` node is created, when its USR is inspected, then it follows the format `type:<sha1(canonical_spelling)>`.
- Given a source file with pointer and reference types is ingested, when `is_lvalue_reference` and `is_rvalue_reference` are both checked on any single Type node, then they are mutually exclusive (never both true).

Priority: P0 — foundational; S2-B through S2-E all depend on Type nodes existing.

Dependencies: S1 shipped (Field/GlobalVariable split complete).

Open questions:
- Architect must ratify the USR strategy `type:<sha1(canonical_spelling)>` for builtins (no real USR exists) in ADR-26.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-A; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New node types"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-B — Type-shape edges (POINTS_TO / REFERS_TO)

As a graph consumer, I want `POINTS_TO` and `REFERS_TO` edges between Type nodes, so that I can traverse pointer and reference chains in a graph query.

Acceptance criteria:
- Given a pointer `Type` node (e.g., `int *`), when the graph is queried, then it has exactly one outgoing `POINTS_TO` edge to the pointee `Type` node (e.g., `int`).
- Given a reference `Type` node (e.g., `const std::string &`), when the graph is queried, then it has exactly one outgoing `REFERS_TO` edge to the referent `Type` node (e.g., `const std::string`).
- Given a non-pointer, non-reference `Type` node, when the graph is queried, then it has no `POINTS_TO` or `REFERS_TO` outgoing edges.
- Given any pointer/reference chain, when the exporter runs, then each `POINTS_TO`/`REFERS_TO` edge chases exactly one level of indirection per export run (depth is bounded at 1; multi-level pointers produce one edge per level, not unbounded recursion).

Priority: P0 — required for meaningful type queries.

Dependencies: S2-A (Type node).

Open questions:
- Architect must confirm depth-bound of 1 in ADR-26; if multi-level pointer chains (e.g., `int **`) should produce a chain of 2 edges, that needs to be stated explicitly.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-B; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New / refined edge types"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-C — Parameter node + HAS_PARAM edge

As a graph consumer, I want `Parameter` nodes connected to `Function` nodes via `HAS_PARAM` edges, so that I can query the ordered parameter list of any function or method.

Acceptance criteria:
- Given a function with N parameters is ingested, when the graph is queried, then N `Parameter` nodes exist, each with properties: `index` (int, 0-based), `name` (string; empty string for unnamed parameters), `default_value` (string spelling; empty string if absent).
- Given a function with parameters is ingested, when `HAS_PARAM` edges are queried, then one `HAS_PARAM` edge exists from the `Function` node to each `Parameter` node, with edge property `index` equal to the parameter's `index` property.
- Given a method (member function), constructor, or destructor is ingested, when `HAS_PARAM` edges are queried, then they also emit `HAS_PARAM` edges to their `Parameter` nodes.
- Given a function with parameters ordered by `index`, when parameters are retrieved via `HAS_PARAM` edges sorted by `index`, then they appear in source-declaration order.
- Given a function with no parameters is ingested, when `HAS_PARAM` edges are queried, then zero edges and zero `Parameter` nodes for that function exist.

Priority: P0 — required for function signature queries (reference question #3).

Dependencies: S2-A (Type node, needed for S2-D which pairs with this story).

Open questions: none.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-C; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New / refined edge types"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-D — OF_TYPE edge

As a graph consumer, I want `OF_TYPE` edges from `Parameter`, `Variable`, `Field`, and `GlobalVariable` nodes to `Type` nodes, so that I can query the declared type of any symbol.

Acceptance criteria:
- Given a `Parameter` node is created (via S2-C), when the graph is queried, then it has exactly one outgoing `OF_TYPE` edge to its `Type` node.
- Given a `Variable` node (non-static local variable) is ingested, when the graph is queried, then it has exactly one outgoing `OF_TYPE` edge to its `Type` node.
- Given a `Field` node (S1 split) is ingested, when the graph is queried, then it has exactly one outgoing `OF_TYPE` edge to its `Type` node.
- Given a `GlobalVariable` node (S1 split) is ingested, when the graph is queried, then it has exactly one outgoing `OF_TYPE` edge to its `Type` node.
- Given any of the above nodes is ingested, when `OF_TYPE` edges are queried, then each node has exactly one outgoing `OF_TYPE` edge (no duplicates, no zero-count).

Priority: P0 — enables type-based filtering across all symbol kinds.

Dependencies: S2-A (Type node); S1 (Field/GlobalVariable nodes already exist); S2-C (Parameter nodes).

Open questions: none.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-D; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New / refined edge types"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-E — RETURNS edge

As a graph consumer, I want a `RETURNS` edge from each `Function` node to a `Type` node, so that I can answer "what is the return type of function X?" in a single graph query.

Acceptance criteria:
- Given a free function is ingested, when the graph is queried, then it has exactly one outgoing `RETURNS` edge to its return `Type` node.
- Given a method (non-constructor, non-destructor) is ingested, when the graph is queried, then it has exactly one outgoing `RETURNS` edge to its return `Type` node.
- Given a function returning `void` is ingested, when the graph is queried, then it has a `RETURNS` edge to a `Type` node with `spelling = "void"`.
- Given a constructor or destructor is ingested, when the graph is queried, then it has a `RETURNS` edge following the rule ratified in ADR-26 (exactly one consistent rule; no constructor/destructor may be missing its `RETURNS` edge).

Priority: P0 — directly answers reference question #4.

Dependencies: S2-A (Type node).

Open questions:
- Architect must decide in ADR-26 whether constructors `RETURNS` the constructed class `Type`, `void`, or are excluded. Destructors are similarly ambiguous. This story requires the rule to be documented before implementation begins.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-E; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New / refined edge types"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-F — Function signature properties

As a graph consumer, I want additional properties on `Function` nodes describing calling conventions and qualifiers, so that I can filter functions by `constexpr`, `noexcept`, `deleted`, `defaulted`, cv-qualifiers, and ref-qualifiers without inspecting source.

Acceptance criteria:
- Given any `Function` node is ingested, when its properties are queried, then it includes: `signature` (canonical string), `is_constexpr` (bool), `is_noexcept` (bool), `is_deleted` (bool), `is_defaulted` (bool), `cv_qualifiers` (one of: `""`, `"const"`, `"volatile"`, `"const volatile"`), `ref_qualifier` (one of: `""`, `"&"`, `"&&"`).
- Given a free function (no member qualifiers), when `cv_qualifiers` and `ref_qualifier` are queried, then both are `""`.
- Given a `const` method, when `cv_qualifiers` is queried, then it is `"const"`.
- Given a `deleted` function, when `is_deleted` is queried, then it is `true`.
- Given a `defaulted` function, when `is_defaulted` is queried, then it is `true`.
- Given a `constexpr` function, when `is_constexpr` is queried, then it is `true`.
- Given a `noexcept` function, when `is_noexcept` is queried, then it is `true`.

DEFERRED — do NOT implement in S2:
- `is_template` on `Function` — deferred to S3 (Templates).
- `is_virtual` on `Function` — deferred to S4 (Virtual dispatch).
- `is_override` on `Function` — deferred to S4 (Virtual dispatch).

Priority: P0 — answers reference question #3 (signature).

Dependencies: none beyond existing Function node.

Open questions:
- Architect must confirm canonical `signature` string source (libclang spelling vs manually composed from `HAS_PARAM`+`RETURNS`) in ADR-26.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-F; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New properties on existing nodes"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-G — Class properties (S2-scoped subset)

As a graph consumer, I want `is_final`, `is_abstract`, and `record_kind` properties on `Class` nodes, so that I can distinguish structs from classes, identify abstract base classes, and find sealed types without re-parsing source.

Acceptance criteria:
- Given any `Class` node is ingested, when its properties are queried, then it includes: `is_final` (bool), `is_abstract` (bool), `record_kind` (one of: `"class"`, `"struct"`, `"union"`).
- Given a class declared `final`, when `is_final` is queried, then it is `true`.
- Given a class with at least one pure virtual method, when `is_abstract` is queried, then it is `true`.
- Given a `struct` declaration, when `record_kind` is queried, then it is `"struct"`.
- Given a `union` declaration, when `record_kind` is queried, then it is `"union"`.
- Given a `class` declaration, when `record_kind` is queried, then it is `"class"`.

DEFERRED — do NOT implement in S2:
- `is_template` on `Class` — deferred to S3 (Templates).

Priority: P0 — required for completeness of Class representation in v2.

Dependencies: none beyond existing Class node.

Open questions: none.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-G; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"New properties on existing nodes"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Story S2-H — describe_graph_schema update + backward compatibility

As a tool user, I want `describe_graph_schema` to surface all S2 additions, so that consumers can discover the enriched schema without reading source code.

Acceptance criteria:
- Given S2 is fully implemented, when `describe_graph_schema` is called, then the response lists node types `Type` and `Parameter` alongside existing node types.
- Given S2 is fully implemented, when `describe_graph_schema` is called, then the response lists edge types `RETURNS`, `HAS_PARAM`, `OF_TYPE`, `POINTS_TO`, `REFERS_TO` alongside existing edge types.
- Given S2 is fully implemented, when `describe_graph_schema` is called, then `schema_version` is `"v2"` (unchanged from S1; S2 does not bump the version).
- Given a v1 graph (schema_version="v1") is loaded after S2 ships, when any read operation runs, then it succeeds without error (backward compat already proven by S1; must not regress).
- Given a v2-from-S1 graph (has no Type/Parameter nodes) is loaded after S2 ships, when any read operation runs, then it succeeds without error (read path tolerates missing Type/Parameter nodes and missing S2 edges).
- Given S2 ships, when the full existing unit test suite (1020 tests) is run, then all tests that passed before S2 still pass (no regression).

Priority: P0 — I1 invariant requires schema surface and non-regression before any next-stage dispatch.

Dependencies: S2-A through S2-G.

Open questions: none.

References: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md` §S2-H and §Backward compat; `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` §"Acceptance criteria"; cognee tags: `task:cpp-mcp-v7-s2`, `role:product-manager`.

---

## Deferred items (named explicitly; must NOT be implemented in S2)

| Item | Stage | Rationale |
|---|---|---|
| `is_template` on `Function` | S3 | Depends on Template node + TEMPLATE_PARAM/TEMPLATE_ARG edges |
| `is_virtual` on `Function` | S4 | Depends on OVERRIDES / virtual dispatch modeling |
| `is_override` on `Function` | S4 | Depends on OVERRIDES edge |
| `is_template` on `Class` | S3 | Same as Function; template graph machinery not in scope |
| `INSTANTIATES`/`SPECIALIZES`/`TEMPLATE_PARAM`/`TEMPLATE_ARG`/`CONSTRAINED_BY`/`Concept` | S3 | Full template stage |
| `OVERRIDES`/`FRIEND_OF`/`INHERITS.is_virtual` | S4 | Virtual dispatch stage |
| `Enum`/`Enumerator`/`ENUMERATOR_OF`/`UNDERLYING_TYPE`/`USES_*`/`ALIAS_OF` | S5 | Enum/namespace/alias stage |
| IndraDB ordered-traversal verb | S6 | Executor extension stage |
| `pyproject.toml` version bump (0.4.0 → 0.5.0) | S6 (final) | Held until all 6 stages land |

---

## ADR required before architect dispatch

- ADR-26: Type node identity strategy (USR format, dedup algorithm, builtin handling), constructor/destructor `RETURNS` rule, `POINTS_TO`/`REFERS_TO` depth bound, canonical `signature` string source, deferred props list. Must reach "Accepted" status before developer dispatch (CHARTER invariant I2).

---

## Open questions summary (3 items — details in stories above)

1. Constructor/destructor `RETURNS` rule — architect to decide and document in ADR-26 (S2-E).
2. Type USR strategy for builtins — architect to ratify `type:<sha1(spelling)>` or propose alternative in ADR-26 (S2-A).
3. Canonical `signature` string source — libclang spelling vs composed from `HAS_PARAM`+`RETURNS`; architect to confirm in ADR-26 (S2-F).
