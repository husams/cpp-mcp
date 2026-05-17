# Design — cpp-mcp v7 Stage S2

Stage: S2 of 6
Authoritative ADR: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md`
(Status: accepted)
Reads: `requirements.md`, `scenarios.md`, `CHARTER.md`, `adr-25.md`,
post-S1 source under `src/cpp_mcp/graphdb/`.

This design is an extension of the S1 exporter pattern, not a refactor.
Every new emission piggybacks on the existing `_walk_cursor` DFS and
`seen_usrs` set.  No driver changes.  No schema_version bump (stays `"v2"`).

---

## 1. Schema additions (binds requirements §S2-A..S2-H)

### 1.1 New node types

| Constant | Label | Source cursor |
|---|---|---|
| `NODE_TYPE` | `"Type"` | derived from `cursor.type` of any decl that has one |
| `NODE_PARAMETER` | `"Parameter"` | `PARM_DECL` (replaces ADR-25 D2 transitional `Variable`) |

Append both to `ALL_NODE_TYPES` in `src/cpp_mcp/graphdb/schema.py`.
`NODE_VARIABLE` stays in `ALL_NODE_TYPES` (ADR-26 D9 read-compat).

### 1.2 New edge types

| Constant | Label | From → To |
|---|---|---|
| `EDGE_RETURNS` | `"RETURNS"` | `Function → Type` |
| `EDGE_HAS_PARAM` | `"HAS_PARAM"` | `Function → Parameter` (edge prop `index:int`) |
| `EDGE_OF_TYPE` | `"OF_TYPE"` | `{Parameter, Variable, Field, GlobalVariable} → Type` |
| `EDGE_POINTS_TO` | `"POINTS_TO"` | `Type → Type` (pointer pointee, chained per ADR-26 D4) |
| `EDGE_REFERS_TO` | `"REFERS_TO"` | `Type → Type` (reference referent, chained per ADR-26 D4) |

Append all five to `ALL_EDGE_TYPES` in `schema.py`.

### 1.3 New node properties

**`Type` node** (per ADR-26 D2 source-form spelling):

| Property | Type | Source |
|---|---|---|
| `spelling` | str | `cursor.type.spelling` (top-level only — qualifiers below are top-level too) |
| `is_const` | bool | `type.is_const_qualified()` (top-level qualifier) |
| `is_volatile` | bool | `type.is_volatile_qualified()` |
| `is_pointer` | bool | `type.kind == TypeKind.POINTER` |
| `is_reference` | bool | `type.kind in {LVALUEREFERENCE, RVALUEREFERENCE}` |
| `is_lvalue_reference` | bool | `type.kind == TypeKind.LVALUEREFERENCE` |
| `is_rvalue_reference` | bool | `type.kind == TypeKind.RVALUEREFERENCE` |
| `kind` | str | `type.kind.name` (e.g. `"POINTER"`, `"LVALUEREFERENCE"`, `"INT"`) |

**`Parameter` node** (per ADR-26 D6 positional USR):

| Property | Type | Source |
|---|---|---|
| `index` | int | enumeration order of `parent_function.get_arguments()` (0-based) |
| `name` | str | `param_cursor.spelling` (`""` for unnamed — SC-C-02) |
| `default_value` | str | scan `param_cursor.get_children()` for an initializer expression; render via `_render_default_value` (token concatenation between `=` and end of cursor extent); `""` when absent (SC-C-04) |
| `spelling` | str | name or `f"<param#{index}>"` for unnamed (debugging aid) |
| `file`/`line`/`col` | str/int/int | from `_safe_location` (mirrors existing pattern) |

**`Function` node — added S2 properties** (per S2-F):

| Property | Type | Source |
|---|---|---|
| `signature` | str | `cursor.displayname` (per ADR-26 D7) |
| `is_constexpr` | bool | token-scan for `"constexpr"` (ADR-26 D10: `is_constexpr` absent) |
| `is_noexcept` | bool | `cursor.exception_specification_kind in {BASIC_NOEXCEPT, COMPUTED_NOEXCEPT, DYNAMIC_NONE}` (per ADR-26 D11) |
| `is_deleted` | bool | `cursor.is_deleted_method()` (returns False for non-methods — safe) |
| `is_defaulted` | bool | `cursor.is_default_method()` |
| `cv_qualifiers` | str | `"const"` if `cursor.is_const_method()`; `"volatile"` if token-scan finds `volatile` in method qualifier tokens; `"const volatile"` if both; `""` otherwise |
| `ref_qualifier` | str | `cursor.type.get_ref_qualifier()` → `RefQualifierKind` → `""` / `"&"` / `"&&"` |

DEFERRED (do NOT emit in S2 — would fail "no S3+ work"):

  - `is_template` (Function) — S3
  - `is_virtual` (Function) — S4
  - `is_override` (Function) — S4

**`Class` node — added S2 properties** (per S2-G):

| Property | Type | Source |
|---|---|---|
| `is_final` | bool | walk `cursor.get_children()` for `CursorKind.CXX_FINAL_ATTR` (ADR-26 D10) |
| `is_abstract` | bool | `cursor.is_abstract_record()` (present on pinned libclang) |
| `record_kind` | str | `"class"` if `cursor.kind.name in {"CLASS_DECL","CLASS_TEMPLATE"}`; `"struct"` if `STRUCT_DECL`; `"union"` if `UNION_DECL` (per ADR-26 D8) |

DEFERRED: `is_template` (Class) — S3.

### 1.4 Classifier updates (ADR-26 D8, D9)

`_KIND_TO_NODE_TYPE` in `exporter.py:96-113` changes:

```python
"UNION_DECL": NODE_CLASS,             # ADR-26 D8 (new)
"PARM_DECL":  NODE_PARAMETER,         # ADR-26 D9 (was NODE_VARIABLE per ADR-25 D2)
```

`record_kind` is derived in the same place `_classify_field` is called —
either inline in `_walk_cursor`'s node-create block (preferred; mirrors
how `is_static` is emitted) or in a new `_classify_class_props(cursor)`
helper for symmetry.  Recommend the helper for testability.

---

## 2. Helper functions (mirrors S1's `_var_qualifiers` / `_storage_class_value` pattern)

All new helpers live in `exporter.py` between the existing helpers
(after `_storage_class_value`, before `_kind_name`).  Each is a pure
function of cursor inputs so unit tests can stub a fake cursor.

### 2.1 `_type_usr(spelling: str) -> str`

```python
def _type_usr(spelling: str) -> str:
    """ADR-26 D1: Type USR is type:<sha1(spelling)>."""
    import hashlib
    return f"type:{hashlib.sha1(spelling.encode('utf-8')).hexdigest()}"
