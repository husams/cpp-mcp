# Scenarios — cpp-mcp v7 Stage S2

Stage: S2 of 6
Upstream: requirements.md (PM, handoff v8)
Downstream: architect reads this file; developers implement against it.

---

## Requirements

### In-scope

- S2-A: Type node (spelling, is_const, is_volatile, is_pointer, is_reference, is_lvalue_reference, is_rvalue_reference, kind, USR as type:<sha1>)
- S2-B: POINTS_TO / REFERS_TO edges between Type nodes
- S2-C: Parameter node (index, name, default_value) + HAS_PARAM edge (Function → Parameter)
- S2-D: OF_TYPE edge (Parameter / Variable / Field / GlobalVariable → Type)
- S2-E: RETURNS edge (Function → Type)
- S2-F: Function signature properties (signature, is_constexpr, is_noexcept, is_deleted, is_defaulted, cv_qualifiers, ref_qualifier)
- S2-G: Class properties (is_final, is_abstract, record_kind)
- S2-H: describe_graph_schema reflects S2 additions; backward compat (v1 and v2-from-S1 graphs)

### Out-of-scope (do NOT add scenarios for these)

- is_template on Function or Class (S3)
- is_virtual / is_override on Function (S4)
- OVERRIDES / FRIEND_OF / INHERITS.is_virtual (S4)
- INSTANTIATES / SPECIALIZES / TEMPLATE_PARAM / TEMPLATE_ARG / CONSTRAINED_BY / Concept node (S3)
- Enum / Enumerator / ENUMERATOR_OF / UNDERLYING_TYPE / USES_* / ALIAS_OF (S5)
- IndraDB ordered-traversal verb (S6)
- pyproject version bump 0.4.0 → 0.5.0 (S6 final)

### Assumptions

- S1 is fully shipped at commit 774cd66; schema_version="v2"; 1020 unit / 0 fail / 6 skip (confirmed).
- Type dedup is keyed by canonical spelling only; two Type nodes with identical spellings are never created (confirmed).
- POINTS_TO / REFERS_TO chase exactly one level of indirection per edge; int** produces two chained edges: int** →POINTS_TO→ int* →POINTS_TO→ int (assumed; see open question 2 — needs-clarification on exact depth bound).
- Constructor RETURNS rule is TBD (needs-clarification; see open question 1).
- Canonical signature string source is TBD (needs-clarification; see open question 3).
- Empty string is the sentinel for unnamed parameter name and absent default_value (confirmed).

### Open questions

1. **[S2-E] Constructor / destructor RETURNS rule** — ADR-26 must decide: does a constructor RETURNS the constructed class Type, void, or is excluded? Same for destructor. Scenarios SC-E-04 and SC-E-05 are marked `needs-clarification` and carry placeholder rules pending ADR-26.
2. **[S2-B] int** POINTS_TO chain depth** — Requirements AC4 states "depth bounded at 1; multi-level pointers produce one edge per level, not unbounded recursion." This describes a chain of edges (each edge = 1 level), not a depth cap of 1 edge total. Architect must state explicitly in ADR-26 whether int** produces a 2-edge chain (int** →POINTS_TO→ int* →POINTS_TO→ int) or only one edge (int** →POINTS_TO→ int, skipping int*). Scenario SC-B-05 is marked `needs-clarification`.
3. **[S2-F] Canonical signature string source** — ADR-26 must confirm whether `signature` is the libclang cursor spelling, composed from HAS_PARAM+RETURNS, or another form. Scenario SC-F-01-sig is marked `needs-clarification`.

### Edge cases enumerated

| ID | Description | Tag |
|----|-------------|-----|
| EC-1 | Builtin types (int, void) are deduped to a single Type node | confirmed |
| EC-2 | int** multi-pointer chain produces chained POINTS_TO edges | needs-clarification |
| EC-3 | Unnamed parameter (void f(int)) emits Parameter with name="" | confirmed |
| EC-4 | Default parameter value (void f(int x = 0)) stored as string "0" | confirmed |
| EC-5 | Constructor RETURNS rule (void or class Type or excluded) | needs-clarification |
| EC-6 | Destructor RETURNS rule (void or excluded) | needs-clarification |
| EC-7 | Method with lvalue ref-qualifier (&) sets ref_qualifier="&" | confirmed |
| EC-8 | Method with rvalue ref-qualifier (&&) sets ref_qualifier="&&" | confirmed |
| EC-9 | deleted function sets is_deleted=true | confirmed |
| EC-10 | defaulted function sets is_defaulted=true | confirmed |
| EC-11 | Abstract class (≥1 pure virtual) sets is_abstract=true | confirmed |
| EC-12 | Non-pointer/non-reference Type has zero outgoing POINTS_TO/REFERS_TO | confirmed |
| EC-13 | is_lvalue_reference and is_rvalue_reference are mutually exclusive on any Type node | confirmed |
| EC-14 | v1 graph loaded after S2 ships does not error | confirmed |
| EC-15 | v2-from-S1 graph (no Type/Parameter nodes) loaded after S2 ships does not error | confirmed |
| EC-16 | Malformed/incomplete TU produces no half-created Type nodes (no partial state) | assumed |

