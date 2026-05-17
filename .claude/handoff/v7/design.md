# Design — cpp-mcp v7 Stage S1

run_id: cpp-mcp-v7-s1
stage: S1 of 6
produced_by: architect
charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
requirements: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md
scenarios: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/scenarios.md
adrs: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md
schema target: 0.4.0 (no pyproject bump in S1)

---

## 1. Scope and trace

This design realises stories S1-1..S1-6. ADR-25 resolves OQ-1..OQ-7 plus
two gaps surfaced in architectural review (PARM_DECL transition and
`schema_version` value format). All decisions referenced below as
**D1..D8** are defined in `adr-25.md`.

| Story | AC ranges covered | Code touched |
|-------|-------------------|--------------|
| S1-1  | AC1..AC5          | `graphdb/exporter.py`, `graphdb/schema.py` |
| S1-2  | AC1..AC5          | `graphdb/exporter.py` |
| S1-3  | AC1..AC9          | `graphdb/exporter.py` |
| S1-4  | AC1..AC6          | `graphdb/schema_version.py`, `graphdb/schema_introspector.py` |
| S1-5  | AC1..AC6          | `tests/unit/graphdb/` |
| S1-6  | AC1..AC3          | `tests/integration/` |

CHARTER path note: the charter says `src/cpp_mcp/graphdb_export/`; the real
directory is `src/cpp_mcp/graphdb/`. This design uses the real path.

---

## 2. Schema diff (v1 → v2)

### Node types

| Constant         | Label             | v1                      | v2 (after S1)                                    |
|------------------|-------------------|-------------------------|--------------------------------------------------|
| NODE_FILE        | File              | unchanged               | unchanged                                        |
| NODE_NAMESPACE   | Namespace         | unchanged               | unchanged                                        |
| NODE_CLASS       | Class             | unchanged               | unchanged                                        |
| NODE_FUNCTION    | Function          | unchanged               | unchanged                                        |
| NODE_VARIABLE    | Variable          | FIELD/VAR/PARM_DECL     | **transitional**: PARM_DECL only (D2)            |
| NODE_FIELD       | **Field** (new)   | —                       | FIELD_DECL when not static (D1, D7)              |
| NODE_GLOBAL_VAR  | **GlobalVariable** (new) | —                | VAR_DECL + static FIELD_DECL (D1, D7)            |
| NODE_MACRO       | Macro             | unchanged               | unchanged                                        |
| NODE_TYPE_ALIAS  | TypeAlias         | unchanged               | unchanged                                        |

`ALL_NODE_TYPES` extends to include the two new labels. `NODE_VARIABLE`
constant remains exported (D1).

### Edge types

| Type        | v1 properties                 | v2 properties (after S1)               |
|-------------|-------------------------------|----------------------------------------|
| MEMBER_OF   | (none)                        | `access: public | protected | private` (D5) |
| DEFINES, DECLARES, CALLS, INHERITS, REFERENCES, INCLUDES | unchanged | unchanged |

### Node properties (Field and GlobalVariable)

| Property        | Type    | v1   | v2 source                                         |
|-----------------|---------|------|---------------------------------------------------|
| spelling        | str     | yes  | existing                                          |
| type            | str     | yes  | existing (`cursor.type.spelling`)                 |
| file, line, col | mixed   | yes  | existing                                          |
| is_static       | bool    | —    | `cursor.storage_class == StorageClass.STATIC` OR `cursor.is_static_member()` for FIELD_DECL |
| is_const        | bool    | —    | `cursor.type.is_const_qualified()`                |
| is_constexpr    | bool    | —    | tokenize cursor extent OR `cursor.is_constexpr()` if available; constexpr → also is_const (D6, scenario S1-3-SC2) |
| storage_class   | str     | —    | mapping from `cursor.storage_class` (see §4.3); `"none"` for non-static Field (D6) |

### schema_version

`SCHEMA_VERSION = "v2"` (string). Wire format unchanged from v1 (D8).
Stamped only on File nodes (existing behavior). Requirements prose says
"schema_version: 2" — read as the string `"v2"`. Do NOT change to int.

---

## 3. Classifier — canonical implementation

`_KIND_TO_NODE_TYPE` becomes a *partial* table; FIELD_DECL classification
becomes a function call because it depends on `is_static_member()`.

