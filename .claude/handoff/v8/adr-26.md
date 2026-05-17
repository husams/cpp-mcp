# ADR-26: Type / Parameter node introduction and signature property surface (v7 S2)

Status: accepted
Date: 2026-05-17
Stage: cpp-mcp v7 — S2
Supersedes: none (extends ADR-7 schema, ADR-24 schema-version stamping, ADR-25 Variable split)

---

## Context

Stage S2 of v7 introduces the first **derived-type node** (`Type`) and the
first **positional child node** (`Parameter`) into the graph, plus the edges
that wire return types, parameter types, and pointer/reference indirection.
It also fills out qualifier properties on `Function` and `Class`.

Requirements / scenarios (`/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements.md`,
`scenarios.md`) carry three explicit `needs-clarification` items and several
gaps the architect must resolve before developer dispatch (CHARTER I2):

  - OQ-1 (S2-E EC-5/6): constructor / destructor `RETURNS` rule.
  - OQ-2 (S2-A): `Type` USR scheme (no real libclang USR for builtins).
  - OQ-3 (S2-B EC-2): `POINTS_TO` chain depth for multi-pointer types.
  - OQ-4 (S2-F SC-F-01-sig): canonical `signature` string source.
  - OQ-5 (PRD-derived): `Type` spelling source — desugared (canonical) vs
    source-form.  Not in requirements.md but is the single largest source
    of QA defect risk; surfaced and resolved here.
  - OQ-6 (S2-G SC-G-05): `record_kind="union"` requires `UNION_DECL` in the
    kind map (currently missing — see exporter.py:96-113).
  - OQ-7 (transition): existing S1 tests that assert PARM_DECL → Variable
    will fail when PARM_DECL → Parameter.  Test churn must be documented as
    expected, not regression.

Evidence from the post-S1 code (commit 774cd66 / handoff v8):

  - `src/cpp_mcp/graphdb/exporter.py:96-113` — `_KIND_TO_NODE_TYPE` is the
    single classifier table; PARM_DECL still maps to `NODE_VARIABLE` (ADR-25
    D2 transitional rule).  `UNION_DECL` is **not** in the table.
  - `src/cpp_mcp/graphdb/exporter.py:135-189` — `_is_static_member`,
    `_classify_field`, `_classify_node` are the canonical pattern for
    runtime classifier branches; new Type / Parameter creation must follow
    the same pattern (helper function, single call site in `_walk_cursor`).
  - `src/cpp_mcp/graphdb/exporter.py:241-344` — `_var_qualifiers`,
    `_is_storage_static`, `_storage_class_value` show the canonical pattern
    for cursor-feature probing with `getattr`/`callable` fallback and
    token-scan fallback for libclang features missing on the pinned version
    (S1 used this for `is_constexpr` and `thread_local`).
  - `src/cpp_mcp/graphdb/exporter.py:388-665` — `_walk_cursor` recursive
    DFS; new Type / Parameter emission must happen inside the existing
    `node_type and usr` block (after node create, before edge creation),
    and Type nodes must be created via a helper that is also callable from
    `_get_or_create_type_for_function_return` and
    `_get_or_create_type_for_pointee`.
  - `src/cpp_mcp/graphdb/driver.py:17-46` — `NodeRecord` and `EdgeRecord`
    are single-label `TypedDict`s.  Confirms ADR-25 D1 constraint: still
    one label per node, one type per vertex.  Type / Parameter must be
    independent vertices, not multi-labeled annotations.
  - `src/cpp_mcp/graphdb/schema_introspector.py:121-128, 332-373` — live
    introspector groups by single label / vertex type.  New `Type` and
    `Parameter` labels surface automatically; backward compat for v1 and
    v2-from-S1 graphs holds by construction (SC-H-04, SC-H-05).
  - Libclang capability probe (executed during architect pass, see
    "Capability matrix" below): `is_noexcept` **not** available; use
    `exception_specification_kind` instead.  `is_constexpr` on cursors
    **not** available on pinned libclang — S1's token-scan fallback applies
    to functions as well as variables.  `is_const_method`,
    `is_deleted_method`, `is_default_method`, `is_pure_virtual_method`,
    `is_abstract_record`, `is_anonymous`, `get_arguments`, `result_type`,
    `displayname`, `Type.get_pointee`, `Type.get_ref_qualifier`,
    `CursorKind.CXX_FINAL_ATTR` all **present**.