### Stakeholders

- Graph consumers (LLM agents querying the graph)
- Developers implementing S2
- Architect ratifying ADR-26
- QA executing these scenarios

---

## Gherkin

### Feature: S2-A — Type Node Creation and Deduplication

```gherkin
Feature: Type node creation and deduplication
  As a graph consumer
  I want first-class Type nodes with canonical type properties
  So that I can query types without re-parsing source

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-A.AC1 — basic Type node properties
  @S2-A.AC1 @confirmed
  Scenario: SC-A-01 — Type node created with all required properties
    Given a C++ source file containing the declaration:
      """
      void foo(const std::string & s);
      """
    When the file is ingested
    Then a Type node exists with spelling "const std::string &"
    And that Type node has is_const equal to false
    And that Type node has is_volatile equal to false
    And that Type node has is_pointer equal to false
    And that Type node has is_reference equal to true
    And that Type node has is_lvalue_reference equal to true
    And that Type node has is_rvalue_reference equal to false
    And that Type node has a non-empty kind property

  # S2-A.AC1 — pointer type properties
  @S2-A.AC1 @confirmed
  Scenario: SC-A-02 — Pointer Type node has is_pointer true
    Given a C++ source file containing the declaration:
      """
      void bar(int * p);
      """
    When the file is ingested
    Then a Type node exists with spelling "int *"
    And that Type node has is_pointer equal to true
    And that Type node has is_reference equal to false
    And that Type node has is_lvalue_reference equal to false
    And that Type node has is_rvalue_reference equal to false

  # S2-A.AC1 — builtin type (EC-1: int dedup)
  @S2-A.AC1 @edge-case @confirmed
  Scenario: SC-A-03 — Builtin type int creates a single Type node
    Given a C++ source file containing the declarations:
      """
      void f(int a);
      void g(int b);
      """
    When the file is ingested
    Then exactly one Type node exists with spelling "int"

  # S2-A.AC1 — builtin type void (EC-1: void dedup)
  @S2-A.AC1 @edge-case @confirmed
  Scenario: SC-A-04 — Builtin type void creates a single Type node
    Given a C++ source file containing the declarations:
      """
      void f();
      void g();
      """
    When the file is ingested
    Then exactly one Type node exists with spelling "void"

  # S2-A.AC2 — dedup across declarations
  @S2-A.AC2 @confirmed
  Scenario: SC-A-05 — Two declarations sharing the same canonical type produce one Type node
    Given a C++ source file containing the declarations:
      """
      int foo(const std::string & a);
      int bar(const std::string & b);
      """
    When the file is ingested
    Then exactly one Type node exists with spelling "const std::string &"

  # S2-A.AC3 — USR format
  @S2-A.AC3 @confirmed
  Scenario: SC-A-06 — Type node USR follows type:<sha1(canonical_spelling)> format
    Given a C++ source file containing the declaration:
      """
      void foo(int x);
      """
    When the file is ingested
    Then the Type node with spelling "int" has a USR matching the pattern "type:[0-9a-f]{40}"

  # S2-A.AC4 — mutual exclusion of lvalue/rvalue reference flags
  @S2-A.AC4 @edge-case @confirmed
  Scenario: SC-A-07 — lvalue reference Type has is_lvalue_reference true and is_rvalue_reference false
    Given a C++ source file containing the declaration:
      """
      void foo(int & r);
      """
    When the file is ingested
    Then the Type node with spelling "int &" has is_lvalue_reference equal to true
    And the Type node with spelling "int &" has is_rvalue_reference equal to false

  @S2-A.AC4 @edge-case @confirmed
  Scenario: SC-A-08 — rvalue reference Type has is_rvalue_reference true and is_lvalue_reference false
    Given a C++ source file containing the declaration:
      """
      void foo(int && r);
      """
    When the file is ingested
    Then the Type node with spelling "int &&" has is_rvalue_reference equal to true
    And the Type node with spelling "int &&" has is_lvalue_reference equal to false

  @S2-A.AC4 @confirmed
  Scenario: SC-A-09 — No Type node ever has both is_lvalue_reference and is_rvalue_reference true
    Given a C++ source file containing mixed reference declarations:
      """
      void foo(int & a, int && b, const std::string & c);
      """
    When the file is ingested
    Then no Type node exists where both is_lvalue_reference and is_rvalue_reference are true
```

---

### Feature: S2-B — Type-Shape Edges (POINTS_TO / REFERS_TO)