```python
# graphdb/exporter.py
from cpp_mcp.graphdb.schema import (
    NODE_FIELD, NODE_GLOBAL_VARIABLE, NODE_VARIABLE, ...
)

_KIND_TO_NODE_TYPE: dict[str, str] = {
    "NAMESPACE": NODE_NAMESPACE,
    "CLASS_DECL": NODE_CLASS,
    "STRUCT_DECL": NODE_CLASS,
    "CLASS_TEMPLATE": NODE_CLASS,
    "FUNCTION_DECL": NODE_FUNCTION,
    "CXX_METHOD": NODE_FUNCTION,
    "CONSTRUCTOR": NODE_FUNCTION,
    "DESTRUCTOR": NODE_FUNCTION,
    "FUNCTION_TEMPLATE": NODE_FUNCTION,
    "VAR_DECL": NODE_GLOBAL_VARIABLE,      # D1: VAR_DECL → GlobalVariable
    # "FIELD_DECL" classified at runtime (see _classify_field)
    "PARM_DECL": NODE_VARIABLE,            # D2: transitional
    "MACRO_DEFINITION": NODE_MACRO,
    "TYPEDEF_DECL": NODE_TYPE_ALIAS,
    "TYPE_ALIAS_DECL": NODE_TYPE_ALIAS,
    "TYPE_ALIAS_TEMPLATE_DECL": NODE_TYPE_ALIAS,
}

def _classify_node(cursor) -> str | None:
    kind = _kind_name(cursor)
    if kind == "FIELD_DECL":
        return _classify_field(cursor)
    return _KIND_TO_NODE_TYPE.get(kind)

def _classify_field(cursor) -> str:
    # D7: enforce invariant — static class data member → GlobalVariable
    if _is_static_member(cursor):
        return NODE_GLOBAL_VARIABLE
    return NODE_FIELD

def _is_static_member(cursor) -> bool:
    is_static = getattr(cursor, "is_static_member", None)
    if callable(is_static):
        try:
            return bool(is_static())
        except Exception:
            pass
    # Fallback: probe storage_class enum.
    try:
        from clang.cindex import StorageClass
        return cursor.storage_class == StorageClass.STATIC
    except Exception:
        return False
```

---

## 4. Property extraction

### 4.1 `is_const`, `is_constexpr`

```python
def _var_qualifiers(cursor) -> tuple[bool, bool]:
    try:
        is_const = bool(cursor.type.is_const_qualified())
    except Exception:
        is_const = False
    is_constexpr = False
    method = getattr(cursor, "is_constexpr", None)
    if callable(method):
        try:
            is_constexpr = bool(method())
        except Exception:
            is_constexpr = False
    if is_constexpr:
        is_const = True  # scenario S1-3-SC2 (constexpr implies const)
    return is_const, is_constexpr
```

If `is_constexpr()` is unavailable on the pinned libclang version, the
developer adds a token-scan fallback over `cursor.get_tokens()` looking
for `constexpr` (document in `implementation-notes.md`).

### 4.2 `is_static`

For VAR_DECL: `cursor.storage_class == StorageClass.STATIC`.
For FIELD_DECL: invariant — never `True` on a `Field` node (D7); for
`GlobalVariable` from a static member: `True`.

### 4.3 `storage_class` mapping

| `cursor.storage_class` (libclang enum) | emitted value     | scenario |
|----------------------------------------|-------------------|----------|
| `NONE` or `INVALID`                    | `"none"`          | S1-3-SC7 |
| `STATIC`                               | `"static"`        | S1-3-SC3 |
| `EXTERN`                               | `"extern"`        | S1-3-SC4 |
| `AUTO`                                 | `"auto"`          | —        |
| `REGISTER`                             | `"register"`      | —        |
| (libclang lacks a dedicated `THREAD_LOCAL` value) | `"thread_local"` if cursor exposes `is_thread_local`/token scan finds `thread_local` keyword | S1-3-SC5 |

Non-static `Field` nodes get `"none"` (D6) — regardless of what libclang
returns for FIELD_DECL.

**EC1 (`extern thread_local`)**: precedence is `thread_local`. The
developer verifies by tokenizing the cursor extent and choosing
`thread_local` if both `extern` and `thread_local` tokens are present.
Document the verification in `implementation-notes.md`.

### 4.4 `access` on MEMBER_OF (D5)

`exporter.py:312` — the existing `MEMBER_OF` branch — reads
`cursor.access_specifier` (libclang `AccessSpecifier` enum) and maps:

