# ADR-19: Cache-key scope under v5 rename (OQ-1)

Status: accepted
Context:
- v5 NFR mandates "cache keys untouched."
- `src/cpp_mcp/core/tu_cache.py` keys are `(file, build, flags_hash)` per ADR-6. Tool name is not a cache dimension; no other cache exists in the codebase.
- OQ-1 asked whether "untouched" means schema-untouched or string-untouched.

Decision:
- "Untouched" means **cache key schema (dimensions and arguments) is unchanged**. Tool-name strings are not embedded in any cache key today, so the rename trivially satisfies the NFR.
- Developer MUST NOT add tool-name to any cache key as part of this release. QA gate: `grep -RIn "tool.\?name\|\"cpp_\|'cpp_" src/cpp_mcp/core/tu_cache.py` returns no hits.

Alternatives considered:
- Require byte-for-byte cache-key equality verification — rejected: no tool-name strings exist in keys today (verified), so the check is vacuous.
- Add tool-name to cache key for observability — rejected: out of scope for a pure-rename release.

Consequences:
- Positive: zero cache invalidation; existing on-disk/runtime caches remain valid across upgrade.
- Negative: none.
- Follow-up: none.

References: `src/cpp_mcp/core/tu_cache.py:47`, ADR-6, requirements.md OQ-1.