```gherkin
Feature: Type-shape edges POINTS_TO and REFERS_TO
  As a graph consumer
  I want POINTS_TO and REFERS_TO edges between Type nodes
  So that I can traverse pointer and reference chains in graph queries

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-B.AC1 — POINTS_TO on pointer type
  @S2-B.AC1 @confirmed
  Scenario: SC-B-01 — Pointer Type has exactly one outgoing POINTS_TO edge
    Given a C++ source file containing the declaration:
      """
      void foo(int * p);
      """
    When the file is ingested
    Then the Type node with spelling "int *" has exactly one outgoing POINTS_TO edge
    And that POINTS_TO edge points to the Type node with spelling "int"

  # S2-B.AC2 — REFERS_TO on reference type
  @S2-B.AC2 @confirmed
  Scenario: SC-B-02 — Reference Type has exactly one outgoing REFERS_TO edge
    Given a C++ source file containing the declaration:
      """
      void foo(const std::string & s);
      """
    When the file is ingested
    Then the Type node with spelling "const std::string &" has exactly one outgoing REFERS_TO edge
    And that REFERS_TO edge points to the Type node with spelling "const std::string"

  # S2-B.AC2 — rvalue reference REFERS_TO
  @S2-B.AC2 @confirmed
  Scenario: SC-B-03 — Rvalue reference Type has exactly one outgoing REFERS_TO edge
    Given a C++ source file containing the declaration:
      """
      void foo(int && r);
      """
    When the file is ingested
    Then the Type node with spelling "int &&" has exactly one outgoing REFERS_TO edge
    And that REFERS_TO edge points to the Type node with spelling "int"

  # S2-B.AC3 — non-pointer/non-reference has no POINTS_TO or REFERS_TO (EC-12)
  @S2-B.AC3 @edge-case @negative @confirmed
  Scenario: SC-B-04 — Non-pointer non-reference Type has zero outgoing POINTS_TO or REFERS_TO edges
    Given a C++ source file containing the declaration:
      """
      void foo(int x, double y);
      """
    When the file is ingested
    Then the Type node with spelling "int" has zero outgoing POINTS_TO edges
    And the Type node with spelling "int" has zero outgoing REFERS_TO edges
    And the Type node with spelling "double" has zero outgoing POINTS_TO edges
    And the Type node with spelling "double" has zero outgoing REFERS_TO edges

  # S2-B.AC4 — multi-pointer chain (EC-2: int** depth)
  @S2-B.AC4 @edge-case @needs-clarification
  Scenario: SC-B-05 — int** pointer chain produces chained POINTS_TO edges
    # needs-clarification: ADR-26 must confirm whether int** produces
    # a 2-edge chain (int** →POINTS_TO→ int* →POINTS_TO→ int)
    # or collapses to one edge (int** →POINTS_TO→ int, skipping int*).
    # This scenario assumes the chain interpretation (one edge per level).
    Given a C++ source file containing the declaration:
      """
      void foo(int ** pp);
      """
    When the file is ingested
    Then a Type node exists with spelling "int **"
    And a Type node exists with spelling "int *"
    And a Type node exists with spelling "int"
    And the Type node with spelling "int **" has exactly one outgoing POINTS_TO edge to the Type node with spelling "int *"
    And the Type node with spelling "int *" has exactly one outgoing POINTS_TO edge to the Type node with spelling "int"
```

---

### Feature: S2-C — Parameter Node and HAS_PARAM Edge

