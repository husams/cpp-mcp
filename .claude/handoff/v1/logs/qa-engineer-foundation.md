run_id: cpp-mcp-1
story: foundation (Stories 1-4: project-bootstrap, error-envelope-and-path-guard, compile-db-and-default-flags, clang-session-and-tu-cache)
role: qa-engineer
date: 2026-05-16

---

## Scope

Foundation stories: project-bootstrap (Story 1), error-envelope-and-path-guard (Story 2),
compile-db-and-default-flags (Story 3), clang-session-and-tu-cache (Story 4).

ACs in scope: US-8 (stateless build_path), US-9 (default_flags), US-10 (TU cache),
US-11 (read-only enforcement), US-12 (path validation), US-13 (error envelope).

---

## Skills loaded

- python-conventions (triggered: pyproject.toml + *.py present)
- advisor (called once before writing tests to confirm approach)

---

## Commands run + outcomes

| Command | Outcome | Exit Code |
|---|---|---|
| `find /Users/husam/workspace/cpp-mcp/src /Users/husam/workspace/cpp-mcp/tests -type f -name "*.py"` | File inventory — 49 Python files found | 0 |
| `uv run pytest tests/unit/test_error_envelope.py tests/unit/test_path_guard.py tests/unit/test_compile_db.py tests/unit/test_tu_cache.py tests/unit/test_clang_session.py -v` | 89 passed | 0 |
| `uv add --dev hypothesis` | hypothesis==6.152.7 installed | 0 |
| `uv run pytest tests/unit/test_foundation_property.py -v` (pass 1) | 5 failed (Hypothesis health checks), 16 passed | 1 |
| `uv run pytest tests/unit/test_foundation_property.py -v` (pass 2, after macOS realpath fix) | 20 passed, 1 failed | 1 |
| `uv run pytest tests/unit/test_foundation_property.py -v` (pass 3, after all fixes) | 21 passed | 0 |
| `uv run pytest tests/unit/test_error_envelope.py tests/unit/test_path_guard.py tests/unit/test_compile_db.py tests/unit/test_tu_cache.py tests/unit/test_clang_session.py tests/unit/test_foundation_property.py -v --tb=short` | **110 passed** | 0 |
| `uv run pytest tests/unit/ -v` (full unit suite regression check) | 243 passed, 1 skipped | 0 |

---

## AC-to-Scenario-ID Traceability Table

### US-8: Stateless build_path (no cross-call state contamination)

| AC | Scenario ID | Covering Test | Status |
|---|---|---|---|
| US-8/AC-1 (two calls with different build_paths use independent flags) | SC-US-8-1 | test_compile_db.py::test_db_hit_returns_db_flags + test_foundation_property.py::test_resolve_flags_none_build_path_returns_default | pass |
| US-8/AC-2 (no-build_path then with build_path — no state mutation) | SC-US-8-2 | test_foundation_property.py::test_resolve_flags_none_build_path_returns_default (purity check — two sequential calls with None) | pass |
| US-8/AC-3 (server restart clears TU cache) | SC-US-8-3 | test_tu_cache.py::test_initial_hit_rate_is_zero + test_tu_cache.py::test_clear_empties_cache (new TUCache() proxy) | pass |
| US-8/AC-4 (no global project root endpoint exposed) | SC-US-8-4 | out-of-scope: server/tool layer (Stories 5-7) — no tool dispatcher exists in foundation |

### US-9: Default Flags Fallback

| AC | Scenario ID | Covering Test | Status |
|---|---|---|---|
| US-9/AC-1 (build_path=None applies default_flags) | SC-US-9-1 | test_compile_db.py::test_build_path_none_returns_default_flags + test_foundation_property.py::test_resolve_flags_none_build_path_returns_default | pass |
| US-9/AC-2 (file absent from compile_commands.json falls back) | SC-US-9-2 | test_compile_db.py::test_file_not_in_db_returns_default_flags | pass |
| US-9/AC-3 (file present uses compilation_db flags) | SC-US-9-3 | test_compile_db.py::test_db_hit_returns_db_flags | pass |
| US-9/AC-4 (default flags configurable at startup) | SC-US-9-4 | test_path_guard.py::test_load_config_custom_flags | pass |

### US-10: TU Cache with LRU Eviction

| AC | Scenario ID | Covering Test | Status |
|---|---|---|---|
| US-10/AC-1 (cache hit on second call for same key) | SC-US-10-1 | test_tu_cache.py::test_second_access_is_hit | pass |
| US-10/AC-1 negative (cache miss on first call) | SC-US-10-2 | test_tu_cache.py::test_first_access_is_miss + test_foundation_property.py::test_tu_cache_miss_on_each_distinct_key | pass |
| US-10/AC-2 (LRU eviction when cache is full) | SC-US-10-3 | test_tu_cache.py::test_lru_eviction + test_tu_cache.py::test_configurable_capacity | pass |
| US-10/AC-3 (cache stats endpoint returns hit rate) | SC-US-10-4 | test_tu_cache.py::test_stats_structure_and_counts + test_clang_session.py::test_cache_stats_after_parse | pass |
| US-10/AC-4 (different build_paths for same file are separate entries) | SC-US-10-5 | test_tu_cache.py::test_two_build_paths_separate_entries | pass |
| US-10/AC-5 (cache capacity configurable at startup) | SC-US-10-6 | test_tu_cache.py::test_configurable_capacity + test_path_guard.py::test_load_config_success (cache_capacity=128 default) | pass |
| US-10/AC-6 (stale TU evicted on mtime change) | SC-US-10-7 | test_tu_cache.py::test_mtime_invalidation_triggers_reparse + test_tu_cache.py::test_mtime_boundary_one_ns | pass |

