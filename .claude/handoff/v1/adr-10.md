# ADR-10: Transport — official MCP Python SDK; stdio + HTTP loopback only; no auth v1
Status: accepted
Context:
  - US-14 requires both stdio (P0) and HTTP (P1) transports with identical tool surface.
  - OQ-17: should HTTP transport require authentication in v1?
  - Charter scope explicitly excludes auth and multi-tenant access; v1 is "local only".

Decision:
  - Use the official Anthropic **MCP Python SDK** (`mcp` package on PyPI) for tool registration and JSON-RPC framing. Do not hand-roll JSON-RPC.
  - **Stdio transport:** entry point `python -m cpp_mcp` (default), uses `mcp.server.stdio.stdio_server()` async context.
  - **HTTP transport:** `python -m cpp_mcp --transport http --port 8765`. Implemented with FastAPI:
    - `POST /mcp` — JSON-RPC payload, returns JSON-RPC response.
    - `GET /healthz` — returns `{status:"ok", cache_size, cache_capacity, cache_hit_rate, version}`.
  - **Bind address:** `127.0.0.1` only by default. If `CPP_MCP_HTTP_BIND` is set to anything other than `127.0.0.1` or `::1`, the server logs a WARN and prints to stderr: `"HTTP bound to non-loopback address without auth; do not expose to untrusted networks"`. The server still starts (operators may use Tailscale or equivalent).
  - **Authentication in v1:** NONE. Rationale:
    - Local-only scope; loopback bind is the security boundary.
    - Adding auth (API key, bearer) without operationalizing rotation/storage would be theater.
    - Operators wanting auth in v1 can front the server with a reverse proxy (Caddy, Nginx) that adds auth — the server-side contract stays simple.

Alternatives considered:
  - Hand-rolled JSON-RPC: rejected — MCP SDK exists, handles spec edge cases.
  - Require API key on HTTP from day 1: rejected — adds key-management surface (storage, rotation, revocation) that has no home in v1. Local-loopback is enough.
  - Defer HTTP transport entirely to v2: rejected — US-14 marks HTTP as P1 and remote-agent use is a stated use case.
  - Listen on Unix domain socket instead of TCP: considered; deferred. TCP loopback is simpler for agents that expect HTTP URLs. Re-evaluate if the auth question reopens.

Consequences:
  - Positive: minimal scope, single SDK dependency, identical tool surface across transports.
  - Negative: operators exposing the HTTP transport on a routable interface must layer their own auth. Documented prominently in deploy-notes.
  - Follow-up: if v2 demands multi-tenant HTTP, design auth (bearer + tenant-scoped allowed-roots) in a fresh ADR.

References:
  - requirements.md US-14 (all AC), OQ-17
  - scenarios.md SC-US-14-1..4
  - design.md §5 (transport), §6 (config)
  - MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