Forces:

  - F1 (single-label backends): both drivers still emit one label per
    node.  Type / Parameter MUST be separate vertices with their own USRs
    (Alt-A rejected for same reason as ADR-25 D1).
  - F2 (scenario fidelity): SC-A-01 asserts `spelling == "const std::string &"`
    — the **source-form** spelling.  `type.get_canonical().spelling` returns
    desugared `const std::basic_string<char, std::char_traits<char>, ...> &`
    and will fail SC-A-01 immediately.
  - F3 (idempotency): the exporter is per-file and re-runs must converge
    on the same graph.  Type USRs must be deterministic and stable across
    runs and across files.  Spelling-hash satisfies this; cursor-USRs do
    not exist for builtins.
  - F4 (forward compat for S3/S5): `Type` will gain template-instantiation
    spellings (`std::vector<int>`) in S3 and underlying-type targets in
    S5.  The USR scheme picked here must not require revision.
  - F5 (test churn budget): S1 ships with 1020 unit tests passing.
    SC-H-06 demands no regression.  Migrating PARM_DECL from `Variable` to
    `Parameter` will fail any test that asserts on the transitional emission.
    Grep located ~6 tests asserting PARM_DECL → Variable directly; these
    are required updates, not regressions, and ADR-26 must call them out
    explicitly so QA does not flag them as defects.

---

## Decisions

### D1 — Type USR scheme: `type:<sha1(spelling)>` (resolves OQ-2)

A `Type` node's USR is `f"type:{hashlib.sha1(spelling.encode('utf-8')).hexdigest()}"`,
where `spelling` is the source-form spelling defined in D2.

Rationale: builtin types (`int`, `void`) have no libclang USR; template
spellings (`std::vector<int>`) have a USR on the template decl but not on
the instantiation; pointer/reference variants have no USR at all.
Spelling-hash is deterministic, collision-resistant for distinct C++ type
spellings (sha1 over short type strings has zero observed collisions in
the wild), and stable across runs.  USR-as-content-hash also gives free
dedup at the upsert layer (drivers MERGE on USR).

`type:` prefix disambiguates from cursor USRs (which start with `c:`) and
from the file URN prefix `file://`.

### D2 — Type spelling: source-form (`cursor.type.spelling`), not desugared (resolves OQ-5)

`Type.spelling` is `cursor.type.spelling` (libclang's source-form
rendering: `const std::string &`, `int *`, `int **`, `void`).  Do **not**
call `type.get_canonical().spelling` (desugared form like
`const std::basic_string<char, std::char_traits<char>, ...> &`).

Rationale: every scenario (SC-A-01, SC-B-02, SC-D-04, SC-E-01, SC-E-03)
asserts source-form spellings.  Desugared spellings fail scenarios on
the first invocation.  "Canonical" in this ADR's vocabulary means
"normalized to the source-as-libclang-renders-it form, deduped by exact
string equality" — NOT ISO desugared.

Trade-off accepted: two source files that write the same type with
different aliases (`std::string` vs `std::basic_string<char>`) will
produce two `Type` nodes.  This is the correct behavior for "what does
the source say?" queries; an ISO-canonical second view can be added in a
later stage (e.g., a `CANONICAL_OF` edge) without breaking S2.

### D3 — Type dedup: in-memory per-export `usr → NodeRecord` map (extends seen_usrs)

The `_walk_cursor` already carries `seen_usrs: set[str]`.  Type creation
piggybacks on it: `_get_or_create_type(cursor.type, nodes, seen_usrs)`
computes USR via D1, checks membership, and appends to `nodes` only on
miss.  Two declarations sharing a spelling produce one Type node
(SC-A-03, SC-A-05) without backend round-trip — drivers' `MERGE`/upsert
provides cross-file dedup automatically.

### D4 — POINTS_TO / REFERS_TO recursion: depth-1 per edge, chain per export (resolves OQ-3)

