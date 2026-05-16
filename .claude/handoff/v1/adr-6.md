# ADR-6: TU cache — OrderedDict LRU, mtime-polled invalidation, capacity 128
Status: accepted
Context:
  - OQ-13: how to detect stale TUs when source file changes on disk (US-10/AC-6).
  - Two options: (a) poll source file `mtime` on every cache lookup; (b) install an OS-level filesystem watcher (inotify on Linux, FSEvents on macOS).
  - The cache key must include `build_path` so two different build configs produce two cache entries (US-10/AC-4).

Decision:
  - Data structure: `collections.OrderedDict[Key, Entry]` with `move_to_end` on hit (canonical Python LRU).
  - Key: `(realpath(file), realpath(build_path) or "", sha1(tuple(flags)))`. Including the flags hash protects against `compile_commands.json` mutation invalidating cached TUs.
  - Entry value: `(translation_unit, source_mtime_ns, flags_used, source_path)`.
  - Invalidation: **poll** — on every lookup, `os.stat(source_path).st_mtime_ns` is compared to cached value. Mismatch → evict + re-parse. Stat is microseconds; cheap relative to the libclang parse it might save.
  - Capacity: default **128**, override via `CPP_MCP_CACHE_CAPACITY`.
  - Thread safety: a single `threading.Lock` around lookup/insert/evict. Held only for the dict operations, not for the parse itself (we release the lock, run parse, re-acquire to insert).
  - Stats: `cache_size`, `cache_capacity`, `hits`, `misses`, `evictions`, `cache_hit_rate = hits/(hits+misses)` exposed via `/healthz` (HTTP) and a `get_cache_stats` MCP tool would be redundant; we put it in healthz only.

Alternatives considered:
  - inotify/FSEvents watcher: rejected for v1 — adds a platform-specific dependency, async complexity, and only saves a few microseconds per lookup. Re-evaluate if mtime polling shows up in profiles.
  - `functools.lru_cache`: rejected — no eviction visibility and can't easily invalidate by key.
  - Content hash instead of mtime: rejected — reading file to hash defeats the latency saving.

Consequences:
  - Positive: simple, dependency-free, works identically on Linux and macOS.
  - Negative: a file modified between the stat call and libclang opening it could be served stale; race window is microseconds and the next call will catch it. Acceptable.
  - Follow-up: tune default capacity based on operator feedback; document RSS expectation in runbook.

References:
  - requirements.md US-10 (all AC), OQ-13
  - design.md §2 (tu_cache), §4 (data flow)