```gherkin
Feature: Parameter node and HAS_PARAM edge
  As a graph consumer
  I want Parameter nodes connected to Function nodes via HAS_PARAM edges
  So that I can query the ordered parameter list of any function or method

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-C.AC1 — N parameters produce N Parameter nodes with correct properties
  @S2-C.AC1 @confirmed
  Scenario: SC-C-01 — Function with 3 parameters emits 3 Parameter nodes with correct index and name
    Given a C++ source file containing the declaration:
      """
      int add(int a, double b, const std::string & c);
      """
    When the file is ingested
    Then 3 Parameter nodes are connected to the Function node for "add"
    And a Parameter node exists with index 0 and name "a"
    And a Parameter node exists with index 1 and name "b"
    And a Parameter node exists with index 2 and name "c"

  # S2-C.AC1 — unnamed parameter (EC-3)
  @S2-C.AC1 @edge-case @confirmed
  Scenario: SC-C-02 — Unnamed parameter emits a Parameter node with name equal to empty string
    Given a C++ source file containing the declaration:
      """
      void process(int, double);
      """
    When the file is ingested
    Then a Parameter node exists with index 0 and name ""
    And a Parameter node exists with index 1 and name ""

  # S2-C.AC1 — default parameter value (EC-4)
  @S2-C.AC1 @edge-case @confirmed
  Scenario: SC-C-03 — Parameter with default value stores default_value as string spelling
    Given a C++ source file containing the declaration:
      """
      void resize(int n = 0, bool clear = true);
      """
    When the file is ingested
    Then the Parameter node with index 0 has default_value equal to "0"
    And the Parameter node with index 1 has default_value equal to "true"

  # S2-C.AC1 — parameter without default
  @S2-C.AC1 @confirmed
  Scenario: SC-C-04 — Parameter without default value has default_value equal to empty string
    Given a C++ source file containing the declaration:
      """
      void foo(int x);
      """
    When the file is ingested
    Then the Parameter node with index 0 has default_value equal to ""

  # S2-C.AC2 — HAS_PARAM edges carry index property
  @S2-C.AC2 @confirmed
  Scenario: SC-C-05 — HAS_PARAM edge index property equals the Parameter node index property
    Given a C++ source file containing the declaration:
      """
      void swap(int & a, int & b);
      """
    When the file is ingested
    Then the HAS_PARAM edge from Function "swap" to the Parameter with index 0 has edge property index equal to 0
    And the HAS_PARAM edge from Function "swap" to the Parameter with index 1 has edge property index equal to 1

  # S2-C.AC3 — methods / constructors / destructors also emit HAS_PARAM
  @S2-C.AC3 @confirmed
  Scenario: SC-C-06 — Member function emits HAS_PARAM edges to its Parameter nodes
    Given a C++ source file containing the class:
      """
      class Foo {
      public:
        void bar(int x, int y);
      };
      """
    When the file is ingested
    Then the Function node for "Foo::bar" has 2 HAS_PARAM edges
    And a Parameter node exists with index 0 and name "x"
    And a Parameter node exists with index 1 and name "y"

  @S2-C.AC3 @confirmed
  Scenario: SC-C-07 — Constructor emits HAS_PARAM edges to its Parameter nodes
    Given a C++ source file containing the class:
      """
      class Widget {
      public:
        Widget(int width, int height);
      };
      """
    When the file is ingested
    Then the Function node for "Widget::Widget" has 2 HAS_PARAM edges
    And a Parameter node exists with index 0 and name "width"
    And a Parameter node exists with index 1 and name "height"

  @S2-C.AC3 @confirmed
  Scenario: SC-C-08 — Destructor emits HAS_PARAM edge count of zero (destructors have no parameters)
    Given a C++ source file containing the class:
      """
      class Widget {
      public:
        ~Widget();
      };
      """
    When the file is ingested
    Then the Function node for "Widget::~Widget" has 0 HAS_PARAM edges

  # S2-C.AC4 — ordering by index equals source declaration order
  @S2-C.AC4 @confirmed
  Scenario: SC-C-09 — Parameters retrieved sorted by HAS_PARAM index appear in source declaration order
    Given a C++ source file containing the declaration:
      """
      void build(const char * name, int version, bool debug);
      """
    When the file is ingested
    And HAS_PARAM edges for Function "build" are sorted by index
    Then the Parameter at index 0 has name "name"
    And the Parameter at index 1 has name "version"
    And the Parameter at index 2 has name "debug"

  # S2-C.AC5 — zero-parameter function (boundary)
  @S2-C.AC5 @boundary @confirmed
  Scenario: SC-C-10 — Function with no parameters has zero HAS_PARAM edges and zero Parameter nodes
    Given a C++ source file containing the declaration:
      """
      void doNothing();
      """
    When the file is ingested
    Then the Function node for "doNothing" has 0 HAS_PARAM edges
    And no Parameter node is linked to Function "doNothing"
```

---

### Feature: S2-D — OF_TYPE Edge

