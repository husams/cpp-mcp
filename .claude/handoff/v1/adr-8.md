# ADR-8: Error envelope — fixed shape, fixed code set, partial success NOT in envelope
Status: accepted
Context:
  - US-13/AC-1 requires `{code, message, tool, request_id}`.
  - OQ-16: partial-success cases (US-4/AC-7 partial AST, US-7/AC-5 per-file failures) need a representation.
  - Agents need to write conditional logic against a closed enum of error codes.

Decision:
  - Wire shape (exact):
    ```json
    { "code": "<UPPER_SNAKE_CODE>",
      "message": "<human readable, caller-safe>",
      "tool": "<tool_name>",
      "request_id": "<uuid4>" }
    ```
  - Closed enum: `FILE_NOT_FOUND, INVALID_POSITION, INVALID_RANGE, INVALID_ARGUMENT, PATH_VIOLATION, DB_UNREACHABLE, PARSE_ERROR, INTERNAL_ERROR`. No tool emits a code outside this set; new codes require an ADR superseding this one.
  - `message` discipline: contains only (a) static strings, (b) caller-provided values echoed back, (c) error codes themselves. Never Python tracebacks, server-internal absolute paths, libclang library paths, or environment values. Enforced by `error_envelope.build_error()` running the message through an allowlist filter.
  - `request_id`: server-generated uuid4 per inbound request; logged at INFO so operators can correlate.
  - **Partial success uses the success payload, not the envelope:**
    - `cpp_get_ast` partial parse: success result with `parse_errors: [{severity, message, file, line, col}, ...]`.
    - `cpp_export_to_graphdb` per-file failure: success result with `errors: [{file, code, message}, ...]`.
    The envelope is reserved for "the whole call failed; no useful result available."
  - Implementation: `error_envelope.wrap_tool(tool_name)` is a decorator applied to every registered tool callable. It catches:
    - `PathViolation` → `PATH_VIOLATION`
    - `FileNotFoundError` (post-validation) → `FILE_NOT_FOUND`
    - `InvalidPosition`/`InvalidRange`/`InvalidArgument` → matching code
    - `DBUnreachable` → `DB_UNREACHABLE`
    - `FatalParseError` (raised only when libclang returns zero nodes + fatal diagnostics) → `PARSE_ERROR`
    - any other `Exception` → `INTERNAL_ERROR` (logged in full at ERROR; sanitized in response)

Alternatives considered:
  - Open-ended error code strings: rejected — agents need an enum to branch on.
  - Errors as JSON-RPC errors (using JSON-RPC error field instead of result): rejected — MCP SDK convention varies; embedding the envelope in the result keeps tool behavior uniform across transports.
  - Single `warnings: []` field at the top of every response (success and error alike): rejected — adds noise to the 95% case where there are no warnings.

Consequences:
  - Positive: agents have a small, closed grammar to handle; logging/correlation by request_id is straightforward.
  - Negative: adding a new error code is an ADR-level change (intentional friction; the contract should not drift).
  - Follow-up: emit a `version` field in every response in v1.1 so future envelope changes are observable.

References:
  - requirements.md US-13 (all AC), OQ-16
  - design.md §4
