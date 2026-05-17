# ADR-20: Source-file rename scope under v5 (OQ-2)

Status: accepted
Context:
- Six of seven tool source files are already named without the `cpp_` prefix (`src/cpp_mcp/tools/get_ast.py`, `get_definition.py`, `get_references.py`, `get_type_info.py`, `get_header_info.py`, `get_preprocessor_state.py`). Only `export_to_graphdb.py` mismatches the new wire name `ingest_code`.
- AC-R1-2 mandates the Python symbol renames; OQ-2 asked whether the file path also renames.

Decision:
- Rename exactly one source file: `src/cpp_mcp/tools/export_to_graphdb.py` → `src/cpp_mcp/tools/ingest_code.py`.
- Rename the matching BDD test files per AC-R2-2 (`test_export_to_graphdb.py` → `test_ingest_code.py`; `test_export_to_indradb.py` → `test_ingest_code_indradb.py`).
- The other six tool source files already match their new wire names — no file rename required.
- Use `git mv` (not delete + create) to preserve history.

Alternatives considered:
- Keep `export_to_graphdb.py` as the filename and only rename the symbol — rejected: partial rename is observable in tracebacks, import paths, and code search; violates the "no half-renamed surface" NFR.
- Add a shim re-export at the old path — rejected: AC-R4-3 forbids compatibility aliases.

Consequences:
- Positive: single source of truth; import path matches wire name and symbol name.
- Negative: any external import of `cpp_mcp.tools.export_to_graphdb` breaks. Acceptable per AC-R4-3 (clean break, no known external integrators).
- Follow-up: update `src/cpp_mcp/tools/__init__.py` and the server registration site to import from the new module path.

References: requirements.md OQ-2, AC-R1-2, AC-R2-2, AC-R4-3.