For each Type created, the helper inspects `cursor.type.kind`:

  - `POINTER` → emit POINTS_TO edge to the Type for `type.get_pointee()`;
    recursively create that Type (which, if itself a pointer, emits its
    own POINTS_TO edge — natural chain via recursion).
  - `LVALUEREFERENCE` or `RVALUEREFERENCE` → emit REFERS_TO edge to the
    Type for `type.get_pointee()` (libclang reuses `get_pointee` for ref
    types), same recursion.
  - any other kind → no outgoing POINTS_TO / REFERS_TO.

Net result for `int **`: three Type nodes (`int **`, `int *`, `int`) with
two POINTS_TO edges chained `int ** → int * → int` — exactly SC-B-05.

"Depth bound 1" in requirements AC4 means **one level per edge**, not one
edge total.  The chain length equals the indirection depth.  This is also
the only interpretation consistent with SC-B-05's three-node assertion.

### D5 — Constructor / destructor RETURNS: both → `void` Type (resolves OQ-1)

Both constructors and destructors emit a `RETURNS` edge to the singleton
`Type` node with `spelling = "void"`.

Rationale:

  - `cursor.result_type.spelling` on a `CONSTRUCTOR` or `DESTRUCTOR`
    cursor returns `"void"` from libclang itself — no special-case lookup
    needed; the natural code path Just Works.
  - Asymmetric rule (ctor → class Type, dtor → void) requires special-case
    lookup of the enclosing class Type and conflates `RETURNS` ("what value
    does the callee return?") with `CONSTRUCTS` (the relationship a
    consumer actually wants for "what type does this constructor build?",
    which is already answerable via `MEMBER_OF` to the enclosing class).
  - "Constructor returns the class" is a model the consumer can layer on
    top: `MATCH (ctor:Function {is_ctor:true})-[:MEMBER_OF]->(cls:Class)
    RETURN cls AS constructed`.  This is more correct than baking the
    asymmetric rule into RETURNS.

Consequence: SC-E-04 expected `Type` spelling = `"void"`; SC-E-05 expected
`Type` spelling = `"void"`.  Both scenarios are now `confirmed` after this
ADR.  Implementer must substitute `"void"` for "rule documented in
ADR-26" in scenario `Then` clauses.

### D6 — Parameter USR: `<function-USR>#param:<index>` (resolves implicit OQ)

Parameter USRs are `f"{function_usr}#param:{index}"` (0-based index).

Rationale: libclang assigns USRs to PARM_DECL cursors, but they are
**not stable** across declaration vs definition of the same function
(PARM_DECL USRs include the parent function's USR plus a parameter
name, and unnamed parameters get synthetic names that differ between
forward decl and definition).  Synthetic positional USR is stable,
human-debuggable, and matches the index-based identity already in S2-C.AC1.

The `#` separator avoids collision with libclang's `c:` USR scheme
(which never contains `#`) and with the `type:<hex>` and `file://` USRs.

### D7 — Function signature source: `cursor.displayname` (resolves OQ-4)

`Function.signature = cursor.displayname` (libclang's canonical
name+params rendering, e.g., `"foo(int, const std::string &)"`).

Rationale: composing from `HAS_PARAM` + `RETURNS` reimplements what
libclang already canonicalizes and invites string-format bugs (where do
spaces go, how is `const` rendered, etc.).  `displayname` is also stable
across forward decl / definition for the same function (unlike
`cursor.spelling` which is just the unqualified name).

Trade-off: `displayname` does **not** include return type, cv-qualifiers,
ref-qualifier, or noexcept.  This is **deliberate** — those live as
discrete properties (`cv_qualifiers`, `ref_qualifier`, `is_noexcept`)
and on the `RETURNS` edge.  Consumers compose the full signature client-side
from the property bag if they need it.  Implementer must document this
in implementation-notes.md and the developer must verify SC-F-01-sig's
expected value matches `displayname` exactly for the test input.

### D8 — `UNION_DECL` added to `_KIND_TO_NODE_TYPE` (resolves OQ-6)

Add `"UNION_DECL": NODE_CLASS` to `_KIND_TO_NODE_TYPE`.  `record_kind` is
derived at node-create time from `cursor.kind.name`:

