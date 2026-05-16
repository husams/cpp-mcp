# ADR-2: Concurrency model — single libclang worker thread behind asyncio
Status: accepted
Context:
  - OQ-11: HTTP transport may receive concurrent requests; libclang's `Index` is not safe for concurrent `parse()` calls from multiple Python threads (documented behavior; reentrancy issues with the C++ Index/TU state).
  - GIL plus libclang's CPython binding does not protect concurrent libclang internal mutation; segfaults observed in field reports.
  - stdio transport is serial by JSON-RPC framing — no concurrency issue there.
  - We still want HTTP to accept multiple in-flight requests (health check, cache-stats endpoint) without blocking on a long parse.

Decision:
  - Single shared `clang.cindex.Index` instance owned by `core/clang_session.py`.
  - All `parse()` calls are dispatched to a `concurrent.futures.ThreadPoolExecutor(max_workers=1)` — exactly one libclang parse runs at a time, process-wide.
  - HTTP handlers are `async def`; the dispatch into the executor is `await loop.run_in_executor(executor, ...)` so the event loop stays free to serve healthz/stats concurrently.
  - TU cache mutations are guarded by a `threading.Lock` (lookups are fast; contention is negligible).

Alternatives considered:
  - Multi-worker thread pool with per-thread `Index`: rejected — separate Index instances cannot share TUs, defeats the cache. Memory cost N× per worker.
  - `multiprocessing.Pool` for true parallelism: rejected for v1 — IPC overhead per call, cache must be shared (would need shm), and v1 has no documented throughput requirement.
  - Pure async (no executor): rejected — libclang is blocking C code; would freeze the event loop.

Consequences:
  - Positive: thread-safe by construction; cache lives in one process, no IPC.
  - Negative: parse throughput capped at one TU at a time. Concurrent agents on HTTP transport will queue. Acceptable for v1 (local-only, single-agent-typical workload).
  - Follow-up: if throughput becomes a problem in v2, evaluate process-per-build_path sharding (each process owns one repo's TUs).

References:
  - requirements.md US-8, OQ-11
  - design.md §2 (clang_session), §5 (transport)
  - libclang Python bindings: https://github.com/llvm/llvm-project/blob/main/clang/bindings/python/clang/cindex.py (Index docstring)