```

### 2.2 `_type_props(t: Any) -> dict[str, Any]`

Returns the eight Type properties from §1.3 above.  All accesses guarded
by `try/except`, defaulting to `False`/`""` on failure (mirrors
`_safe_*` pattern).

### 2.3 `_get_or_create_type(t: Any, nodes: list[NodeRecord], edges: list[EdgeRecord], seen_usrs: set[str]) -> str | None`

Single helper used for return types, parameter types, variable/field/global
types, and recursive pointee/referent types.

```python
def _get_or_create_type(t, nodes, edges, seen_usrs) -> str | None:
    if t is None: return None
    try:
        spelling = t.spelling or ""
    except Exception:
        return None
    if not spelling:
        return None
    usr = _type_usr(spelling)
    if usr in seen_usrs:
        return usr
    seen_usrs.add(usr)
    nodes.append(NodeRecord(label=NODE_TYPE, usr=usr, props=_type_props(t)))

    # ADR-26 D4: recurse one level for pointer / reference shapes.
    try:
        from clang.cindex import TypeKind
        if t.kind == TypeKind.POINTER:
            pointee = t.get_pointee()
            pointee_usr = _get_or_create_type(pointee, nodes, edges, seen_usrs)
            if pointee_usr:
                edges.append(EdgeRecord(
                    source_usr=usr, target_usr=pointee_usr,
                    edge_type=EDGE_POINTS_TO, props={}))
        elif t.kind in (TypeKind.LVALUEREFERENCE, TypeKind.RVALUEREFERENCE):
            referent = t.get_pointee()  # libclang reuses get_pointee for refs
            referent_usr = _get_or_create_type(referent, nodes, edges, seen_usrs)
            if referent_usr:
                edges.append(EdgeRecord(
                    source_usr=usr, target_usr=referent_usr,
                    edge_type=EDGE_REFERS_TO, props={}))
    except Exception:
        pass
    return usr