```
CLASS_DECL, CLASS_TEMPLATE → "class"
STRUCT_DECL                → "struct"
UNION_DECL                 → "union"
```

Without D8, SC-G-05 row 3 (`union MyUnion`) emits no Class node at all and
the scenario fails on "Class node for MyUnion exists".  S1 missed this
because S1 only worried about FIELD_DECL classification; union as a record
kind was deferred to S2 by the PRD.

### D9 — PARM_DECL → Parameter migration & test update list (resolves OQ-7)

PARM_DECL's classifier mapping changes from `NODE_VARIABLE` (ADR-25 D2
transitional) to a new `NODE_PARAMETER` constant in `graphdb/schema.py`.
The S1 transitional rule is now complete.

**Known test updates required** (not regression — SC-H-06 must be
interpreted as "1020 - test_updates passing" and a fresh count after
updates).  Confirmed via grep at architect time:

| File | Update |
|---|---|
| `tests/unit/graphdb/test_field_classification.py:327-384` | Section "PARM_DECL → Variable (ADR-25 D2 invariant)" — replace with "PARM_DECL → Parameter (ADR-26 D9)" |
| `tests/unit/graphdb/test_global_variable_classification.py:167` | Update USR-scoped Variable filter to Parameter |
| `tests/integration/test_describe_graph_schema_e2e.py:65, 84, 176-214` | `Variable` count assertion (currently `< 33` PARM-only) becomes `Parameter` count > 0; drop legacy `Variable` from `_V2_SPLIT_TYPES` for S2-exported graphs |
| `tests/unit/graphdb/test_describe_v1_compat.py:181-258` | KEEP unchanged — this test seeds literal `"Variable"` vertices to prove v1 read-compat (SC-H-04); the constant `NODE_VARIABLE` MUST remain exported for this test |
| `tests/unit/graphdb/test_indradb_query_subset.py:49` | KEEP unchanged — same v1 read-compat reason |
| `tests/unit/graphdb/test_schema_constants.py:37-42` | KEEP unchanged — explicitly tests ADR-25 D1 read-compat preservation |
| `tests/unit/test_graphdb_additions.py:53, 66` | Inspect at impl time; update if it asserts PARM_DECL emission, keep if it tests v1 compat |

`NODE_VARIABLE` stays exported from `schema.py` and stays in
`ALL_NODE_TYPES` (ADR-25 D1 read-compat invariant, also required by
SC-H-04/SC-H-05).

### D10 — Capability matrix (informational; not a decision but binds implementation)

Verified via libclang probe at architect-pass time on the pinned version.
Anything `present` may be used directly; anything `absent` requires the
same `getattr + callable + token-scan or enum fallback` pattern S1
established in `_var_qualifiers` and `_storage_class_value`.

| Capability | Status | Use |
|---|---|---|
| `Cursor.is_const_method()` | present | `cv_qualifiers="const"` |
| `Cursor.is_deleted_method()` | present | `is_deleted` |
| `Cursor.is_default_method()` | present | `is_defaulted` |
| `Cursor.is_pure_virtual_method()` | present | `is_abstract` aggregation |
| `Cursor.is_abstract_record()` | present | `Class.is_abstract` directly |
| `Cursor.is_anonymous()` | present | future-use (anonymous struct fields) |
| `Cursor.is_constexpr()` | **absent** | token-scan for `"constexpr"` (mirror S1 pattern) |
| `Cursor.is_noexcept` | **absent** | use `exception_specification_kind` — see D11 |
| `Cursor.exception_specification_kind` | present | source of `is_noexcept` |
| `Cursor.get_arguments()` | present | iterate parameters in order |
| `Cursor.result_type` | present | source of `RETURNS` Type |
| `Cursor.displayname` | present | `signature` per D7 |
| `Type.get_pointee()` | present | `POINTS_TO` / `REFERS_TO` target |
| `Type.get_ref_qualifier()` | present | `ref_qualifier` property |
| `Type.is_const_qualified()` | present | `Type.is_const` (top-level only per AC1) |
| `Type.is_volatile_qualified()` | present | `Type.is_volatile` |
| `Type.kind` (TypeKind enum) | present | `Type.kind` property (enum-name string) |
| `CursorKind.CXX_FINAL_ATTR` | present | `Class.is_final` detection |
| `RefQualifierKind` enum | present | NONE/LVALUE/RVALUE mapping to "", "&", "&&" |
| `ExceptionSpecificationKind` enum | present | see D11 |

