# ADR-2: Error envelope delivery — return dict from wrapped tool; FastMCP serialises as structuredContent

Status: accepted
Context:
  - OQ-2: For each of the 7 tools, the error envelope `{code, message, tool, request_id}` (ADR-8 from v1) must reach the MCP client unchanged on every failure path (US-M5/AC-1..AC-5; C-4).
  - FastMCP's default error path is `raise ToolError(...)`, which produces a different wire shape (`isError: true`, content as text) and would break C-4.
  - Three candidate mechanisms exist: (a) return the envelope as a plain `dict` from the wrapped function; (b) return `ToolResult(structured_content={...})` explicitly; (c) introduce custom middleware that catches a sentinel exception and rewrites the response.

Decision:
  - The existing `core.error_envelope.wrap_tool` decorator stays on every tool function and is the outermost decorator on the function definition. `@mcp.tool` registers the already-wrapped function.
  - On both the success and failure paths, the wrapped function returns a plain Python `dict`. FastMCP's automatic structured-output handling serialises this `dict` into the MCP tool result as `structuredContent` AND mirrors it as a JSON text block in `content[]` (per FastMCP servers wiki, return-types section).
  - No exception is allowed to escape `wrap_tool`. Internal libclang / I/O exceptions are caught inside `wrap_tool` and converted to the envelope's `INTERNAL_ERROR` (or specific code) form. `ToolError` is NOT raised.
  - `mask_error_details=True` is set on the `FastMCP(...)` constructor as defense-in-depth (US-M5/AC-4) for the EC-3 path where a bug bypasses `wrap_tool`. With the dict-return path as primary, mask_error_details is exercised only on bug paths.

Alternatives considered:
  - `ToolResult(structured_content={...})` explicit wrapping: rejected — adds a FastMCP-typed return at every tool, defeating the point of decorating existing functions; equivalent wire shape to plain dict return per wiki.
  - Custom middleware catching a `WrappedToolError` sentinel: rejected — adds a hook surface that has no other consumer; out-of-scope per OQ-7 (no middleware in v2); harder to reason about than direct return.
  - Raise `ToolError(envelope_json)`: rejected — `ToolError` strips structured content, leaving only a text message; agents parsing `code`/`tool` fields would break (C-4 violation).

Consequences:
  - Positive: zero change to `core/error_envelope.py` logic; `wrap_tool` continues to own the envelope contract; `mask_error_details=True` covers escape paths.
  - Positive: BDD step files asserting `response.structuredContent.code == "PATH_VIOLATION"` map directly to FastMCP's serialised dict.
  - Negative: tool return type annotations widen to `dict[str, Any]`; mypy strictness preserved via a `TypedDict` (`ToolEnvelope`) defined in `core.error_envelope`.
  - Follow-up: senior-developer captures the `TypedDict` design in plan.md; QA scenario SC_USM5_5 asserts envelope reaches the client as a tool result, not a JSON-RPC error.

References:
  - C-4; US-M5 (all AC); EC-3
  - `[[pages/manuals/fastmcp/servers]]` §Tools — return types
  - v1/adr-8.md (error envelope)
  - src/cpp_mcp/core/error_envelope.py