```

Idempotent: re-calling with the same spelling does nothing (seen_usrs
guard).  The chain in §SC-B-05 emerges naturally: creating `int**` calls
itself for `int*`, which calls itself for `int`.

### 2.4 `_emit_function_signature_props(cursor: Any) -> dict[str, Any]`

Returns the seven Function S2 properties (`signature`, `is_constexpr`,
`is_noexcept`, `is_deleted`, `is_defaulted`, `cv_qualifiers`,
`ref_qualifier`).  All probes guarded; absent capabilities fall through
to safe defaults (mostly `False` / `""`).  See ADR-26 D10/D11 for the
authoritative capability matrix and `is_noexcept` semantics.

`cv_qualifiers` composition:

```python
cv = []
try:
    if cursor.is_const_method(): cv.append("const")
except Exception: pass
# volatile: no is_volatile_method; token-scan between ')' and next ';' or '{'
if _method_has_volatile_qualifier(cursor): cv.append("volatile")
cv_qualifiers = " ".join(cv)  # "", "const", "volatile", "const volatile"
```

`ref_qualifier` mapping:

```python
from clang.cindex import RefQualifierKind
rq = cursor.type.get_ref_qualifier()
ref_qualifier = {
    RefQualifierKind.NONE: "",
    RefQualifierKind.LVALUE: "&",
    RefQualifierKind.RVALUE: "&&",
}.get(rq, "")
```

### 2.5 `_emit_class_props(cursor: Any) -> dict[str, Any]`

Returns `{"is_final": bool, "is_abstract": bool, "record_kind": str}`.
`is_final` walks children for `CursorKind.CXX_FINAL_ATTR`; `is_abstract`
calls `cursor.is_abstract_record()`; `record_kind` derived from
`cursor.kind.name` per §1.3.

### 2.6 `_render_default_value(param_cursor: Any) -> str`

Returns the source-text spelling of a parameter's default value (`"0"`,
`"true"`, `"\"hello\""`), or `""` if no initializer.  Strategy: iterate
`param_cursor.get_tokens()`, capture tokens after the first `=` token
up to end of extent, join with single spaces, strip surrounding whitespace.
Edge case: multi-token defaults (`= std::string("x")`) preserved; the
property is a string, exact format documented in implementation-notes.md.

### 2.7 `_method_has_volatile_qualifier(cursor: Any) -> bool`

Token-scan helper: walk tokens of `cursor.extent`; find the `)` that
closes the parameter list (track paren depth); scan tokens after it until
`{`, `;`, `=`, or `->` (trailing return); return True if `"volatile"`
appears in that window.  Mirrors S1's `_storage_class_value` token-scan.

---

## 3. `_walk_cursor` integration points

Modifications, in source order, inside the existing
`if node_type and usr:` block (exporter.py:505-650):

### 3.1 After computing `props` (line 513-519), but before `nodes.append`:

  - If `node_type == NODE_FUNCTION`:
    `props.update(_emit_function_signature_props(cursor))`
  - If `node_type == NODE_CLASS`:
    `props.update(_emit_class_props(cursor))`
  - If `node_type == NODE_PARAMETER`:
    - compute `index` from sibling enumeration — see §3.2 below.
    - `props.update({"index": index, "name": spelling, "default_value": _render_default_value(cursor)})`
  - The existing Field / GlobalVariable block (520-530) is unchanged.

### 3.2 Parameter index sourcing

Parameters need their positional index.  Two viable approaches:

  - **(a) Inline:** when descending into a function cursor, the parent
    `_walk_cursor` call enumerates `cursor.get_arguments()` directly and
    emits Parameter nodes + HAS_PARAM edges in one pass, rather than
    relying on the generic child recursion.  **Recommended** — gives
    deterministic ordering and a single ground-truth for both the
    Parameter's `index` property and the HAS_PARAM edge's `index` prop.
  - (b) Generic recursion: track parameter index in a counter passed
    through `_walk_cursor`'s arguments; risks ordering bugs if libclang
    yields children out of order.

Recommend (a).  Pseudocode (after the Function node is appended and
RETURNS edge emitted, before generic child recursion):

```python
if kind in _FUNCTION_CURSOR_KINDS:
    # emit RETURNS edge (§3.3)
    ret_usr = _get_or_create_type(cursor.result_type, nodes, edges, seen_usrs)
    if ret_usr:
        edges.append(EdgeRecord(
            source_usr=usr, target_usr=ret_usr,
            edge_type=EDGE_RETURNS, props={}))
    # emit Parameter nodes + HAS_PARAM + OF_TYPE
    for idx, param in enumerate(cursor.get_arguments()):
        param_usr = f"{usr}#param:{idx}"
        if param_usr not in seen_usrs:
            seen_usrs.add(param_usr)
            param_type_usr = _get_or_create_type(param.type, nodes, edges, seen_usrs)
            nodes.append(NodeRecord(
                label=NODE_PARAMETER, usr=param_usr,
                props={
                    "spelling": param.spelling or f"<param#{idx}>",
                    "name": param.spelling or "",
                    "index": idx,
                    "default_value": _render_default_value(param),
                    **dict(zip(("file","line","col"), _safe_location(param))),
                }))
            edges.append(EdgeRecord(
                source_usr=usr, target_usr=param_usr,
                edge_type=EDGE_HAS_PARAM, props={"index": idx}))
            if param_type_usr:
                edges.append(EdgeRecord(
                    source_usr=param_usr, target_usr=param_type_usr,
                    edge_type=EDGE_OF_TYPE, props={}))
```

This block runs *before* the generic `for child in cursor.get_children()`
recursion.  PARM_DECL cursors encountered during generic recursion will
hit the `usr in seen_usrs` guard and not re-emit.  (Note: parameter USRs
emitted by libclang for PARM_DECL cursors during generic recursion will
be the original libclang USR, not the synthetic `#param:N` form — and
will not collide with ours.  The recommended fix: in the generic
recursion, skip cursors with `kind == "PARM_DECL"` whose parent function
has already been handled.  Implementer choice: either gate `_walk_cursor`
to skip PARM_DECL after the function-arg loop, or rely on the
`seen_usrs` guard plus the fact that the libclang-USR Parameter node and
the synthetic-USR Parameter node would be duplicates.  **Recommend
skip-PARM_DECL-in-generic-recursion**: cleaner, no duplicate vertices,
explicit in code.)