There is no `is_volatile_method`.  `cv_qualifiers="volatile"` requires
token-scan for the `volatile` keyword in the method's signature tokens
(after the closing `)` and before `noexcept`/`override`/`{`).  Same
pattern S1 used in `_storage_class_value` for `thread_local`.

### D11 — `is_noexcept` semantics: only true for non-throwing specifications

`is_noexcept` is `True` iff `cursor.exception_specification_kind` is in:

```
{BASIC_NOEXCEPT, COMPUTED_NOEXCEPT}
```

`NOEXCEPT_FALSE` (`noexcept(false)`) → `is_noexcept = False`.  The C++
function *has* a noexcept exception specification, but the specification
promises that exceptions *may* be thrown — the property name reads as
"does this function promise not to throw?", so `noexcept(false)` answers
"no".

`DYNAMIC_NONE` (`throw()`, legacy) → `True`, since it promises no throws.
`UNEVALUATED`, `NONE`, `MS_ANY`, `BASIC_NOEXCEPT_DEPRECATED` etc. →
`False`.

Document this in implementation-notes.md; it is the kind of decision QA
will ask about when SC-F-09 lands.

---

## Alternatives considered

### Alt-A: Multi-label Type-as-property on existing nodes

Rejected.  Same constraint as ADR-25 D1: backends are single-label and
the introspector groups by single label / vertex type.  Type-as-property
also defeats the central S2 use case — querying "what functions return
`std::vector<int>`" requires Type as a first-class node so the query is a
single hop, not a property scan.

### Alt-B: Type USR = cursor USR of the declaring type

Rejected.  Builtins (`int`, `void`) have no cursor USR.  Pointer /
reference variants have no cursor USR.  Template instantiations
(`std::vector<int>`) share a USR with the primary template — distinct
instantiations would collide on dedup.  Hash-of-spelling is the only
scheme that works uniformly for every Type case in v2.

### Alt-C: Constructor → class Type, destructor → void

Rejected per D5.  Requires special-case lookup, conflates RETURNS with
CONSTRUCTS, and is reproducible client-side via MEMBER_OF without baking
the asymmetry into the schema.

### Alt-D: signature composed from HAS_PARAM + RETURNS at write time

Rejected per D7.  Reimplements libclang's `displayname` and invites
formatting bugs; consumers who need the full type+qualifier signature can
compose client-side from the property bag with a deterministic format
they control.

### Alt-E: Skip Type nodes for return type and parameter type; store as string property

Rejected.  Defeats reference question #4 ("what is the return type of X?")
as a graph query — a string property requires the consumer to fan out a
second query to find all functions sharing a return type.  The whole
point of S2 is to make type a first-class graph node.

---

## Consequences

### Positive

  - All eight S2 stories implementable with localized changes:
    `_KIND_TO_NODE_TYPE` (3 new mappings: `UNION_DECL`; PARM_DECL → new
    NODE_PARAMETER), one new helper (`_get_or_create_type`), one new
    classifier-style helper (`_emit_function_signature_props`), and a
    handful of additional emissions inside the existing
    `node_type and usr` block in `_walk_cursor`.  Driver code untouched.
  - Backward compat (SC-H-04, SC-H-05) holds by construction: new labels
    surface in the introspector automatically; legacy graphs without
    Type/Parameter nodes show empty buckets for those labels, not errors.
  - Forward path for S3 (template instantiation as Type spelling),
    S4 (virtual/override props on Function), S5 (Enum/Enumerator,
    `ALIAS_OF` between Types, `UNDERLYING_TYPE` enum → Type) is
    established: Type-as-content-hash scales to template spellings;
    Parameter-as-positional-child scales to template parameter positions
    in S3.
  - `record_kind` correctly handles all three C++ record kinds via D8
    rather than silently dropping `union` declarations.
  - Test churn is bounded and listed (D9 table).  QA / coordinator have
    an explicit list and can treat affected tests as expected updates,
    not regressions.

