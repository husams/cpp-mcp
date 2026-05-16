# ADR-7: Lifespan owns ClangSession; sync handlers dispatch through `ClangSession.executor.submit().result()`

Status: accepted
Context:
  - OQ-9: Architect to confirm sync `def` + `ClangSession.executor.submit(...).result()` pattern for libclang thread-affinity (US-M7/AC-1..AC-4).
  - US-M6 requires the `ClangSession` and TU LRU cache to live in a FastMCP `lifespan` context manager, with `session.close()` called on teardown.
  - Risk R-3 / R-5: libclang `Index` is non-reentrant; concurrent FastMCP requests must not hit `clang.cindex` in parallel.

Decision:
  - **Lifespan structure.** A single `app_lifespan(server)` `@asynccontextmanager` is attached to `FastMCP(..., lifespan=app_lifespan)`. It:
    1. Reads and validates env (raises `ConfigError` on missing `CPP_MCP_ALLOWED_ROOTS` or unloadable libclang — surfaces at the `main()` boundary per ADR-4).
    2. Constructs `ClangSession(capacity=config.cache_capacity)`.
    3. Yields `AppLifespanContext` dict: `{"session": session, "allowed_roots": ..., "default_flags": ..., "ast_max_nodes": ..., "ast_max_bytes": ...}`.
    4. On teardown calls `await session.aclose()` (new async method) which: (a) waits for any in-flight executor task to finish (`executor.shutdown(wait=True)`), (b) clears the TU cache.
  - **Session typing.** Add `AppLifespanContext` `TypedDict` in `core/deps.py` (see ADR-3). Lifespan annotated to yield `AppLifespanContext`.
  - **Handler convention.** All 7 tool handlers are `def` (sync). They obtain `session: ClangSession = Depends(get_session)` (ADR-3) and dispatch libclang calls as:
    ```python
    @mcp.tool(name="cpp_get_definition")
    @wrap_tool(name="cpp_get_definition")
    def cpp_get_definition(
        file_path: str,
        line: int,
        column: int,
        *,
        session: ClangSession = Depends(get_session),
        allowed_roots: tuple[Path, ...] = Depends(get_allowed_roots),
        ...
    ) -> dict[str, Any]:
        ...
        return session.executor.submit(_do_get_definition, ...).result()
    ```
  - **Why sync def + submit().result().** FastMCP runs sync handlers via `anyio.to_thread.run_sync` on its worker pool. Submitting to the single-worker `ClangSession.executor` and blocking on `.result()` forces all libclang work onto exactly one OS thread, regardless of how many FastMCP workers run in parallel. The handler's outer thread (FastMCP's anyio worker) blocks waiting for the libclang worker — this is intentional: FastMCP's pool is the request boundary; `ClangSession.executor` is the libclang serializer. The two thread hops are the cost of preserving ADR-2's non-reentrancy invariant against concurrent MCP requests.
  - **Async-def alternative discarded.** `async def` handlers calling `asyncio.get_running_loop().run_in_executor(session.executor, ...)` would also serialize libclang, but introduces an unnecessary asyncio frame around code that has no other await points. The wiki recommends sync handlers for blocking C APIs (`run_in_thread=True` auto-detect).

Alternatives considered:
  - `async def` handlers + `run_in_executor(session.executor, ...)`: rejected — equivalent correctness, more boilerplate, no benefit for a non-async libclang.
  - Per-tool `ThreadPoolExecutor`s: rejected — violates ADR-2 (single Index, single thread).
  - Drop the executor and use a `threading.Lock` around `clang.cindex` calls on FastMCP's worker thread: rejected — works for the lock, but libclang's `Index` is also thread-affinity-sensitive in some configurations; the single-worker executor is the proven v1 pattern (C-8).

Consequences:
  - Positive: ADR-2 invariant preserved end-to-end; concurrent-request regression test (SC_USM7_3) succeeds with `parse_count == 1` on cache hits; clean shutdown via `executor.shutdown(wait=True)`.
  - Positive: handler bodies read top-to-bottom like procedural code — easier to maintain than async-def + run_in_executor.
  - Negative: per-request latency includes a thread-hop into `session.executor`; v1 already paid this cost so no regression.
  - Follow-up: developer adds `ClangSession.aclose()`; QA's R-3 regression scenario (SC_USM7_3) launches 3 concurrent HTTP `cpp_get_ast` calls and asserts parse_count == 1.

References:
  - US-M6, US-M7 (all AC); EC-11, EC-12, EC-13
  - C-8; R-3; R-5; v1/adr-2.md
  - `[[pages/manuals/fastmcp/servers]]` §Lifespan, §Tools (run_in_thread)