```gherkin
Feature: OF_TYPE edge from symbol nodes to Type nodes
  As a graph consumer
  I want OF_TYPE edges from Parameter, Variable, Field, and GlobalVariable nodes to Type nodes
  So that I can query the declared type of any symbol

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-D.AC1 — Parameter → OF_TYPE → Type
  @S2-D.AC1 @confirmed
  Scenario: SC-D-01 — Parameter node has exactly one outgoing OF_TYPE edge to its Type node
    Given a C++ source file containing the declaration:
      """
      void foo(const std::string & s);
      """
    When the file is ingested
    Then the Parameter node with name "s" has exactly one outgoing OF_TYPE edge
    And that OF_TYPE edge points to the Type node with spelling "const std::string &"

  # S2-D.AC2 — Variable → OF_TYPE → Type
  @S2-D.AC2 @confirmed
  Scenario: SC-D-02 — Local Variable node has exactly one outgoing OF_TYPE edge to its Type node
    Given a C++ source file containing the function body:
      """
      void foo() {
        int count = 0;
      }
      """
    When the file is ingested
    Then the Variable node with name "count" has exactly one outgoing OF_TYPE edge
    And that OF_TYPE edge points to the Type node with spelling "int"

  # S2-D.AC3 — Field → OF_TYPE → Type
  @S2-D.AC3 @confirmed
  Scenario: SC-D-03 — Field node has exactly one outgoing OF_TYPE edge to its Type node
    Given a C++ source file containing the class:
      """
      class Point {
        double x;
        double y;
      };
      """
    When the file is ingested
    Then the Field node with name "x" has exactly one outgoing OF_TYPE edge
    And that OF_TYPE edge points to the Type node with spelling "double"
    And the Field node with name "y" has exactly one outgoing OF_TYPE edge
    And that OF_TYPE edge points to the Type node with spelling "double"

  # S2-D.AC4 — GlobalVariable → OF_TYPE → Type
  @S2-D.AC4 @confirmed
  Scenario: SC-D-04 — GlobalVariable node has exactly one outgoing OF_TYPE edge to its Type node
    Given a C++ source file containing the global declaration:
      """
      const int MAX_SIZE = 1024;
      """
    When the file is ingested
    Then the GlobalVariable node with name "MAX_SIZE" has exactly one outgoing OF_TYPE edge
    And that OF_TYPE edge points to a Type node with spelling matching "const int" or "int"

  # S2-D.AC5 — no duplicates, no zero-count
  @S2-D.AC5 @confirmed
  Scenario: SC-D-05 — Each symbol node has exactly one OF_TYPE edge (no duplicates, no missing)
    Given a C++ source file containing mixed declarations:
      """
      int g_counter = 0;
      class Box {
        float width;
      };
      void fn(char * buf) {
        bool done = false;
      }
      """
    When the file is ingested
    Then the GlobalVariable node with name "g_counter" has exactly 1 outgoing OF_TYPE edge
    And the Field node with name "width" has exactly 1 outgoing OF_TYPE edge
    And the Parameter node with name "buf" has exactly 1 outgoing OF_TYPE edge
    And the Variable node with name "done" has exactly 1 outgoing OF_TYPE edge
```

---

### Feature: S2-E — RETURNS Edge

```gherkin
Feature: RETURNS edge from Function nodes to Type nodes
  As a graph consumer
  I want a RETURNS edge from each Function node to a Type node
  So that I can answer "what is the return type of function X?" in one graph query

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-E.AC1 — free function RETURNS
  @S2-E.AC1 @confirmed
  Scenario: SC-E-01 — Free function has exactly one outgoing RETURNS edge
    Given a C++ source file containing the declaration:
      """
      int compute(int a, int b);
      """
    When the file is ingested
    Then the Function node for "compute" has exactly one outgoing RETURNS edge
    And that RETURNS edge points to the Type node with spelling "int"

  # S2-E.AC2 — method RETURNS
  @S2-E.AC2 @confirmed
  Scenario: SC-E-02 — Non-constructor non-destructor method has exactly one outgoing RETURNS edge
    Given a C++ source file containing the class:
      """
      class Counter {
      public:
        int getValue() const;
      };
      """
    When the file is ingested
    Then the Function node for "Counter::getValue" has exactly one outgoing RETURNS edge
    And that RETURNS edge points to the Type node with spelling "int"

  # S2-E.AC3 — void return type
  @S2-E.AC3 @confirmed
  Scenario: SC-E-03 — Function returning void has RETURNS edge to Type node with spelling "void"
    Given a C++ source file containing the declaration:
      """
      void reset();
      """
    When the file is ingested
    Then the Function node for "reset" has exactly one outgoing RETURNS edge
    And that RETURNS edge points to the Type node with spelling "void"

  # S2-E.AC4 — constructor RETURNS (EC-5)
  @S2-E.AC4 @edge-case @needs-clarification
  Scenario: SC-E-04 — Constructor has exactly one RETURNS edge per the ADR-26 rule
    # needs-clarification: ADR-26 must decide whether constructor RETURNS
    # (a) the constructed class Type, (b) void, or (c) is excluded.
    # This scenario asserts only that exactly one RETURNS edge exists and it is consistent.
    # Implementer must substitute the concrete Type spelling after ADR-26 is accepted.
    Given a C++ source file containing the class:
      """
      class Widget {
      public:
        Widget(int w, int h);
      };
      """
    When the file is ingested
    Then the Function node for "Widget::Widget" has exactly one outgoing RETURNS edge
    And the target Type node spelling matches the rule documented in ADR-26

  # S2-E.AC4 — destructor RETURNS (EC-6)
  @S2-E.AC4 @edge-case @needs-clarification
  Scenario: SC-E-05 — Destructor has exactly one RETURNS edge per the ADR-26 rule
    # needs-clarification: ADR-26 must decide whether destructor RETURNS void or is excluded.
    Given a C++ source file containing the class:
      """
      class Widget {
      public:
        ~Widget();
      };
      """
    When the file is ingested
    Then the Function node for "Widget::~Widget" has exactly one outgoing RETURNS edge
    And the target Type node spelling matches the rule documented in ADR-26
```

---

### Feature: S2-F — Function Signature Properties