### 3.3 RETURNS edge

For every Function cursor (FUNCTION_DECL, CXX_METHOD, CONSTRUCTOR,
DESTRUCTOR, FUNCTION_TEMPLATE per `_FUNCTION_CURSOR_KINDS`), emit a
RETURNS edge to the Type for `cursor.result_type`.  Per ADR-26 D5,
ctors and dtors both yield `result_type.spelling == "void"` from
libclang — single Type, single edge, no special case.

### 3.4 OF_TYPE for Field / GlobalVariable / Variable

In the existing Field/GlobalVariable property block (exporter.py:520-530),
after computing properties, emit OF_TYPE:

```python
type_usr = _get_or_create_type(cursor.type, nodes, edges, seen_usrs)
if type_usr:
    edges.append(EdgeRecord(
        source_usr=usr, target_usr=type_usr,
        edge_type=EDGE_OF_TYPE, props={}))
```

Local variables (per SC-D-02) are currently classified as
`NODE_GLOBAL_VARIABLE` by S1 (`VAR_DECL → GlobalVariable` per
`_KIND_TO_NODE_TYPE`).  S2 does NOT change that classification.
SC-D-02's assertion ("Variable node with name `count`") is satisfied by
the existing GlobalVariable bucket for VAR_DECL, OR by re-classifying
local VAR_DECL to a future `Variable` node.  **Architect note:** the
S2 scenarios use the word "Variable node" loosely — read it as "the
node emitted for the local VAR_DECL", regardless of label.  ADR-25 made
VAR_DECL → GlobalVariable unconditionally; S2 does not revisit that
decision.  Developer must confirm SC-D-02's intent with QA; if the
literal label `Variable` is required, escalate before implementation
(this would be an ADR-25 revision, not an ADR-26 decision).

