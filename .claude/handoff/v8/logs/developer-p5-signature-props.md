# Developer Log — P5: Function signature properties

task-slug: cpp-mcp-v7-s2 (story P5)
stage: developer
date: 2026-05-17
handoff-dir: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/

## Skills loaded
- `python-conventions` — loaded before writing any code

## Skills considered but not loaded
- `implement-story` — task is a developer dispatch, not a new story dispatch; plan.md already provided full implementation spec
- `simplify` — no pre-existing duplication to remove; P5 is additive

## Orientation reads
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md`
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/plan.md` (P5 story)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/design.md` (§2.4, §2.7, §3.1)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md` (D7, D10, D11)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/implementation-notes.md` (P1–P4 state)
- `src/cpp_mcp/graphdb/exporter.py` (current state, all existing helpers and _walk_cursor)
- `tests/unit/graphdb/test_parameter_node.py` (function cursor mock pattern from P3/P4)

## Advisor call
Called advisor once before writing — advisor highlighted:
1. MagicMock truthy-return trap for is_const_method()/is_deleted_method()/is_default_method()
2. Token-scan must respect paren depth for volatile detection (avoid false-positives inside param list)
3. ExceptionSpecificationKind.NOEXCEPT_FALSE absence — must probe
4. ADR-26 F-7 follow-up: include multi-line volatile test alongside single-line

## Libclang probes run
```
uv run python -c "from clang.cindex import ExceptionSpecificationKind; print([m.name for m in ExceptionSpecificationKind])"
# → ['NONE', 'DYNAMIC_NONE', 'DYNAMIC', 'MS_ANY', 'BASIC_NOEXCEPT', 'COMPUTED_NOEXCEPT', 'UNEVALUATED', 'UNINSTANTIATED', 'UNPARSED']

uv run python -c "from clang.cindex import RefQualifierKind; print([m.name for m in RefQualifierKind])"
# → ['NONE', 'LVALUE', 'RVALUE']
```

Finding: `NOEXCEPT_FALSE` is absent. `COMPUTED_NOEXCEPT` covers both `noexcept(true)` and `noexcept(false)`. ADR-26 D11 maps COMPUTED_NOEXCEPT → True; this means `noexcept(false)` returns `is_noexcept=True`. Documented in implementation-notes.md §Libclang fallbacks.

## Commands run and outcomes

```
uv run ruff format src tests       → 1 file reformatted (test_function_signature.py import order)
uv run ruff check src tests        → 1 error (I001 import sort, 1 error RUF012 mutable class attr)
# Fix: added ClassVar annotation; ran ruff check --fix for I001
uv run ruff format src tests       → 142 files unchanged
uv run ruff check src tests        → All checks passed!
uv run pytest tests/unit/graphdb/test_function_signature.py -x -q  → 26 passed
uv run pytest tests/unit -x -q    → 1024 passed, 4 skipped, 0 failed
```

## Implementation details

### New helpers in exporter.py (between _render_default_value and _kind_name)

1. `_method_has_volatile_qualifier(cursor)`:
   - Walks `cursor.get_tokens()` tracking paren depth to find the `)` closing the param list
   - Scans tokens after that `)` until `{`, `;`, `=`, or `->` (trailing return)
   - Returns True if "volatile" appears in that window
   - Correctly ignores "volatile" inside param list (SC-F-04 negative test)

2. `_emit_function_signature_props(cursor)`:
   - Returns 7-key dict with all S2 Function props
   - `signature`: `cursor.displayname` (ADR-26 D7)
   - `is_constexpr`: native method if available, else token-scan (ADR-26 D10)
   - `is_noexcept`: `exception_specification_kind in {BASIC_NOEXCEPT, COMPUTED_NOEXCEPT, DYNAMIC_NONE}` (ADR-26 D11)
   - `is_deleted`: `cursor.is_deleted_method()` (guarded by getattr+callable)
   - `is_defaulted`: `cursor.is_default_method()` (guarded by getattr+callable)
   - `cv_qualifiers`: `"const"` via `is_const_method()` + `"volatile"` via token-scan
   - `ref_qualifier`: `RefQualifierKind` → `""` / `"&"` / `"&&"`

### Wire-in in _walk_cursor:
After the existing `if node_type in (NODE_FIELD, NODE_GLOBAL_VARIABLE):` block and before `nodes.append()`:
```python
if node_type == NODE_FUNCTION:
    props.update(_emit_function_signature_props(cursor))
```

## Test file: test_function_signature.py

26 tests covering:
- SC-F-01: all 7 props present with correct types
- SC-F-01-sig: signature == cursor.displayname (ADR-26 D7)
- SC-F-02: free function → cv_qualifiers="" and ref_qualifier=""
- SC-F-03: const method → cv_qualifiers="const"
- SC-F-04: volatile method → cv_qualifiers="volatile" (single-line + multi-line + negative param-list test)
- SC-F-05: const volatile → cv_qualifiers="const volatile"
- SC-F-06: deleted → is_deleted=True, is_defaulted=False
- SC-F-07: defaulted → is_defaulted=True, is_deleted=False
- SC-F-08: constexpr token-scan → is_constexpr=True; non-constexpr → False
- SC-F-09: BASIC_NOEXCEPT → True; DYNAMIC_NONE → True; absent spec → False; NONE kind → False
- SC-F-10: LVALUE ref_qualifier → "&"
- SC-F-11: RVALUE ref_qualifier → "&&"
- SC-F-12: regular function → is_deleted=False, is_defaulted=False
- Parametrized: all 4 _FUNCTION_CURSOR_KINDS (FUNCTION_DECL, CXX_METHOD, CONSTRUCTOR, DESTRUCTOR) get all 7 props
- FUNCTION_TEMPLATE also gets all 7 props

## Deviations from plan
- None. All decisions per design §2.4/§2.7/§3.1 and ADR-26 D7/D10/D11.
- DEFERRED as instructed: is_template, is_virtual, is_override (not added).

## Follow-ups (open items)
- P6: Class properties (is_final, is_abstract, record_kind) — next story
- The `noexcept(false)` / COMPUTED_NOEXCEPT ambiguity: if QA or a live test surface this as a defect, it requires either a future libclang upgrade or expression-inspection; not blocking S2 per ADR-26 D11 documentation.