| Enum value          | Emitted `access` |
|---------------------|------------------|
| `PUBLIC`            | `"public"`       |
| `PROTECTED`         | `"protected"`    |
| `PRIVATE`           | `"private"`      |
| `INVALID` / `NONE`  | apply default: `"public"` for STRUCT_DECL/UNION_DECL parent; `"private"` for CLASS_DECL/CLASS_TEMPLATE parent |

Defaults (scenarios S1-2-SC2, S1-2-SC3) are determined by the parent
cursor kind, not by libclang — libclang sometimes returns `INVALID` for
implicit specifiers. The exporter must read the parent kind that's already
threaded through `_walk_cursor` (`parent_kind` parameter).

`access` is emitted on **all** `MEMBER_OF` edges (fields, methods,
ctors, dtors, nested types — D5). The existing block at `exporter.py:313`
already gates on the four "member" kinds; this list extends to include
nested CLASS_DECL/STRUCT_DECL/TYPEDEF_DECL only if they appear as
direct children of a class — this is **not required** for S1 but is
permitted because the code already runs through this branch when the
parent kind is one of `_MEMBER_PARENT_KINDS`.

For S1, the explicit requirement is: every `MEMBER_OF` edge currently
emitted (fields, methods, ctors, dtors) carries `access`. Adding nested
types to the emitter is a non-goal for S1 — flag as a follow-up.

---

## 5. MEMBER_OF construction (existing block, modified)

Current code (`exporter.py:311-326`) builds MEMBER_OF with empty props.
Patch:

```python
if parent_usr:
    if parent_kind in _MEMBER_PARENT_KINDS and kind in (
        "FIELD_DECL", "CXX_METHOD", "CONSTRUCTOR", "DESTRUCTOR",
    ):
        access = _resolve_access(cursor, parent_kind)
        edges.append(
            EdgeRecord(
                source_usr=usr,
                target_usr=parent_usr,
                edge_type=EDGE_MEMBER_OF,
                props={"access": access},   # D5
            )
        )
```

`_resolve_access` applies the table in §4.4.

---

## 6. Node-property population

In the `if node_type and usr:` block at `exporter.py:286-306`, after the
common `spelling/type/file/line/col` props, branch on `node_type`:

```python
props: dict[str, Any] = {
    "spelling": spelling,
    "type": type_spelling,
    "file": loc_file,
    "line": loc_line,
    "col": loc_col,
}
if node_type in (NODE_FIELD, NODE_GLOBAL_VARIABLE):
    is_const, is_constexpr = _var_qualifiers(cursor)
    props["is_const"] = is_const
    props["is_constexpr"] = is_constexpr
    props["is_static"] = (node_type == NODE_GLOBAL_VARIABLE
                          and _kind_name(cursor) == "FIELD_DECL") \
                          or _is_storage_static(cursor)
    props["storage_class"] = _storage_class_value(cursor, node_type)
nodes.append(NodeRecord(label=node_type, usr=usr, props=props))
```

D6: when `node_type == NODE_FIELD`, `_storage_class_value` returns
`"none"` regardless of libclang.

---

## 7. schema_version bump

```python
# graphdb/schema_version.py
SCHEMA_VERSION: str = "v2"   # was "v1"
```

This is the **only** change to this file. It cascades into:

  - `exporter.py:210` — `"schema_version": SCHEMA_VERSION` on File nodes
    (no source change; constant is re-imported).
  - `schema_introspector.py:188, 367` — `"schema_version": SCHEMA_VERSION`
    in the describe response (no source change).
  - `schema_introspector.py:464-476` — skew detection now treats `"v1"`
    as the legacy version; the existing message text is acceptable.

---

## 8. `describe_graph_schema` response (S1-4)

The describe shape is **unchanged** (NC-1, scenario S1-4-SC6). Only the
*values* surface the new types and properties because the introspector is
live: it queries Neo4j `db.labels()` / IndraDB `vertex.t` grouping and
samples properties. After S1, a fresh export produces:

```jsonc
{
  "schema_version": "v2",
  "backend": "neo4j",
  "node_types": [
    {"name": "Field", "count": N, "property_keys": ["col","file","is_const","is_constexpr","is_static","line","spelling","storage_class","type","usr"]},
    {"name": "GlobalVariable", "count": N, "property_keys": [...same as Field...]},
    {"name": "Function", ...},
    ...
  ],
  "edge_types": [
    {"name": "MEMBER_OF", "count": N, "property_keys": ["access"]},
    ...
  ],
  "totals": {...},
  "notes": [...]
}
```