### 3.5 INCLUSION_DIRECTIVE / REFERENCES paths unchanged

The early-return blocks at exporter.py:411-478 are S2-orthogonal — no
modification.

---

## 4. Backward compatibility (SC-H-04, SC-H-05, SC-H-06)

  - `SCHEMA_VERSION` stays `"v2"` (CHARTER §S2 deployment note).
  - `describe_graph_schema` introspector groups by live label / vertex
    type.  Type / Parameter / RETURNS / HAS_PARAM / OF_TYPE / POINTS_TO
    / REFERS_TO surface automatically the first time they appear in a
    graph.  No introspector code change.
  - v1 graphs (SC-H-04): the only label they carry that S2 doesn't
    emit is the legacy `Variable`.  `NODE_VARIABLE` stays in
    `ALL_NODE_TYPES` per ADR-25 D1 + ADR-26 D9; read path is happy.
  - v2-from-S1 graphs (SC-H-05): no Type/Parameter nodes present; the
    introspector reports zero counts for those labels; queries against
    those labels return empty results.  No error.
  - SC-H-06 (1020 tests still pass): expected churn per ADR-26 D9 in
    3-4 tests asserting the ADR-25 D2 transitional PARM_DECL → Variable
    behavior.  Those tests must be updated to assert PARM_DECL →
    Parameter.  Tests that explicitly verify v1 read-compat (seeded
    `"Variable"` vertices) MUST stay unchanged.  Run the suite once
    after each refactor pass to catch incidental regressions early.

---

## 5. Per-story → implementation surface

| Story | ADR-26 decisions | Files touched | New helpers |
|---|---|---|---|
| S2-A Type node | D1, D2, D3 | schema.py, exporter.py | `_type_usr`, `_type_props`, `_get_or_create_type` |
| S2-B POINTS_TO/REFERS_TO | D4 | exporter.py | (inside `_get_or_create_type`) |
| S2-C Parameter + HAS_PARAM | D6, D9 | schema.py, exporter.py | (inline in §3.2 function block) |
| S2-D OF_TYPE | (none — uses D1) | exporter.py | (inline §3.4) |
| S2-E RETURNS | D5 | exporter.py | (inline §3.3) |
| S2-F Function sig props | D7, D10, D11 | exporter.py | `_emit_function_signature_props`, `_method_has_volatile_qualifier` |
| S2-G Class props | D8, D10 | schema.py, exporter.py | `_emit_class_props` |
| S2-H schema surface + compat | (read-side: none) | (no code; tests only) | — |