```gherkin
Feature: Function signature properties
  As a graph consumer
  I want additional properties on Function nodes describing qualifiers and calling convention
  So that I can filter functions by constexpr, noexcept, deleted, defaulted, cv-qualifiers, ref-qualifiers

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-F.AC1 — all required properties present (signature needs-clarification)
  @S2-F.AC1 @confirmed
  Scenario: SC-F-01 — Every Function node has all required signature properties
    Given a C++ source file containing the declaration:
      """
      int add(int a, int b);
      """
    When the file is ingested
    Then the Function node for "add" has a "signature" property of type string
    And the Function node for "add" has an "is_constexpr" property of type bool
    And the Function node for "add" has an "is_noexcept" property of type bool
    And the Function node for "add" has an "is_deleted" property of type bool
    And the Function node for "add" has an "is_defaulted" property of type bool
    And the Function node for "add" has a "cv_qualifiers" property of type string
    And the Function node for "add" has a "ref_qualifier" property of type string

  @S2-F.AC1 @needs-clarification
  Scenario: SC-F-01-sig — Function signature string has the canonical form ratified in ADR-26
    # needs-clarification: ADR-26 must confirm whether signature is libclang cursor spelling
    # or composed from HAS_PARAM+RETURNS. Implementer must substitute expected value after ADR-26.
    Given a C++ source file containing the declaration:
      """
      void foo(int x, const std::string & s) const noexcept;
      """
    When the file is ingested
    Then the Function node for "foo" has a "signature" property matching the canonical form in ADR-26

  # S2-F.AC2 — free function cv_qualifiers and ref_qualifier are empty
  @S2-F.AC2 @confirmed
  Scenario: SC-F-02 — Free function has empty cv_qualifiers and empty ref_qualifier
    Given a C++ source file containing the declaration:
      """
      void compute(int x);
      """
    When the file is ingested
    Then the Function node for "compute" has cv_qualifiers equal to ""
    And the Function node for "compute" has ref_qualifier equal to ""

  # S2-F.AC3 — const method
  @S2-F.AC3 @confirmed
  Scenario: SC-F-03 — const method has cv_qualifiers equal to "const"
    Given a C++ source file containing the class:
      """
      class Foo {
      public:
        int getValue() const;
      };
      """
    When the file is ingested
    Then the Function node for "Foo::getValue" has cv_qualifiers equal to "const"

  # S2-F.AC3 — volatile method
  @S2-F.AC3 @confirmed
  Scenario: SC-F-04 — volatile method has cv_qualifiers equal to "volatile"
    Given a C++ source file containing the class:
      """
      class Foo {
      public:
        void poll() volatile;
      };
      """
    When the file is ingested
    Then the Function node for "Foo::poll" has cv_qualifiers equal to "volatile"

  # S2-F.AC3 — const volatile method
  @S2-F.AC3 @confirmed
  Scenario: SC-F-05 — const volatile method has cv_qualifiers equal to "const volatile"
    Given a C++ source file containing the class:
      """
      class Foo {
      public:
        int inspect() const volatile;
      };
      """
    When the file is ingested
    Then the Function node for "Foo::inspect" has cv_qualifiers equal to "const volatile"

  # S2-F.AC4 — deleted function (EC-9)
  @S2-F.AC4 @edge-case @confirmed
  Scenario: SC-F-06 — deleted function has is_deleted equal to true
    Given a C++ source file containing the class:
      """
      class NoCopy {
      public:
        NoCopy(const NoCopy &) = delete;
      };
      """
    When the file is ingested
    Then the Function node for "NoCopy::NoCopy" (copy constructor) has is_deleted equal to true
    And the Function node for "NoCopy::NoCopy" (copy constructor) has is_defaulted equal to false

  # S2-F.AC5 — defaulted function (EC-10)
  @S2-F.AC5 @edge-case @confirmed
  Scenario: SC-F-07 — defaulted function has is_defaulted equal to true
    Given a C++ source file containing the class:
      """
      class Widget {
      public:
        Widget() = default;
      };
      """
    When the file is ingested
    Then the Function node for "Widget::Widget" (default constructor) has is_defaulted equal to true
    And the Function node for "Widget::Widget" (default constructor) has is_deleted equal to false

  # S2-F.AC6 — constexpr function
  @S2-F.AC6 @confirmed
  Scenario: SC-F-08 — constexpr function has is_constexpr equal to true
    Given a C++ source file containing the declaration:
      """
      constexpr int square(int x) { return x * x; }
      """
    When the file is ingested
    Then the Function node for "square" has is_constexpr equal to true

  # S2-F.AC7 — noexcept function
  @S2-F.AC7 @confirmed
  Scenario: SC-F-09 — noexcept function has is_noexcept equal to true
    Given a C++ source file containing the declaration:
      """
      void safeReset() noexcept;
      """
    When the file is ingested
    Then the Function node for "safeReset" has is_noexcept equal to true

  # ref-qualifier & (EC-7)
  @S2-F.AC1 @edge-case @confirmed
  Scenario: SC-F-10 — Method with lvalue ref-qualifier has ref_qualifier equal to "&"
    Given a C++ source file containing the class:
      """
      class Builder {
      public:
        Builder & build() &;
      };
      """
    When the file is ingested
    Then the Function node for "Builder::build" has ref_qualifier equal to "&"

  # ref-qualifier && (EC-8)
  @S2-F.AC1 @edge-case @confirmed
  Scenario: SC-F-11 — Method with rvalue ref-qualifier has ref_qualifier equal to "&&"
    Given a C++ source file containing the class:
      """
      class Builder {
      public:
        Builder && build() &&;
      };
      """
    When the file is ingested
    Then the Function node for "Builder::build" has ref_qualifier equal to "&&"

  # negative — regular function has is_deleted=false, is_defaulted=false
  @S2-F.AC4 @S2-F.AC5 @negative @confirmed
  Scenario: SC-F-12 — Regular function has is_deleted and is_defaulted both false
    Given a C++ source file containing the declaration:
      """
      void normalFunction(int x);
      """
    When the file is ingested
    Then the Function node for "normalFunction" has is_deleted equal to false
    And the Function node for "normalFunction" has is_defaulted equal to false
```

