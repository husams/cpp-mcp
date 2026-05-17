# architect log — cpp-mcp v7 S2 (handoff v8)

Date: 2026-05-17
Inputs read: requirements.md, scenarios.md, CHARTER.md, adr-25.md, src/cpp_mcp/graphdb/{exporter,schema,schema_version,driver,schema_introspector}.py
Capability probe: libclang on pinned version — `is_noexcept` absent, `is_constexpr` absent on cursors, all other S2 surfaces present (`is_const_method`, `is_abstract_record`, `is_pure_virtual_method`, `get_arguments`, `result_type`, `displayname`, `Type.get_pointee`, `Type.get_ref_qualifier`, `CursorKind.CXX_FINAL_ATTR`, `ExceptionSpecificationKind`).

Deliverables:
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/design.md
- /Users/husam/workspace/cpp-mcp/.claude/handoff/v8/adr-26.md (Status: accepted)

ADR-26 resolved 7 open questions (D1 Type USR sha1-of-spelling; D2 source-form spelling not desugared — biggest QA-defect-risk decision, advisor concurred; D3 in-memory dedup via seen_usrs; D4 POINTS_TO/REFERS_TO chain via recursion; D5 ctor+dtor RETURNS → void Type, symmetric, no special case; D6 Parameter USR = `<fn-usr>#param:<i>`; D7 signature = `cursor.displayname`; D8 add UNION_DECL to kind map; D9 PARM_DECL → Parameter migration with explicit test update list; D10 capability matrix; D11 `is_noexcept` semantics — `noexcept(false)` → False).

Test churn budget identified: ~3-4 unit tests + 1 integration test will require updates because PARM_DECL no longer emits Variable (ADR-25 D2 transitional rule completes in S2). Itemized in ADR-26 D9 table. v1-compat tests that seed literal "Variable" vertices stay unchanged.

One open issue escalated for coordinator (not blocker): SC-D-02 uses literal "Variable" for a local VAR_DECL, but ADR-25 classifies all VAR_DECL → GlobalVariable. Recommendation in design §3.4 and §7: read SC-D-02 as label-agnostic; QA confirm before any literal-label fix pivot.

advisor() consulted once before writing — caught the desugared-vs-source-form Type spelling landmine (would have failed SC-A-01 immediately) and the missing UNION_DECL classifier entry (would have failed SC-G-05 row 3). Both folded into D2 and D8 respectively.

Closing status: clear (1 ADR, accepted; design.md written; all 7 open questions resolved).