### Negative

  - Per-export Type-node count rises substantially.  A TU with N
    parameters whose distinct types number K produces K new Type vertices
    plus up to 2K POINTS_TO/REFERS_TO chain edges (pointer-to-pointer
    chains).  Acceptable; both backends already handle the {fmt}-scale
    workload (v6 live test: 99N/180E + signature data).  Re-validate
    against {fmt} during QA.
  - `Type.spelling` source-form means template typedefs and aliases
    produce distinct Type nodes for what ISO C++ considers the same type
    (`std::string` vs `std::basic_string<char>`).  Documented trade-off;
    a future `CANONICAL_OF` edge can layer the desugared view on top
    without schema breakage.
  - PARM_DECL → Parameter migration breaks 3-4 unit/integration tests
    that explicitly assert PARM_DECL → Variable (the ADR-25 D2
    transitional behavior).  D9 lists each test; treat as expected
    update.  v1-compat tests that seed literal `"Variable"` vertices
    stay unchanged — they verify SC-H-04 backward compat.
  - `displayname` for `signature` omits return type and qualifiers
    (D7).  Consumers must compose the full type+qualifier signature
    client-side if they need it.  Documented in implementation-notes.md.

### Follow-ups (out of S2 scope)

  - F-1 (S3): Type spelling for template instantiations
    (`std::vector<int>`) — D2 already handles this via `cursor.type.spelling`;
    INSTANTIATES edge wiring will reuse the same `_get_or_create_type`
    helper.
  - F-2 (S3): `is_template` on Function/Class — explicitly deferred per
    requirements §Deferred items.
  - F-3 (S4): `is_virtual`/`is_override` on Function and OVERRIDES edge
    — explicitly deferred.
  - F-4 (S5): `Enum`/`Enumerator` nodes plus `UNDERLYING_TYPE` edge from
    Enum to a `Type` node — D1's USR scheme already accommodates the
    enum's underlying type.
  - F-5 (future): `CANONICAL_OF` edge or property to map source-form
    Type nodes to ISO-canonical equivalents (per D2 trade-off).
  - F-6 (S2 implementation): developer verifies `Cursor.is_noexcept`
    truly absent on pinned libclang (matches probe at architect time);
    documents in implementation-notes.md.
  - F-7 (S2 implementation): developer verifies `cv_qualifiers="volatile"`
    token-scan handles edge cases (`const volatile`, line-break
    formatting) and adds a unit test for SC-F-04 with single-line and
    multi-line formatting.

---

## References

  - `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements.md`
    (S2-A..S2-H, OQ summary, Deferred items)
  - `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/scenarios.md`
    (SC-A-01..SC-FM-01, AC coverage index)
  - `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md`
    (invariants I1–I4; S2 schema additions §)
  - `src/cpp_mcp/graphdb/exporter.py` (post-S1) §`_KIND_TO_NODE_TYPE` (96-113),
    `_classify_field` (161-177), `_classify_node` (180-189), `_var_qualifiers`
    (241-276), `_storage_class_value` (293-344), `_walk_cursor` (388-665)
  - `src/cpp_mcp/graphdb/schema.py` (NODE_* / EDGE_* constants; ALL_NODE_TYPES,
    ALL_EDGE_TYPES)
  - `src/cpp_mcp/graphdb/schema_version.py` (`SCHEMA_VERSION = "v2"` — stays
    `"v2"` in S2 per CHARTER)
  - `src/cpp_mcp/graphdb/driver.py:17-46` (NodeRecord, EdgeRecord — single-label)
  - `src/cpp_mcp/graphdb/schema_introspector.py:121-128, 332-373` (live
    introspector — picks up Type/Parameter automatically)
  - ADR-7 (schema baseline), ADR-24 (live discovery + version stamp),
    ADR-25 (Variable split + transitional PARM_DECL)
  - Wiki: `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md`
    §"New node types", §"New / refined edge types", §"New properties on
    existing nodes"
  - Cognee tags: `task:cpp-mcp-v7-s2`, `role:architect`
