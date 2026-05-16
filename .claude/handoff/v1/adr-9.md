# ADR-9: Argument and parse-error semantics for build_path and compile_commands.json
Status: accepted
Context:
  - OQ-NEW-1 (BA): `build_path` is an existing **file** (not a directory). Should this be `INVALID_ARGUMENT` or `PATH_VIOLATION`?
  - OQ-NEW-2 (BA): When is `PARSE_ERROR` emitted vs partial AST with `parse_errors[]`? And what happens with a malformed `compile_commands.json`?
  - Existing AC: US-1/AC-7 says missing `compile_commands.json` is a silent fallback (not an error). US-4/AC-7 says partial parse returns partial AST + warnings.

Decision:

### OQ-NEW-1 — `build_path` is a file
- Treat as `INVALID_ARGUMENT`. The path passes the path-guard (it's inside an allowed root and not a traversal), so `PATH_VIOLATION` would be semantically wrong — the input is well-formed and safe, it's just the wrong **type** of filesystem object for this parameter.
- Message: `"build_path must be a directory; got a regular file"`.

### OQ-NEW-2 — `PARSE_ERROR` semantics
Two distinct conditions, two distinct outcomes:

1. **Malformed `compile_commands.json`** (`CompilationDatabaseError` from libclang, JSON syntax error, missing required fields):
   - **Silent fallback** to `default_flags`, response `flags_source="default"`.
   - Rationale: this matches US-1/AC-7 (missing `compile_commands.json` falls back silently); a malformed file is operationally similar — the build context is unavailable. Forcing an error here would block agents from inspecting files in repos with broken build databases.
   - We log a WARN-level server log entry so operators can spot it.

2. **Libclang produces zero AST nodes for `file_path`** (TU completely unparseable — corrupted file, fundamental syntax meltdown, encoding issue):
   - Emit `{code: "PARSE_ERROR", message, tool, request_id}`. This is the only condition that triggers `PARSE_ERROR`.
   - Threshold: TU is created but `tu.cursor.walk_preorder()` yields zero declarations AND libclang diagnostics contain at least one `CXDiagnostic_Fatal` (severity 4).
   - Any partial AST (≥1 node OR no fatal diagnostics, only warnings/errors) → success path with `parse_errors[]` (US-4/AC-7).

Alternatives considered:
- OQ-NEW-1 alt: `PATH_VIOLATION` for file-typed build_path: rejected — the path is inside the allowed root and not a traversal; conflating "wrong type" with "security violation" weakens the security signal and confuses agents.
- OQ-NEW-2 alt A: malformed compile_commands.json → `PARSE_ERROR`: rejected — inconsistent with US-1/AC-7 (missing file = silent fallback). Agents would have to special-case build-system breakage.
- OQ-NEW-2 alt B: `PARSE_ERROR` whenever any error-severity diagnostic appears: rejected — too aggressive; templated C++ routinely produces errors that libclang recovers from with usable AST.

Consequences:
- Positive: clear, testable thresholds. BDD scenarios SC-US-1-13, SC-US-4-11, SC-US-4-12 become deterministic.
- Negative: `PARSE_ERROR` will be rare; if it fires, agent should fall back to grep/AST-free analysis.
- Follow-up: track frequency of WARN-level "malformed compile_commands.json" log to surface broken repos.

References:
- requirements.md US-1/AC-7, US-4/AC-7, US-13/AC-3
- scenarios.md OQ-NEW-1, OQ-NEW-2, SC-US-1-13, SC-US-4-11, SC-US-4-12
- design.md §4
