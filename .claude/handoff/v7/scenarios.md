# Scenarios — cpp-mcp v7 Stage S1

run_id: cpp-mcp-v7-s1
stage: S1 of 6
produced_by: business-analyst
charter: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md
requirements: /Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md

---

## Requirements

### In-scope

- S1-1: Variable node split — `Field` (non-static class data members) and `GlobalVariable` (all other variables)
- S1-2: `MEMBER_OF` edge `access` property (`public` | `protected` | `private`)
- S1-3: New properties on `Field` and `GlobalVariable` nodes: `is_static`, `is_const`, `is_constexpr`, `storage_class`
- S1-4: `describe_graph_schema` returns `schema_version: 2` reflecting all S1 changes
- S1-5: Unit test coverage for all S1-introduced types, properties, and edge attributes
- S1-6: Live IndraDB integration test extension for `Field`/`GlobalVariable` split and `access` filter

### Out-of-scope

- S2–S6: `Type` node; `Parameter` node; `RETURNS`/`OF_TYPE`/`HAS_PARAM` edges; function signature properties; templates; virtual dispatch; enums; namespaces; `ALIAS_OF`; IndraDB ordered-traversal verb
- `pyproject.toml` version bump (stays at 0.4.0; 0.5.0 reserved for end of S6)
- MCP tool public input/output signature changes (NC-1)
- S1-7 (ADR-25 authoring) — architect-owned; no scenarios generated here

### Assumptions

- `confirmed`: `constexpr` implies `const` in C++ (ISO C++ standard); exporter emits both `is_constexpr: true` and `is_const: true` for constexpr variables (S1-3 AC2).
- `confirmed`: C++ default access for struct members with no explicit specifier is `public` (S1-2 AC2).
- `confirmed`: C++ default access for class members with no explicit specifier is `private` (S1-2 AC3).
- `confirmed`: Static class data members are `GlobalVariable` nodes, not `Field` nodes (S1-1 AC3).
- `confirmed`: `extern` and `thread_local` are valid `storage_class` values (S1-3 AC4, AC5).
- `confirmed`: v1 graphs (schema_version 1, typed `Variable`, no `access` or new properties) must remain loadable and queryable without error (NC-2, multiple ACs).
- `assumed`: `extern thread_local` combined storage class is treated as `thread_local` in `storage_class` output (libclang precedence not explicit in requirements; implementer to confirm).
- `assumed`: S1-5 and S1-6 ACs are coverage gates — they assert that the unit/integration test suite contains the required test cases, verified by QA against this scenarios file rather than duplicating behavior already expressed in S1-1..S1-4 scenarios.
- `assumed`: `access` is emitted on `MEMBER_OF` edges for all member kinds (fields, methods, nested types) unless ADR-25 or OQ-4 resolution restricts it to Field-only; scenarios for S1-2 cover fields as the primary case.

### Open questions

- OQ-1 (S1-1): Should `Variable` label be entirely removed or retained alongside `Field`/`GlobalVariable`? Resolved by ADR-25. Scenarios for S1-1 and S1-4 are tagged `@needs-clarification` where the answer affects observable output.
- OQ-2 (S1-1): How should fields of anonymous structs/unions embedded as class members be classified? Scenarios are tagged `@needs-clarification`.
- OQ-3 (S1-2): What is the correct default `access` for a `union` member? libclang behavior not verified. Scenarios are tagged `@needs-clarification`.
- OQ-4 (S1-2): Should `access` be emitted on ALL `MEMBER_OF` edges or only those to `Field` nodes? Defer to architect. Edge-case scenario tagged `@needs-clarification`.
- OQ-5 (S1-3): What is the correct `storage_class` value for a non-static class data member (`Field`)? Options: `none`, omit, `auto`. Scenario tagged `@needs-clarification`.
- OQ-6 (S1-3): Should the exporter enforce the invariant that `is_static: true` never appears on a `Field` node (raise/warn), or silently tolerate it? Scenario tagged `@needs-clarification`.
- OQ-7 (S1-4): If ADR-25 retains `Variable` as a label, should `describe_graph_schema` list it alongside `Field`/`GlobalVariable`? Scenario tagged `@needs-clarification`.

