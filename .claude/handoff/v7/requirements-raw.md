# cpp-mcp v7 — Stage S1 (raw requirements)

Source PRD: `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` (read for full context — this run scopes to S1 only).

## S1 scope (additive, non-breaking)

1. **Split `Variable` node type** into two:
   - `Field` — non-static class data members.
   - `GlobalVariable` — everything else previously emitted as `Variable` (namespace-scope variables, file-scope statics, extern declarations).
   - Pick a transition path and document in an ADR:
     - (a) deprecate `Variable` and stop emitting it; OR
     - (b) keep `Variable` as a parent label and add `Field`/`GlobalVariable` as additional labels.
     - Pick whichever is cleaner for BOTH Neo4j and IndraDB backends. Document trade-offs in the ADR.

2. **Add `access` property** on the `MEMBER_OF` edge: `public` | `protected` | `private`. Default `public` for struct, `private` for class when not otherwise stated by libclang.

3. **Add new properties** on `Variable`/`Field`/`GlobalVariable` nodes:
   - `is_static` (bool)
   - `is_const` (bool)
   - `is_constexpr` (bool)
   - `storage_class` (string: `auto` | `static` | `extern` | `thread_local` | `register` | `none`)

4. **Bump `schema_version`** in the exporter from `1` to `2`. `describe_graph_schema` MUST reflect:
   - new node types (`Field`, `GlobalVariable`, possibly retain `Variable` per ADR)
   - new `MEMBER_OF.access` property
   - new variable/field properties
   - Keep v1 graphs READABLE — read path tolerates missing v2 fields without error.

5. **Unit tests** (must all pass, must not regress existing 880-test suite):
   - ≥1 test per new node type (`Field`, `GlobalVariable`).
   - ≥1 test for `MEMBER_OF.access` (cover public/protected/private).
   - ≥1 test per new property (`is_static`, `is_const`, `is_constexpr`, `storage_class`).
   - Exporter round-trip parity (export → re-import → equivalent graph).

6. **Live integration test** (extends existing live IndraDB test layer):
   - At least one case exercising the `Field` vs `GlobalVariable` distinction.
   - At least one case exercising the `access` filter (e.g., "find private fields of class X").

7. **ADR** under `.claude/handoff/v7/` starting at number 25 (last existing is adr-24 in v6) for the Variable split decision.

## Out of scope (defer to later stages)

- S2: `Type` node + `RETURNS`/`OF_TYPE`/`HAS_PARAM` + function signature props.
- S3: Templates (`INSTANTIATES`/`SPECIALIZES`/`TEMPLATE_*`/`Concept`).
- S4: Virtual dispatch (`OVERRIDES`, `FRIEND_OF`, `INHERITS.virtual/access`).
- S5: Enums, namespaces (`USES_*`), `ALIAS_OF`.
- S6: IndraDB ordered-traversal verb; ADR roll-up; `describe_graph_schema` v2 full rewrite.

## Completion rule

- Commit on `main` with message: `v7-S1: split Variable→Field/GlobalVariable; add MEMBER_OF.access`.
- Full unit test suite green (currently 880 unit / 0 fail / 6 skip).
- Run live IndraDB integration tests; report counts.
- DO NOT bump `pyproject.toml` version (0.5.0 is reserved for end of S6).
- DO NOT proceed to S2.

## Backward compatibility

- All v1 (`schema_version: 1`) graphs must still load and be queryable through `query_graphdb` and `describe_graph_schema` after this change.
- Existing 7 MCP tools' input/output shapes unchanged at the public boundary; only the produced graph's schema gains optional fields.
