# ADR-8: Observability middleware deferred to v3; FastMCP middleware not introduced in this migration

Status: accepted
Context:
  - OQ-7: Introduce FastMCP middleware (`LoggingMiddleware`, `TimingMiddleware`, etc.) for observability now, or defer to a v3 story?
  - Requirements explicitly scope observability middleware out of v2 (see scenarios.md §Out-of-Scope, line "Middleware (LoggingMiddleware, TimingMiddleware) — deferred per OQ-7").

Decision:
  - Defer all FastMCP middleware to a future v3 story. No `LoggingMiddleware`, `TimingMiddleware`, `StructuredLoggingMiddleware`, `ResponseCachingMiddleware`, `RateLimitingMiddleware`, or `ErrorHandlingMiddleware` is added in this migration.
  - Existing logging via `logging.basicConfig(..., stream=sys.stderr)` is preserved; FastMCP's internal logger is configured to stderr at `INFO` to match v1 (C-9).
  - When a v3 story introduces middleware, the entry point is `mcp.add_middleware(instance)` or `middleware=[...]` on the constructor; the wiki page `[[pages/manuals/fastmcp/servers]]` §Middleware documents the hook hierarchy and built-ins.

Alternatives considered:
  - Add `TimingMiddleware` now: rejected — net new code path with no AC demanding it; risks interaction with `wrap_tool` ordering and complicates the migration's scope.
  - Add `LoggingMiddleware` to replace `wrap_tool`-side logging: rejected — `wrap_tool` already emits structured log lines; replacing with FastMCP middleware would touch a stable subsystem outside this migration.

Consequences:
  - Positive: smallest-possible diff against v1's observability surface; lower regression risk.
  - Negative: no per-tool timing histograms or rate-limit guards in v2. Operators relying on those for production HTTP exposure must wait for v3.
  - Follow-up: file a v3 story (`US-M10` future) titled "FastMCP observability middleware" referencing this ADR.

References:
  - scenarios.md §Out-of-Scope
  - `[[pages/manuals/fastmcp/servers]]` §Middleware