### Edge cases

- `confirmed`: Static class data member → `GlobalVariable` (not `Field`) — see S1-1-SC3
- `confirmed`: `constexpr` variable → `is_const: true` AND `is_constexpr: true` — see S1-3-SC2
- `confirmed`: v1 graph read-back via `query_graphdb` — no error — see S1-1-SC4
- `confirmed`: v1 graph read-back via `describe_graph_schema` — no error — see S1-4-SC5
- `confirmed`: struct member with no specifier → `access: public` — see S1-2-SC2
- `confirmed`: class member with no specifier → `access: private` — see S1-2-SC3
- `confirmed`: `extern` variable → `storage_class: extern` — see S1-3-SC4
- `confirmed`: `thread_local` variable → `storage_class: thread_local` — see S1-3-SC5
- `assumed`: `extern thread_local` combined → storage_class value to be confirmed by implementer — see S1-3-EC1
- `needs-clarification`: Fields of anonymous struct/union embedded in a class — see S1-1-EC1 (OQ-2)
- `needs-clarification`: Union member default `access` — see S1-2-EC1 (OQ-3)
- `needs-clarification`: `storage_class` value for a non-static `Field` — see S1-3-EC2 (OQ-5)
- `needs-clarification`: `is_static: true` on a `Field` node — exporter behavior on invariant violation — see S1-3-EC3 (OQ-6)
- `needs-clarification`: `access` on non-Field `MEMBER_OF` edges (methods, nested types) — see S1-2-EC2 (OQ-4)
- `needs-clarification`: `describe_graph_schema` listing of `Variable` label if ADR-25 retains it — see S1-4-EC1 (OQ-7)
- No further cases identified beyond those above.

### Stakeholders

- Graph consumer: downstream agents and users issuing `query_graphdb` calls
- Tool operator: issues `describe_graph_schema` to detect schema version and adapt queries
- Developer: implements S1; reads ADR-25, design.md, plan.md; authors unit and integration tests
- QA engineer: validates scenario coverage against this file; files defects in test-report.md
- Architect: owns ADR-25; resolves OQ-1, OQ-4, OQ-6, OQ-7 before developer dispatch

---

## Gherkin

