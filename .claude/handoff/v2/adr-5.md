# ADR-5: HTTP transport endpoint path — FastMCP default `/mcp`; `GET /health` via `@mcp.custom_route`

Status: accepted
Context:
  - OQ-5: Should the HTTP transport serve at FastMCP's default `/mcp` path, or preserve v1 ADR-10's `/mcp` literal? (These coincide — the question is whether to rely on the default or pin the path explicitly.)
  - US-M2/AC-1 requires the server to accept MCP requests "at the FastMCP-default HTTP path on port 8765".
  - US-M2/AC-4 requires `GET /health` returning `200 OK` plain text via `@mcp.custom_route("/health", methods=["GET"])`.

Decision:
  - Use FastMCP's default HTTP path `/mcp`. Do not override via constructor kwargs.
  - `GET /health` is implemented exactly per the wiki example:
    ```python
    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")
    ```
  - v1 ADR-10's stub `GET /healthz` (which returned cache stats) is NOT carried forward. The v2 `/health` is plain text "OK" per US-M2/AC-4; cache stats are not exposed in this story.
  - Non-loopback bind warning (US-M2/AC-3, EC-2): a startup check inspects `CPP_MCP_HTTP_BIND`; values not in `{"127.0.0.1", "::1", "localhost"}` produce a single WARNING log line on stderr before `mcp.run()` is called. IPv6 `::` is treated as non-loopback (matches EC-2 needs-clarification: confirmed non-loopback).

Alternatives considered:
  - Custom path `/cpp-mcp` or `/v2/mcp`: rejected — breaks expectations of MCP-over-HTTP tooling that defaults to `/mcp`; v1 ADR-10 already used `/mcp`; no operator-stated reason to change.
  - Keep `/healthz` returning JSON cache stats (v1 stub behaviour): rejected — US-M2/AC-4 explicitly specifies plain-text `OK` at `/health`; richer observability deferred per OQ-7.

Consequences:
  - Positive: zero divergence from FastMCP defaults; existing v1 ADR-10 deploy guidance carries over (`POST /mcp` JSON-RPC).
  - Negative: cache-stats endpoint regression vs v1 ADR-10 stub. Mitigation: a follow-up v3 story can add `/healthz` with stats; documented in deploy-notes by the devops stage.
  - Follow-up: devops stage updates `deploy-notes.md` to point operators at `GET /health` for liveness.

References:
  - US-M2/AC-1, AC-3, AC-4; EC-2
  - v1/adr-10.md (path lineage)
  - `[[pages/manuals/fastmcp/servers]]` §Custom HTTP Routes
