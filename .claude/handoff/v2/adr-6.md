# ADR-6: Frozen schema fixtures — move to `tests/fixtures/expected_schemas/`, delete `server/schemas.py`

Status: accepted
Context:
  - OQ-6: After FastMCP generates `inputSchema` from type hints, should `server/schemas.py` (143 lines of hand-maintained dicts) remain as a frozen-fixture file, move to `tests/fixtures/expected_schemas/`, or be deleted outright?
  - US-M4/AC-1 allows either deletion or relocation under `tests/fixtures/expected_schemas/`.
  - US-M4/AC-3 mandates a parity test `tests/unit/test_schema_parity.py` that loads frozen v1 schemas and compares against live FastMCP-generated schemas.

Decision:
  - Move the seven `CPP_*_SCHEMA` dicts from `src/cpp_mcp/server/schemas.py` to `tests/fixtures/expected_schemas/__init__.py` (or one file per tool, developer's choice). Delete `src/cpp_mcp/server/schemas.py`.
  - The fixtures are immutable after migration — they record the v1 wire contract. A schema change in production code is allowed only by an ADR-level decision; the parity test fails loudly otherwise.
  - `tests/unit/test_schema_parity.py`:
    - Loads each of the 7 frozen dicts.
    - Instantiates the live FastMCP server (no transport — direct `FastMCP` instance), reads each generated `inputSchema` via `mcp._tool_manager.get_tools()` or the public client-side `tools/list`.
    - Normalises both before comparison: collapse `["string","null"]` ↔ `{"type":"string","nullable":true}` (and Pydantic's `anyOf`/`null`); inline `$defs`/`$ref`; ignore `title` and `description` text differences except where US-M4/AC-4 requires a non-empty description.
    - Asserts: identical `required` set, identical property name set, identical property types post-normalisation, identical enum values for `format`, identical defaults, `additionalProperties: false` on every schema.
    - Fails with a clear diff showing the offending tool + property.

Alternatives considered:
  - Keep `server/schemas.py` in `src/` as a "frozen fixture": rejected — co-locating expectations with production code blurs the line; production code may inadvertently import the dicts again, defeating US-M3's removal of `_TOOL_SPECS`.
  - Delete schemas entirely (no parity test): rejected — US-M4/AC-3 mandates the parity test; without frozen fixtures there is nothing to compare against.

Consequences:
  - Positive: production `src/` shrinks by 143 lines; the v1 schema becomes a versioned test fixture with clear semantics; client-breaking schema drift fails CI.
  - Negative: introducing a new test directory `tests/fixtures/expected_schemas/`; developer must wire `additionalProperties: false` into every Pydantic model used as a tool argument (FastMCP defaults to `True`; see EC-7) — handled in ADR-8 (Pydantic config).
  - Follow-up: senior-developer plans the test-schema-parity.py file in plan.md; QA verifies SC_USM4_1..6.

References:
  - US-M4 (all AC); EC-7, EC-8, EC-14
  - C-2
  - `src/cpp_mcp/server/schemas.py` (v1)