---

### Feature: S2-G — Class Properties (S2-Scoped Subset)

```gherkin
Feature: Class node properties is_final, is_abstract, record_kind
  As a graph consumer
  I want is_final, is_abstract, and record_kind properties on Class nodes
  So that I can distinguish classes from structs/unions, find abstract bases, and identify sealed types

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # S2-G.AC1 — all required properties present on every Class node
  @S2-G.AC1 @confirmed
  Scenario: SC-G-01 — Every Class node has is_final, is_abstract, and record_kind properties
    Given a C++ source file containing the declaration:
      """
      class Simple {};
      """
    When the file is ingested
    Then the Class node for "Simple" has an "is_final" property of type bool
    And the Class node for "Simple" has an "is_abstract" property of type bool
    And the Class node for "Simple" has a "record_kind" property of type string

  # S2-G.AC2 — final class
  @S2-G.AC2 @confirmed
  Scenario: SC-G-02 — Class declared final has is_final equal to true
    Given a C++ source file containing the declaration:
      """
      class Sealed final {};
      """
    When the file is ingested
    Then the Class node for "Sealed" has is_final equal to true

  # S2-G.AC3 — abstract class (EC-11)
  @S2-G.AC3 @edge-case @confirmed
  Scenario: SC-G-03 — Class with at least one pure virtual method has is_abstract equal to true
    Given a C++ source file containing the class:
      """
      class IShape {
      public:
        virtual double area() = 0;
        virtual ~IShape() = default;
      };
      """
    When the file is ingested
    Then the Class node for "IShape" has is_abstract equal to true

  # S2-G.AC3 — non-abstract class
  @S2-G.AC3 @negative @confirmed
  Scenario: SC-G-04 — Class with no pure virtual methods has is_abstract equal to false
    Given a C++ source file containing the class:
      """
      class Concrete {
      public:
        int value();
      };
      """
    When the file is ingested
    Then the Class node for "Concrete" has is_abstract equal to false

  # S2-G.AC4, S2-G.AC5, S2-G.AC6 — record_kind values (Scenario Outline)
  @S2-G.AC4 @S2-G.AC5 @S2-G.AC6 @confirmed
  Scenario Outline: SC-G-05 — record_kind reflects the C++ keyword used in the declaration
    Given a C++ source file containing the declaration:
      """
      <keyword> <name> { int x; };
      """
    When the file is ingested
    Then the Class node for "<name>" has record_kind equal to "<expected_kind>"

    Examples:
      | keyword | name      | expected_kind |
      | class   | MyClass   | class         |
      | struct  | MyStruct  | struct        |
      | union   | MyUnion   | union         |

  # negative — non-final class
  @S2-G.AC2 @negative @confirmed
  Scenario: SC-G-06 — Class not declared final has is_final equal to false
    Given a C++ source file containing the declaration:
      """
      class Regular {};
      """
    When the file is ingested
    Then the Class node for "Regular" has is_final equal to false
```

---

### Feature: S2-H — describe_graph_schema Update and Backward Compatibility

