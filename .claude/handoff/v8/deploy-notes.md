stage: S2 — Type/Parameter node enrichment + Function/Class props
run_id: cpp-mcp-v7-s2
target-context: n/a — library package, no cluster target
date: 2026-05-17

## Version verification

| Artifact | Expected | Actual | Status |
|----------|----------|--------|--------|
| pyproject.toml version | 0.4.0 | 0.4.0 | PASS |
| schema_version (src/cpp_mcp/graphdb/schema_version.py) | "v2" | "v2" | PASS |
| uv build output | cpp_mcp-0.4.0.tar.gz + .whl | both produced | PASS |

## Build smoke

Command run:
```
uv build
```

Output:
```
Building source distribution...
Building wheel from source distribution...
Successfully built dist/cpp_mcp-0.4.0.tar.gz
Successfully built dist/cpp_mcp-0.4.0-py3-none-any.whl
```

Zero errors. Artifacts in `dist/`.

## Test gate (from test-report.md)

| Suite | Passed | Skipped | Failed |
|-------|--------|---------|--------|
| unit (all) | 1183 | 7 | 0 |
| integration | 39 deselected (daemon absent) | — | 0 |
| ruff format | 0 changes | — | — |
| ruff check | 0 violations | — | — |

Open QA_DEFECT entries: **none** (CHARTER I4 satisfied).

## What S2 added (schema-level)

S2 enriches v2 additively. No schema_version bump; no pyproject bump.

New node labels:
- `Type` — canonical type spelling; deduplicated by USR hash of spelling
- `Parameter` — positional function parameter; props: `index`, `name`, `default_value`

New edge types:
- `RETURNS` — Function → Type
- `HAS_PARAM` — Function → Parameter (with `index` edge property)
- `OF_TYPE` — Parameter/Field/GlobalVariable → Type
- `POINTS_TO` — Type → Type (pointer pointee; chains for `T**`)
- `REFERS_TO` — Type → Type (reference referent; lvalue/rvalue mutually exclusive)

New Function node properties:
- `signature` (= cursor.displayname, per ADR-26 D7)
- `is_constexpr`, `is_noexcept`, `is_deleted`, `is_defaulted`
- `cv_qualifiers` ("", "const", "volatile", "const volatile")
- `ref_qualifier` ("", "&", "&&")

New Class node properties:
- `is_final`, `is_abstract`, `record_kind` ("class" | "struct" | "union")

`PARM_DECL` cursors now emit `Parameter` nodes (was `Variable`; ADR-26 D9). The `NODE_VARIABLE` constant remains exported for read-compat with existing graphs.

## PARM_DECL reclassification note for consumers

Code that queries `node_type = "Variable"` to find function parameters will no longer match on graphs produced by S2+ builds. Query `node_type = "Parameter"` instead. Existing `Variable` nodes in v1 and v2-from-S1 graphs continue to read without errors.

## Not done in S2 (reserved)

- pyproject bump 0.4.0 → 0.5.0: reserved for end of S6
- schema_version bump: stays "v2" for all S2–S5 stages
- is_template (Function/Class): S3
- is_virtual / is_override / OVERRIDES: S4
- Enum / ALIAS_OF / ENUMERATOR_OF: S5
- IndraDB ordered-traversal verb: S6
- git tag v0.4.0: not applied (interior stage; tag after S6 completes)
- PyPI publish: not done

## Deploy action

No cluster action required. This is a pure Python library stage.

Next steps for downstream consumers:
1. `pip install --upgrade cpp-mcp` (after eventual PyPI publish at S6 end)
   or install from dist/ artifact directly: `pip install dist/cpp_mcp-0.4.0-py3-none-any.whl`
2. Call `describe_graph_schema` and confirm `Type` and `Parameter` appear in `node_types`
   and the five new edge types appear in `edge_types` (see runbook.md for exact commands).

## Deferred actions (advisory, not blocking)

- EC-16: No top-level guard around `cursor.get_children()` in `extract_nodes_and_edges`; a
  raw libclang exception propagates uncaught. Behaviour is fail-fast. ADR-26 does not mandate
  a guard; SC-FM-01 get_children path is tagged `@assumed` and is skipped, not failed.
  Add a transactional guard in a follow-up story before S6 close if fail-fast is unacceptable.
- Integration totals re-pin: run `ingest_code` against {fmt}/os.cc with a live IndraDB daemon
  after S2 is accepted; update the >= baseline in test_describe_graph_schema_e2e.py.

## References

- plan.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/plan.md
- implementation-notes.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/implementation-notes.md
- test-report.md: /Users/husam/workspace/cpp-mcp/.claire/handoff/v8/test-report.md
- ADR-26: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md
- CHARTER: /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md
- Cognee tags: task:cpp-mcp-v7-s2, role:devops
