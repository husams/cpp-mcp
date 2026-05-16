# ADR-9 (logical ADR-11): FastMCP supersedes the official MCP Python SDK transport decision (supersedes v1 ADR-10)

Status: accepted
Supersedes: ADR-10 (v1)

Context:
  - v1 ADR-10 chose the official Anthropic MCP Python SDK (`mcp` package) for tool registration and JSON-RPC framing, with stdio + HTTP loopback transports and no auth.
  - v1 ADR-10's HTTP transport was implemented only as a stub (`http_transport.py`); v1 US-14/AC-2 remained an open P1 gap.
  - The FastMCP framework (`fastmcp~=3.1.0`) provides equivalent functionality plus:
    - Decorator-driven tool registration (US-M3).
    - Auto-generated JSON Schemas from Python type hints (US-M4).
    - Production-quality Streamable HTTP transport with `mcp.run(transport="http", ...)` (US-M2).
    - Lifespan context managers for resource lifecycle (US-M6).
    - Built-in `mask_error_details`, `Depends`, custom HTTP routes, and middleware hooks.
  - Adoption is supported by extensive wiki documentation: `[[pages/manuals/fastmcp/getting-started]]`, `[[pages/manuals/fastmcp/servers]]`, `[[pages/manuals/fastmcp/cli]]`, `[[pages/manuals/fastmcp/python-sdk-reference]]`.

Decision:
  - Replace the `mcp` Python SDK with `fastmcp~=3.1.0` as the protocol library for cpp-mcp (pinning detailed in ADR-related work for US-M8; CHARTER constraint).
  - Stdio entrypoint: FastMCP `mcp.run()` (see ADR-4).
  - HTTP transport: FastMCP `mcp.run(transport="http", ...)` at default path `/mcp`, with `GET /health` via `@mcp.custom_route` (see ADR-5). Closes v1 US-14/AC-2.
  - Tool registration: `@mcp.tool` decorators; `_TOOL_SPECS`/`_HANDLERS` glue removed (see US-M3).
  - Schemas: FastMCP-generated, verified against frozen v1 schemas (see ADR-6).
  - Error envelope: preserved via `wrap_tool` + dict return (see ADR-2); `mask_error_details=True` defense-in-depth.
  - DI: `Depends(get_session)` etc. (see ADR-3).
  - Lifespan: owns `ClangSession`; sync handlers dispatch via executor (see ADR-7).
  - Auth: still NONE in v2; defer per US-M2/AC-5 and v1 ADR-10 carry-over.
  - This ADR is referenced as "ADR-11" project-wide; file stored as `v2/adr-9.md` per CHARTER blackboard contract (see ADR-1).

Alternatives considered:
  - Stay on the official `mcp` SDK and implement HTTP from scratch using FastAPI (v1 ADR-10 plan): rejected — duplicates work that FastMCP provides as `mcp.run(transport="http")`; would carry forward 150 lines of hand-rolled JSON-RPC glue (`_TOOL_SPECS`/`_HANDLERS`); leaves hand-maintained schemas as a permanent drift risk.
  - Use FastMCP only for HTTP, keep `mcp` SDK for stdio: rejected — two protocol libraries means two error paths, two lifespan models, two schema generators; the migration cost is the same as a full switch but the maintenance cost is doubled.
  - Defer FastMCP adoption to v3 and ship the HTTP stub: rejected — leaves US-14/AC-2 unmet and locks in the maintenance debt of v1 ADR-10's `_TOOL_SPECS`.

Consequences:
  - Positive: ~300 lines of hand-rolled glue removed (schemas.py 143 + _TOOL_SPECS/_HANDLERS ~150); HTTP transport actually works; schema drift impossible after parity test (ADR-6).
  - Positive: future features (auth via `JWTVerifier`, observability middleware) become opt-in additions, not net-new infrastructure.
  - Negative: FastMCP semver explicitly allows protocol-breaking changes in minor versions — mitigated by exact-pin `fastmcp~=3.1.0` and committed `uv.lock` (US-M8); manual upgrade checklist documented in runbook.
  - Negative: install footprint grows (FastMCP brings Starlette, anyio, httpx). Mitigation: audit `uv tree` post-migration; document in runbook.md (R-8).
  - Follow-up: doc-writer updates v1 ADR-10 `Status:` to `superseded by ADR-11` (per ADR-1) and updates `[[pages/code/cpp-mcp]]` ADR table.

References:
  - v1/adr-10.md (superseded)
  - US-M1..US-M9 (all stories in this migration)
  - `[[pages/manuals/fastmcp/getting-started]]`
  - `[[pages/manuals/fastmcp/servers]]`
  - `[[pages/manuals/fastmcp/cli]]`
  - `[[pages/code/cpp-mcp]]`
