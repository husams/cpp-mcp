# ADR-4: Stdio entrypoint — synchronous `mcp.run()`; `main()` catches ConfigError and KeyboardInterrupt

Status: accepted
Context:
  - OQ-4 and OQ-8 (duplicate): Should `main()` call `asyncio.run(_run_stdio())` (v1 pattern) or FastMCP's synchronous `mcp.run()` which manages the event loop internally?
  - Affects exit-code behaviour on `ConfigError` (US-M1/AC-5, US-M6/AC-5) and `KeyboardInterrupt`.
  - Note: OQ-4 and OQ-8 are the same question with slightly different phrasing; both resolve here.

Decision:
  - Use FastMCP's synchronous `mcp.run(transport=...)` from inside `main()`. `mcp.run()` internally manages the asyncio event loop and runs the lifespan exactly once.
  - `main()` signature stays `def main() -> int`. Structure:
    ```python
    def main() -> int:
        try:
            mcp = build_server()                # constructs FastMCP, registers tools, attaches lifespan
            transport = os.environ.get("CPP_MCP_TRANSPORT", "stdio")
            if transport == "http":
                mcp.run(transport="http",
                        host=config.http_bind,
                        port=config.http_port)
            else:
                mcp.run()                        # default stdio
            return 0
        except ConfigError as exc:
            print(_sanitize_message(str(exc)), file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return 0
    ```
  - `ConfigError` may be raised by `build_server()` itself (env-var validation) or by the lifespan (during `mcp.run()` startup). Both surface to the `except ConfigError` boundary.
  - Stdio EOF: FastMCP's stdio transport exits the run loop cleanly on stdin close, returning normally from `mcp.run()`; `main()` returns 0.

Alternatives considered:
  - `asyncio.run(_run_stdio())` keeping v1 hand-rolled wrapper: rejected — duplicates FastMCP's loop management; complicates lifespan composition (would need manual lifespan entry/exit); no benefit.
  - `anyio.run(mcp.run_async)` for portability: rejected — FastMCP's sync `run()` already invokes anyio internally; no portability gain.

Consequences:
  - Positive: simplest possible `main()`; lifespan invoked exactly once (satisfies US-M6/AC-4 / EC-13); ConfigError catch boundary is unambiguous.
  - Negative: lifespan exceptions surface from inside `mcp.run()` rather than at an explicit await point; debugging requires reading FastMCP's tracebacks. Mitigated by `_sanitize_message` and by structured logging on stderr.
  - Follow-up: developer ensures `build_server()` does no I/O (only constructs the FastMCP and attaches the lifespan); all I/O happens in the lifespan body.

References:
  - US-M1/AC-5; US-M6/AC-4, AC-5; C-5; C-10
  - `[[pages/manuals/fastmcp/servers]]` §Server Class — `mcp.run()`
  - ADR-7 (lifespan)