```gherkin
Feature: describe_graph_schema reflects S2 additions and backward compatibility holds
  As a tool user
  I want describe_graph_schema to surface all S2 additions
  And I want existing graphs to load without error after S2 ships

  Background:
    Given S2 is fully implemented and the cpp-mcp server is running

  # S2-H.AC1 — new node types appear in schema
  @S2-H.AC1 @confirmed
  Scenario: SC-H-01 — describe_graph_schema lists Type and Parameter node types
    When describe_graph_schema is called
    Then the response includes node type "Type"
    And the response includes node type "Parameter"

  # S2-H.AC2 — new edge types appear in schema
  @S2-H.AC2 @confirmed
  Scenario: SC-H-02 — describe_graph_schema lists all five new edge types
    When describe_graph_schema is called
    Then the response includes edge type "RETURNS"
    And the response includes edge type "HAS_PARAM"
    And the response includes edge type "OF_TYPE"
    And the response includes edge type "POINTS_TO"
    And the response includes edge type "REFERS_TO"

  # S2-H.AC3 — schema_version stays "v2"
  @S2-H.AC3 @confirmed
  Scenario: SC-H-03 — describe_graph_schema reports schema_version equal to "v2"
    When describe_graph_schema is called
    Then the response contains schema_version equal to "v2"

  # S2-H.AC4 — v1 graph backward compat (EC-14)
  @S2-H.AC4 @backward-compat @edge-case @confirmed
  Scenario: SC-H-04 — Loading a v1 graph after S2 ships succeeds without error
    Given a graph exported before S1 (schema_version="v1") is connected
    When any read operation is performed (e.g., query_graphdb with a simple node count)
    Then the operation succeeds with no error
    And no crash or exception is raised

  # S2-H.AC5 — v2-from-S1 graph backward compat (EC-15)
  @S2-H.AC5 @backward-compat @edge-case @confirmed
  Scenario: SC-H-05 — Loading a v2-from-S1 graph (no Type/Parameter nodes) after S2 ships succeeds
    Given a graph exported after S1 but before S2 (schema_version="v2", no Type or Parameter nodes)
    When any read operation is performed
    Then the operation succeeds with no error
    And no crash or exception is raised when Type or Parameter nodes are absent

  # S2-H.AC6 — no regression on existing 1020-test suite
  @S2-H.AC6 @confirmed
  Scenario: SC-H-06 — Existing unit test suite passes without regression after S2 ships
    Given the full S1 unit test suite (1020 tests)
    When the suite is run against the S2 codebase
    Then all 1020 previously passing tests still pass
    And no previously passing test is now failing or erroring
```

---

### Feature: Failure Mode — Incomplete TU Produces No Partial Type Nodes

```gherkin
Feature: Failure mode — malformed TU does not produce partial Type state
  As a tool developer
  I want that a malformed or incomplete translation unit leaves no half-created Type nodes
  So that the graph remains consistent even when ingestion fails

  Background:
    Given a running cpp-mcp ingest_code tool connected to a clean graph backend

  # EC-16 — assumed (not explicit in AC; derived from general consistency requirement)
  @failure-mode @assumed
  Scenario: SC-FM-01 — Ingesting a malformed C++ file that fails to parse produces zero Type nodes
    # assumed: the exporter should be atomic per TU; if libclang produces fatal errors,
    # no Type or Parameter nodes from that TU should be partially committed.
    # Verify this with the developer; may need an explicit transactional guard.
    Given a C++ source file containing invalid syntax:
      """
      void foo( {  // missing closing paren — parse error
      """
    When the file is ingested
    Then the ingest_code tool returns an error or warning about parse failure
    And no Type node is created that references the malformed TU's types
    And no Parameter node is created that references the malformed TU's parameters
```

---

## References

- Handoff requirements: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements.md`
- Raw requirements: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/requirements-raw.md`
- CHARTER: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v8/CHARTER.md`
- Wiki PRD: `~/workspace/wiki/pages/planning/cpp-mcp-v7-full-ast-schema.md`
- Wiki S1 delta: `~/workspace/wiki/pages/code/cpp-mcp-v7-s1.md`
- Cognee tags: `task:cpp-mcp-v7-s2`, `role:business-analyst`
- ADR required before developer dispatch: ADR-26 (open questions 1, 2, 3 above)

## AC coverage index

| Story | ACs | Scenario IDs |
|-------|-----|--------------|
| S2-A | AC1, AC2, AC3, AC4 | SC-A-01..SC-A-09 |
| S2-B | AC1, AC2, AC3, AC4 | SC-B-01..SC-B-05 |
| S2-C | AC1, AC2, AC3, AC4, AC5 | SC-C-01..SC-C-10 |
| S2-D | AC1, AC2, AC3, AC4, AC5 | SC-D-01..SC-D-05 |
| S2-E | AC1, AC2, AC3, AC4 | SC-E-01..SC-E-05 |
| S2-F | AC1, AC2, AC3, AC4, AC5, AC6, AC7 | SC-F-01..SC-F-12 |
| S2-G | AC1, AC2, AC3, AC4, AC5, AC6 | SC-G-01..SC-G-06 |
| S2-H | AC1, AC2, AC3, AC4, AC5, AC6 | SC-H-01..SC-H-06 |
| Failure mode | — (assumed) | SC-FM-01 |