For a legacy v1 graph (NC-2, scenarios S1-1-SC4, S1-2-SC5, S1-3-SC8,
S1-4-SC5): nothing in the describe code paths assumes the new labels or
properties. Legacy `Variable` nodes appear in `node_types`; MEMBER_OF
edges without `access` simply produce `property_keys: []`. No error.
The IndraDB introspector emits a skew note ("schema_version=v1…"); Neo4j
does not (existing blind spot; see ADR-25 follow-up F-2).

---

## 9. Test plan (architect-level, full detail in plan.md)

Unit tests (S1-5 AC2..AC6) — at minimum one each, all under
`tests/unit/graphdb/`:

  - **`test_field_classification.py`** — non-static class data member
    produces `Field` (S1-1 AC1), static class data member produces
    `GlobalVariable` (S1-1 AC3), no static member ever yields `Field`
    (D7 invariant), anonymous struct/union member yields `Field` with
    MEMBER_OF to nearest named class (D3).
  - **`test_global_variable_classification.py`** — namespace-scope var
    (S1-1 AC2), file-scope static (S1-1 AC2), extern decl (S1-1 AC2).
  - **`test_member_of_access.py`** — `Scenario Outline` table for
    public/protected/private (S1-2 AC1), struct default public (S1-2
    AC2), class default private (S1-2 AC3), union default public (D4),
    method MEMBER_OF carries access (D5), negative bounds (S1-2 EC3).
  - **`test_variable_properties.py`** — table covering `is_const`,
    `is_constexpr`, `is_static`, `storage_class` true/false matrix
    (S1-3 AC1..AC9), `Field.storage_class == "none"` (D6, S1-3 EC2),
    `extern thread_local → "thread_local"` (S1-3 EC1).
  - **`test_schema_version_bump.py`** — `SCHEMA_VERSION == "v2"`,
    File node carries it (S1-4 AC1).
  - **`test_describe_v1_compat.py`** — load a fixture v1 export
    (JSON or in-memory fake driver), call `describe_graph_schema`, no
    raise (S1-4 AC5; covers S1-1 AC4, S1-2 AC5, S1-3 AC8 by transitive
    read-path coverage).
  - **`test_round_trip.py`** — export → re-import → compare; S1-5 AC6.

Integration tests (S1-6 AC1..AC3) — under `tests/integration/`,
extending the live IndraDB harness from v4:

  - **`test_v7_s1_field_vs_global_live.py`** — fixture with class
    member + namespace var; assert at least one Field and at least one
    GlobalVariable vertex in the live store (S1-6 AC1).
  - **`test_v7_s1_access_filter_live.py`** — fixture with public,
    protected, private members; query by `access:private`; assert only
    private returned (S1-6 AC2).
  - **Regression sweep** — full existing 18-test integration suite runs
    green (S1-6 AC3).

Exit gates (plan.md will list exact commands):

  - `uv run ruff check src/ tests/`
  - `uv run pytest tests/unit -q` (was 880; must end ≥880 + new tests, 0
    fail)
  - `uv run pytest tests/integration -q` (was 18; must end ≥18 + 2 new, 0
    fail)

NC-3: `pyproject.toml` version stays at `0.4.0`. NC-4: commit message
exactly `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`.
NC-5: no S2..S6 code lands.

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `cursor.is_static_member()` not available on pinned libclang | medium | medium | Storage-class fallback in `_is_static_member` (§3) |
| `cursor.is_constexpr()` not available | medium | low | Token scan fallback (§4.1) |
| libclang returns INVALID access for implicit specifiers | high | medium | Parent-kind default in `_resolve_access` (§4.4) |
| Tests fixture v1 graph missing | medium | low | Build small JSON fixture for unit test or seed an in-memory fake driver pre-S1 |
| IndraDB skew note text confuses operators after `v1 → v2` bump | low | low | Note text already lists current vs observed version; no change needed |
| PARM_DECL still emits `Variable` in S1 exports (D2) | high | low | Document explicitly in test assertions; do not assert "no Variable nodes" globally |

---

## 11. References

  - ADR-25 (this stage): /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/adr-25.md
  - ADR-7  (schema baseline), ADR-17 (insert counting), ADR-24 (live discovery + version stamp): /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/adr-22.md and earlier
  - Code: src/cpp_mcp/graphdb/{exporter,schema,schema_version,schema_introspector,neo4j_driver,indradb_driver}.py
  - Wiki PRD: ~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md
  - Cognee tag: `task:cpp-mcp-v7-s1`, `role:architect`