```gherkin
# ============================================================
# Feature S1-1: Variable node split — Field and GlobalVariable
# ============================================================

Feature: Variable node split into Field and GlobalVariable
  As a graph consumer
  I want class data members emitted as Field nodes and other variables as GlobalVariable nodes
  So that I can write schema-typed queries without post-filtering

  # --- S1-1 AC1 ---

  @S1-1.AC1
  Scenario: S1-1-SC1 — Non-static class data member is emitted as Field
    Given a C++ source file containing a class with a non-static data member "int x"
    When the exporter runs against that source file
    Then the exported graph contains a node of type "Field" for the data member "x"
    And the exported graph does NOT contain a node of type "Variable" for that member

  # --- S1-1 AC2 ---

  @S1-1.AC2
  Scenario: S1-1-SC2 — Namespace-scope variable is emitted as GlobalVariable
    Given a C++ source file containing a namespace-scope variable "int counter"
    When the exporter runs against that source file
    Then the exported graph contains a node of type "GlobalVariable" for "counter"
    And the exported graph does NOT contain a node of type "Variable" for that symbol

  @S1-1.AC2
  Scenario: S1-1-SC2b — File-scope static variable is emitted as GlobalVariable
    Given a C++ source file containing a file-scope static variable "static int file_count"
    When the exporter runs against that source file
    Then the exported graph contains a node of type "GlobalVariable" for "file_count"

  @S1-1.AC2
  Scenario: S1-1-SC2c — Extern declaration is emitted as GlobalVariable
    Given a C++ source file containing an extern declaration "extern int shared_val"
    When the exporter runs against that source file
    Then the exported graph contains a node of type "GlobalVariable" for "shared_val"

  # --- S1-1 AC3 ---

  @S1-1.AC3
  Scenario: S1-1-SC3 — Static class data member is emitted as GlobalVariable, not Field
    Given a C++ source file containing a class with a static data member "static int count"
    When the exporter runs against that source file
    Then the exported graph contains a node of type "GlobalVariable" for "count"
    And the exported graph does NOT contain a node of type "Field" for "count"

  # --- S1-1 AC4: backward-compatible read of v1 graph ---

  @S1-1.AC4
  Scenario: S1-1-SC4 — query_graphdb against a v1 graph raises no error
    Given a graph exported with schema_version 1 where all variable nodes are typed "Variable"
    When "query_graphdb" is called against that graph
    Then no error is raised
    And results are returned (missing v2 fields are tolerated)

  # --- S1-1 AC5: live IndraDB integration ---

  @S1-1.AC5 @integration
  Scenario: S1-1-SC5 — Live IndraDB fixture contains both Field and GlobalVariable nodes
    Given a live IndraDB instance is reachable
    And a test fixture C++ source containing a class data member and a namespace-scope variable
    When the exporter runs and exports to the live IndraDB backend
    Then the exported graph contains at least one node of type "Field"
    And the exported graph contains at least one node of type "GlobalVariable"
    And the two nodes are distinguishable by their type attribute

  # --- S1-1 Edge cases ---

  @S1-1.EC1 @needs-clarification
  Scenario: S1-1-EC1 — Fields of anonymous struct/union embedded in a class (OQ-2)
    Given a C++ source file containing a class with an anonymous struct or union as a member
    And the anonymous struct or union contains a data member "int y"
    When the exporter runs against that source file
    Then the classification of "y" as "Field" or another type is determined by ADR-25 or implementation notes
    # needs-clarification: OQ-2 — behavior for anonymous struct/union fields is undefined in requirements


# ============================================================
# Feature S1-2: MEMBER_OF edge access property
# ============================================================

Feature: MEMBER_OF edge carries access property
  As a graph consumer
  I want MEMBER_OF edges to carry an access property (public/protected/private)
  So that I can filter class members by visibility without re-parsing

  # --- S1-2 AC1 ---

  @S1-2.AC1
  Scenario Outline: S1-2-SC1 — Explicit access specifier is recorded on MEMBER_OF edge
    Given a C++ source file containing a class with a member "int <member>" declared under "<specifier>:"
    When the exporter runs against that source file
    Then the MEMBER_OF edge from the "<member>" Field node to the class carries access "<value>"

    Examples:
      | member   | specifier | value     |
      | pub_field | public   | public    |
      | pro_field | protected| protected |
      | pri_field | private  | private   |

  # --- S1-2 AC2 ---

  @S1-2.AC2
  Scenario: S1-2-SC2 — Struct member with no explicit access specifier defaults to public
    Given a C++ source file containing a struct (not class) with a member "int x" and no explicit access specifier
    When the exporter runs against that source file
    Then the MEMBER_OF edge for "x" carries access "public"

  # --- S1-2 AC3 ---

  @S1-2.AC3
  Scenario: S1-2-SC3 — Class member with no explicit access specifier defaults to private
    Given a C++ source file containing a class (not struct) with a member "int x" and no explicit access specifier
    When the exporter runs against that source file
    Then the MEMBER_OF edge for "x" carries access "private"

  # --- S1-2 AC4: live IndraDB access filter ---

  @S1-2.AC4 @integration
  Scenario: S1-2-SC4 — Live IndraDB query by access:private returns only private members
    Given a live IndraDB instance is reachable
    And a test fixture C++ class with members declared as public, protected, and private
    When the exporter exports to the live IndraDB backend
    And a query using "access: private" is issued for members of that class
    Then the query returns only the private member nodes
    And the query does not return public or protected member nodes

  # --- S1-2 AC5: backward-compatible read of v1 graph ---

  @S1-2.AC5
  Scenario: S1-2-SC5 — query_graphdb on v1 graph with no access property raises no error
    Given a graph exported with schema_version 1 where MEMBER_OF edges have no "access" property
    When "query_graphdb" is called against that graph
    Then no error is raised

  # --- S1-2 Edge cases ---

  @S1-2.EC1 @needs-clarification
  Scenario: S1-2-EC1 — Union member access default (OQ-3)
    Given a C++ source file containing a union with a member "int u" and no explicit access specifier
    When the exporter runs against that source file
    Then the MEMBER_OF edge for "u" carries access "public"
    # needs-clarification: OQ-3 — libclang behavior for union member access not verified; expected "public" per C++ spec but may need implementation notes to confirm

  @S1-2.EC2 @needs-clarification
  Scenario: S1-2-EC2 — access property on MEMBER_OF edges for non-Field members (OQ-4)
    Given a C++ source file containing a class with a member function "void foo()" declared under "public:"
    When the exporter runs against that source file
    Then the MEMBER_OF edge from the "foo" Function node to the class either carries access "public" or omits the access property
    # needs-clarification: OQ-4 — whether access is emitted on ALL MEMBER_OF edges or only Field edges deferred to architect

  @S1-2.EC3
  Scenario: S1-2-EC3 — access value is always within allowed set (negative boundary)
    Given a C++ source file with class members of all three access levels
    When the exporter runs against that source file
    Then every MEMBER_OF edge access value is one of "public", "protected", or "private"
    And no MEMBER_OF edge carries any other access value


# ============================================================
# Feature S1-3: New properties on Field and GlobalVariable nodes
# ============================================================

Feature: Field and GlobalVariable nodes carry is_static, is_const, is_constexpr, storage_class properties
  As a graph consumer
  I want Field and GlobalVariable nodes to carry storage and qualification properties
  So that I can filter variables without re-parsing

  # --- S1-3 AC1 ---

  @S1-3.AC1
  Scenario: S1-3-SC1 — const variable has is_const true
    Given a C++ source file containing "const int MAX = 100" at namespace scope
    When the exporter runs against that source file
    Then the GlobalVariable node for "MAX" has property is_const with value true

  # --- S1-3 AC2 ---

  @S1-3.AC2
  Scenario: S1-3-SC2 — constexpr variable has both is_constexpr true and is_const true
    Given a C++ source file containing "constexpr int LIMIT = 42" at namespace scope
    When the exporter runs against that source file
    Then the GlobalVariable node for "LIMIT" has property is_constexpr with value true
    And the GlobalVariable node for "LIMIT" has property is_const with value true

  # --- S1-3 AC3 ---

  @S1-3.AC3
  Scenario: S1-3-SC3 — static namespace-scope variable has is_static true and storage_class static
    Given a C++ source file containing "static int file_var = 0" at namespace scope
    When the exporter runs against that source file
    Then the GlobalVariable node for "file_var" has property is_static with value true
    And the GlobalVariable node for "file_var" has property storage_class with value "static"

  # --- S1-3 AC4 ---

  @S1-3.AC4
  Scenario: S1-3-SC4 — extern variable has storage_class extern
    Given a C++ source file containing "extern int shared_val" at namespace scope
    When the exporter runs against that source file
    Then the GlobalVariable node for "shared_val" has property storage_class with value "extern"

  # --- S1-3 AC5 ---

  @S1-3.AC5
  Scenario: S1-3-SC5 — thread_local variable has storage_class thread_local
    Given a C++ source file containing "thread_local int tls_var = 0" at namespace scope
    When the exporter runs against that source file
    Then the GlobalVariable node for "tls_var" has property storage_class with value "thread_local"

  # --- S1-3 AC6 ---

  @S1-3.AC6
  Scenario: S1-3-SC6 — non-static class data member Field has is_static false
    Given a C++ source file containing a class with a non-static data member "int value"
    When the exporter runs against that source file
    Then the Field node for "value" has property is_static with value false

  # --- S1-3 AC7 ---

  @S1-3.AC7
  Scenario: S1-3-SC7 — plain namespace-scope variable with no specifier has storage_class none
    Given a C++ source file containing "int plain_var = 0" at namespace scope with no storage-class specifier
    When the exporter runs against that source file
    Then the GlobalVariable node for "plain_var" has property storage_class with value "none"
    # Note: "none" value is pending OQ-5 resolution; this scenario uses "none" as the assumed default

  # --- S1-3 AC8: backward-compatible read of v1 graph ---

  @S1-3.AC8
  Scenario: S1-3-SC8 — query_graphdb on v1 graph with no new properties raises no error
    Given a graph exported with schema_version 1 where Variable nodes have no is_static, is_const, is_constexpr, or storage_class properties
    When "query_graphdb" is called against that graph
    Then no error is raised

  # --- S1-3 AC9: unit test coverage gate (per-property) ---

  @S1-3.AC9 @qa-gate
  Scenario Outline: S1-3-SC9 — Unit test suite contains at least one test for each new property covering both values
    Given the S1 unit test suite has been executed
    When the test results are inspected for property "<property>"
    Then there is at least one test asserting the property value true or a non-default alternate value
    And there is at least one test asserting the property value false or a default value

    Examples:
      | property      |
      | is_static     |
      | is_const      |
      | is_constexpr  |
      | storage_class |

  # --- S1-3 Edge cases ---

  @S1-3.EC1 @assumed
  Scenario: S1-3-EC1 — extern thread_local combined storage class (assumed behavior)
    Given a C++ source file containing "extern thread_local int ext_tls" at namespace scope
    When the exporter runs against that source file
    Then the GlobalVariable node for "ext_tls" has property storage_class with value "thread_local"
    # assumed: libclang precedence for combined extern thread_local resolves to "thread_local"; implementer must confirm and document in implementation-notes.md

  @S1-3.EC2 @needs-clarification
  Scenario: S1-3-EC2 — storage_class value for a non-static Field node (OQ-5)
    Given a C++ source file containing a class with a non-static data member "int val"
    When the exporter runs against that source file
    Then the Field node for "val" has a storage_class property whose value is one of "none", absent, or "auto"
    # needs-clarification: OQ-5 — exact value undefined in requirements; architect or developer to resolve in implementation-notes.md

  @S1-3.EC3 @needs-clarification
  Scenario: S1-3-EC3 — Exporter invariant: is_static true on a Field node (OQ-6)
    Given the exporter encounters a case where libclang classifies a static member as a Field node erroneously
    When the exporter processes that member
    Then the exporter either raises a warning or error, or silently corrects the classification to GlobalVariable
    # needs-clarification: OQ-6 — enforcement vs. tolerance decision deferred to architect; behavior must be documented in design.md

  @S1-3.EC4
  Scenario: S1-3-EC4 — non-const variable has is_const false
    Given a C++ source file containing "int mutable_var = 0" at namespace scope with no const qualifier
    When the exporter runs against that source file
    Then the GlobalVariable node for "mutable_var" has property is_const with value false
    And the GlobalVariable node for "mutable_var" has property is_constexpr with value false


# ============================================================
# Feature S1-4: schema_version bump and describe_graph_schema update
# ============================================================

Feature: describe_graph_schema reflects schema_version 2 and all S1 changes
  As a tool operator
  I want describe_graph_schema to return schema_version 2 and document all S1 additions
  So that clients can detect the schema version and adapt queries

  # --- S1-4 AC1 ---

  @S1-4.AC1
  Scenario: S1-4-SC1 — describe_graph_schema returns schema_version 2 after S1 export
    Given a graph exported after S1 changes are deployed
    When "describe_graph_schema" is called
    Then the response includes schema_version with value 2

  # --- S1-4 AC2 ---

  @S1-4.AC2 @needs-clarification
  Scenario: S1-4-SC2 — describe_graph_schema lists Field and GlobalVariable as node types
    Given a graph exported after S1 changes are deployed
    When "describe_graph_schema" is called
    Then the response lists "Field" as a node type
    And the response lists "GlobalVariable" as a node type
    # needs-clarification: OQ-1/OQ-7 — whether "Variable" also appears depends on ADR-25 resolution; see S1-4-EC1

  # --- S1-4 AC3 ---

  @S1-4.AC3
  Scenario: S1-4-SC3 — describe_graph_schema documents access as property of MEMBER_OF edge
    Given a graph exported after S1 changes are deployed
    When "describe_graph_schema" is called
    Then the response documents "access" as a property of the "MEMBER_OF" edge type

  # --- S1-4 AC4 ---

  @S1-4.AC4
  Scenario: S1-4-SC4 — describe_graph_schema documents new node properties
    Given a graph exported after S1 changes are deployed
    When "describe_graph_schema" is called
    Then the response documents "is_static" as a property of "Field" and "GlobalVariable" nodes
    And the response documents "is_const" as a property of "Field" and "GlobalVariable" nodes
    And the response documents "is_constexpr" as a property of "Field" and "GlobalVariable" nodes
    And the response documents "storage_class" as a property of "Field" and "GlobalVariable" nodes

  # --- S1-4 AC5: backward-compatible describe_graph_schema on v1 graph ---

  @S1-4.AC5
  Scenario: S1-4-SC5 — describe_graph_schema against v1 graph raises no error
    Given a graph exported with schema_version 1
    When "describe_graph_schema" is called against that graph
    Then no error is raised

  # --- S1-4 AC6: MCP tool signatures unchanged ---

  @S1-4.AC6
  Scenario Outline: S1-4-SC6 — MCP tool public input/output shapes are unchanged after S1
    Given S1 changes are deployed
    When the MCP tool "<tool>" is inspected for its public input and output schema
    Then the input schema is identical to the pre-S1 schema
    And the output schema is identical to the pre-S1 schema

    Examples:
      | tool                  |
      | ingest_code           |
      | query_graphdb         |
      | describe_graph_schema |

  # --- S1-4 Edge cases ---

  @S1-4.EC1 @needs-clarification
  Scenario: S1-4-EC1 — describe_graph_schema listing of Variable label if ADR-25 retains it (OQ-7)
    Given ADR-25 is resolved and the decision is to retain "Variable" as an additional label
    And a graph exported after S1 changes
    When "describe_graph_schema" is called
    Then the response either lists "Variable" alongside "Field" and "GlobalVariable", or lists only the leaf types
    # needs-clarification: OQ-7 — listing behavior deferred to architect per ADR-25


# ============================================================
# Feature S1-5: Unit test coverage for S1 changes
# ============================================================

Feature: Unit test suite covers all S1 node types, edge properties, and node properties
  As a developer
  I want every new type, property, and edge attribute to have dedicated unit tests
  So that regressions are caught before integration

  # --- S1-5 AC1 ---

  @S1-5.AC1 @qa-gate
  Scenario: S1-5-SC1 — All 880 pre-existing unit tests continue to pass after S1
    Given the S1 implementation is complete
    When the full unit test suite is executed
    Then all 880 pre-existing tests pass
    And the total failure count is zero

  # --- S1-5 AC2 ---

  @S1-5.AC2 @qa-gate
  Scenario: S1-5-SC2 — Unit suite contains a test asserting Field for non-static class data member
    Given the S1 unit test suite has been executed
    When the test results are inspected
    Then at least one test asserts that a non-static class data member produces a "Field" node

  # --- S1-5 AC3 ---

  @S1-5.AC3 @qa-gate
  Scenario: S1-5-SC3 — Unit suite contains a test asserting GlobalVariable for namespace-scope variable
    Given the S1 unit test suite has been executed
    When the test results are inspected
    Then at least one test asserts that a namespace-scope variable produces a "GlobalVariable" node

  # --- S1-5 AC4 ---

  @S1-5.AC4 @qa-gate
  Scenario: S1-5-SC4 — Unit suite covers MEMBER_OF.access for all three values
    Given the S1 unit test suite has been executed
    When the test results are inspected
    Then there is at least one test covering MEMBER_OF edge access value "public"
    And there is at least one test covering MEMBER_OF edge access value "protected"
    And there is at least one test covering MEMBER_OF edge access value "private"

  # --- S1-5 AC5 ---

  @S1-5.AC5 @qa-gate
  Scenario Outline: S1-5-SC5 — Unit suite covers each new node property with true and alternate values
    Given the S1 unit test suite has been executed
    When the test results are inspected for property "<property>"
    Then at least one test covers a true or non-default value for "<property>"
    And at least one test covers a false or default value for "<property>"

    Examples:
      | property      |
      | is_static     |
      | is_const      |
      | is_constexpr  |
      | storage_class |

  # --- S1-5 AC6 ---

  @S1-5.AC6 @qa-gate
  Scenario: S1-5-SC6 — Exporter round-trip test produces equivalent graph
    Given a C++ source file with class data members and namespace-scope variables
    When the exporter runs and exports the graph, then re-imports and compares node-by-node
    Then the resulting graph is equivalent to the pre-export graph for all Field and GlobalVariable nodes
    And no nodes or edges are lost in the round-trip


# ============================================================
# Feature S1-6: Live integration test extension
# ============================================================

Feature: Live IndraDB integration tests cover Field/GlobalVariable split and access filter
  As a developer
  I want the live integration test layer extended with S1 cases
  So that S1 behavior is verified end-to-end against a live graph backend

  # --- S1-6 AC1 ---

  @S1-6.AC1 @integration
  Scenario: S1-6-SC1 — Live fixture contains Field and GlobalVariable nodes; both are asserted by type
    Given a live IndraDB instance is reachable
    And a test fixture containing a C++ class with a non-static data member and a namespace-scope variable
    When the exporter runs and exports to the live IndraDB backend
    Then a query against the live graph returns at least one node with type "Field"
    And a query against the live graph returns at least one node with type "GlobalVariable"

  # --- S1-6 AC2 ---

  @S1-6.AC2 @integration
  Scenario: S1-6-SC2 — Live access filter query returns only private members
    Given a live IndraDB instance is reachable
    And a test fixture containing a C++ class with public, protected, and private data members
    When the exporter exports to the live IndraDB backend
    And a query filtering MEMBER_OF edges by access "private" is issued
    Then the query results contain only the private member nodes
    And the query results do not contain public or protected member nodes

  # --- S1-6 AC3 ---

  @S1-6.AC3 @integration @qa-gate
  Scenario: S1-6-SC3 — All 18 pre-existing live integration tests continue to pass after S1
    Given S1 implementation is complete and deployed to the live test environment
    When all live integration tests are executed
    Then all 18 pre-existing integration tests pass
    And no pre-existing test regresses
```

---

## References

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v7/requirements.md` — source of all stories and ACs
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v7/CHARTER.md` — invariants I1–I4, failure taxonomy, traceability chain
- `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md` — upstream PRD; v7 scope, node/edge definitions, coverage matrix
- `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md §"New properties on existing nodes"` — `MEMBER_OF.access`, `Variable`/`Field` properties
- Cognee tag: `task:cpp-mcp-v7-s1`, `role:business-analyst`