### US-11: Read-Only Enforcement

| AC | Scenario ID | Covering Test | Status |
|---|---|---|---|
| US-11/AC-1 (navigation tools make no filesystem writes) | SC-US-11-1 | out-of-scope: tool layer (Stories 5-7) — navigation tools not yet implemented |
| US-11/AC-2 (cpp_export_to_graphdb makes no source writes) | SC-US-11-2 | out-of-scope: tool layer (Story 7) — export tool not yet implemented |
| US-11/AC-3 (no write-back endpoint exposed) | SC-US-11-3 | out-of-scope: server/tool layer (Stories 5-7) |

### US-12: Path Traversal Validation

| AC | Scenario ID | Covering Test | Status |
|---|---|---|---|
| US-12/AC-1 (PATH_VIOLATION for .. in file_path) | SC-US-12-1 | test_path_guard.py::test_dotdot_in_path_raises_path_violation + test_foundation_property.py::test_has_dotdot_rejects_all_dotdot_paths + test_foundation_property.py::test_dotdot_boundary_cases[*] | pass |
| US-12/AC-2 (PATH_VIOLATION for .. in build_path) | SC-US-12-2 | test_path_guard.py::test_dotdot_in_middle_segment_raises (path_guard is path-type agnostic) | pass |
| US-12/AC-3 (PATH_VIOLATION for symlink escaping root) | SC-US-12-3 | test_path_guard.py::test_symlink_escaping_root_raises_path_violation + test_path_guard.py::test_chained_symlink_escape_raises | pass |
| US-12/AC-4 (absolute path within root passes) | SC-US-12-4 | test_path_guard.py::test_valid_path_inside_root_returns_resolved + test_foundation_property.py::test_valid_path_inside_root_always_passes | pass |
| US-12/AC-5 (server refuses all calls if ALLOWED_ROOT not configured) | SC-US-12-5 | test_path_guard.py::test_load_config_raises_on_missing_allowed_roots | pass |
| US-12/AC-1 boundary (absolute path outside root rejected) | SC-US-12-6 | test_path_guard.py::test_path_outside_all_roots_raises + test_foundation_property.py::test_path_outside_root_always_rejected | pass |

### US-13: Structured Error Envelope

| AC | Scenario ID | Covering Test | Status |
|---|---|---|---|
| US-13/AC-1 (all error responses conform to envelope schema) | SC-US-13-1 | test_error_envelope.py::test_build_error_shape + test_foundation_property.py::test_build_error_envelope_schema_invariant + test_foundation_property.py::test_wrap_tool_code_always_in_valid_set | pass |
| US-13/AC-2 (INTERNAL_ERROR exposes no stack trace) | SC-US-13-2 | test_error_envelope.py::test_wrap_tool_internal_error_no_traceback_in_message + test_foundation_property.py::test_sanitizer_redacts_unechoed_absolute_paths | pass |
| US-13/AC-3 (no unstructured string returned as error) | SC-US-13-3 | test_foundation_property.py::test_wrap_tool_always_returns_structured_dict | pass |

---

## Defects

None. All exercised ACs pass. Out-of-scope items are not defects — they are forwarded to tool-layer stories.

---

## Observations (advisory)

1. **macOS symlink in tempdir**: On macOS `/var/folders/...` is a symlink to `/private/var/folders/...`. Tests using `tempfile.TemporaryDirectory()` must call `os.path.realpath()` on the returned path before passing it as `allowed_roots`, otherwise `_under_any_root` comparison fails. Developer tests correctly use pytest's `tmp_path` fixture (which already returns the realpath). Property tests exposed this latent portability consideration. The fix was applied in test code (not production code).

2. **hypothesis not in pyproject.toml dev deps**: `hypothesis` was added via `uv add --dev hypothesis` to enable property tests. This is a dev-only change and should be committed. The production source code is unchanged.

3. **US-11 (read-only enforcement) is entirely out-of-scope at foundation stage**: The three ACs require tool implementations from Stories 5-7. This is expected and is not a QA_DEFECT.

4. **US-8/AC-4 (no global set_project_root endpoint)**: Server-layer concern; cannot be validated until the MCP app is wired in Stories 5-7.

---

## Additions made

**Property-based (Hypothesis)**: Added `tests/unit/test_foundation_property.py` with 10 property suites and 11 parametrised boundary cases (21 tests total). Covers SC-US-12-1, SC-US-12-4, SC-US-12-6, SC-US-13-1, SC-US-13-2, SC-US-13-3, SC-US-9-1, SC-US-8-1, SC-US-10-2.

---

## References

- scenarios.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/scenarios.md
- developer-project-bootstrap.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-project-bootstrap.md
- developer-error-envelope-and-path-guard.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-error-envelope-and-path-guard.md
- developer-compile-db-and-default-flags.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-compile-db-and-default-flags.md
- developer-clang-session-and-tu-cache.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/logs/developer-clang-session-and-tu-cache.md
- Cognee tags: task:cpp-mcp, role:qa-engineer, scope:foundation
