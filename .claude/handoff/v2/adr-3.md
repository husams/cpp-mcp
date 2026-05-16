# ADR-3: Tool dependency injection via FastMCP `Depends(get_session)` + lifespan context

Status: accepted
Context:
  - OQ-3: Tool handlers need access to `session: ClangSession`, `allowed_roots`, `default_flags`, `ast_max_nodes`, `ast_max_bytes`. These MUST NOT appear in the MCP `inputSchema` (US-M3/AC-4, EC-6).
  - Three candidates: (a) FastMCP `Depends(callable)` resolver, (b) `ctx.lifespan_context["session"]` lookup inside handler bodies, (c) closure capture inside a factory function that returns the decorated tools.

Decision:
  - Use FastMCP `Depends(callable)` as the canonical injection mechanism for `session`, `allowed_roots`, `default_flags`, `ast_max_nodes`, `ast_max_bytes`. The wiki (`[[pages/manuals/fastmcp/servers]]` §Dependency Injection) is explicit: "DI parameters are excluded from the MCP schema — clients never see them" and "Dependencies are cached per-request".
  - Provide a small `core/deps.py` module exposing:
    - `def get_session() -> ClangSession` → returns `get_context().lifespan_context["session"]`.
    - `def get_allowed_roots() -> tuple[Path, ...]` → returns `get_context().lifespan_context["allowed_roots"]`.
    - `def get_default_flags() -> tuple[str, ...]`, `get_ast_limits() -> AstLimits`.
  - The lifespan (see ADR-7) yields a `dict` with keys `session`, `allowed_roots`, `default_flags`, `ast_max_nodes`, `ast_max_bytes`. Resolvers read from there via `fastmcp.server.dependencies.get_context()`.

Alternatives considered:
  - Direct `ctx.lifespan_context["session"]` in handler bodies: rejected — couples every handler to `Context` typing and lifespan-dict keys; harder to test in isolation; wiki recommends `Depends` for shared dependencies.
  - Closure capture via factory: rejected — forces tool functions to be defined inside a factory, breaking module-level decorator usage; complicates mypy --strict typing.
  - Module-level globals (current v1 pattern): rejected — US-M6/AC-3 forbids module-level `ClangSession` access.

Consequences:
  - Positive: handler signatures stay flat and clients see only the public arguments. EC-6 (DI params in inputSchema) is structurally impossible.
  - Positive: per-request caching of `Depends` means a single tool invocation that calls helpers via `get_context()` shares the same `ClangSession` instance.
  - Negative: `core/deps.py` is a new module; mypy --strict must type the `lifespan_context` dict — use a `TypedDict` (`AppLifespanContext`).
  - Follow-up: developer adds `core/deps.py` and `AppLifespanContext` TypedDict; QA verifies SC_USM3_4.

References:
  - US-M3/AC-4; EC-6
  - `[[pages/manuals/fastmcp/servers]]` §Dependency Injection
  - ADR-7 (lifespan)