`schema.py` additions are 5 new constants + 5 ALL_*_TYPES updates.
`exporter.py` additions are ~150 lines across helpers + ~30 lines inside
`_walk_cursor`.  No driver, no executor, no introspector changes.

---

## 6. Test surface (binds scenarios.md)

| Scenario | Test layer | Notes |
|---|---|---|
| SC-A-01..SC-A-09 | unit (`tests/unit/graphdb/test_type_node.py` — new) | Fake cursor with `type.spelling`, `type.kind`, `type.is_const_qualified` etc. |
| SC-B-01..SC-B-05 | unit (`tests/unit/graphdb/test_type_edges.py` — new) | SC-B-05 (`int **`) verifies the chain |
| SC-C-01..SC-C-10 | unit (`tests/unit/graphdb/test_parameter_node.py` — new) | Fake function cursor with `get_arguments()` |
| SC-D-01..SC-D-05 | unit (extend `test_global_variable_classification.py`, `test_field_classification.py`) | OF_TYPE edge counts |
| SC-E-01..SC-E-05 | unit (extend `test_parameter_node.py`) | SC-E-04/SC-E-05 substitute `"void"` per ADR-26 D5 |
| SC-F-01..SC-F-12 | unit (`tests/unit/graphdb/test_function_signature.py` — new) | SC-F-01-sig substitutes `displayname` per ADR-26 D7 |
| SC-G-01..SC-G-06 | unit (`tests/unit/graphdb/test_class_props.py` — new) | SC-G-05 includes UNION_DECL row |
| SC-H-01..SC-H-03 | unit (extend `test_describe_*`) | Live introspector autopickup |
| SC-H-04..SC-H-05 | unit (existing `test_describe_v1_compat.py`, `test_indradb_query_subset.py`) | Must remain untouched (ADR-26 D9) |
| SC-H-06 | full suite | Run after every helper-add pass |
| SC-FM-01 | integration | Confirm `extract_nodes_and_edges` returns `(nodes, edges)` lists with no partial Type/Parameter entries when libclang fatal-errors |
| Live | integration (`tests/integration/test_describe_graph_schema_e2e.py`) | Update PARM-only Variable count assertion to Parameter count (ADR-26 D9 table) |

QA runs the full suite + an `ingest_code` smoke against `{fmt}` to
confirm Type / Parameter scale (similar to v6 live test).

---

## 7. Open issues escalated for coordinator visibility (not blockers)

  - **§3.4 SC-D-02 label literal:** scenarios use "Variable node" for a
    local VAR_DECL.  ADR-25 classifies VAR_DECL → GlobalVariable
    unconditionally.  If QA reads SC-D-02 as requiring the literal label
    `Variable`, this becomes an ADR-25 revision (not ADR-26).
    Recommendation: read SC-D-02 as "the node emitted for the local
    variable", regardless of label, and confirm with QA before fix
    pivots.  Not blocking; flagged so it doesn't surprise the developer.
  - **§3.2 skip-PARM_DECL-in-generic-recursion:** chosen to avoid
    duplicate Parameter vertices.  Implementer should add an assertion
    in `_walk_cursor` that PARM_DECL cursors are never reached via
    generic recursion after the function-argument loop, to fail loud if
    the assumption is violated by future cursor-tree changes.

---

## 8. References

  - ADR-26 (this stage's authoritative decision record)
  - ADR-25 (S1: Variable split + transitional PARM_DECL rule)
  - ADR-24 (live schema discovery + schema_version stamp)
  - ADR-7 (schema baseline)
  - `requirements.md`, `scenarios.md`, `CHARTER.md` (handoff v8)
  - `src/cpp_mcp/graphdb/` (post-S1, commit 774cd66) — exporter.py,
    schema.py, schema_version.py, driver.py, schema_introspector.py
  - Wiki: `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md`,
    `~/workspace/wiki/pages/code/cpp-mcp-v7-s1.md`
  - Cognee tags: `task:cpp-mcp-v7-s2`, `role:architect`
