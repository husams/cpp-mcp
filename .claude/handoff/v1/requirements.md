# Requirements: C++ Semantic Analysis MCP Server
run_id: cpp-mcp-1
stage: product-manager
date: 2026-05-16

---

## Scope

**In scope (v1):**
- MCP server (Python, `clang.cindex` / `libclang`) exposing 7 semantic analysis tools over local stdio and HTTP transports.
- Stateless build context: no global project state; every tool takes optional `build_path`.
- TU cache (LRU) for performance.
- Structured error responses on all failure paths.
- Path-traversal validation on all file arguments.
- Read-only enforcement for all tools except `cpp_export_to_graphdb`.

**Out of scope (v1):**
- Kubernetes / cluster deployment (local stdio + HTTP only).
- Persistent index surviving server restarts (TU cache is in-memory only).
- Incremental / watch-mode indexing.
- Refactoring, rename, or code-fix tools.
- Non-C++ languages.
- Authentication / multi-tenant access control.
- IDE / LSP protocol bridging.
- Logging / distributed observability infrastructure.

**Dispatch count note:** The dispatch brief mentions 9 tools; raw requirements (`requirements-raw.md`) enumerate 7 distinct tool signatures. This mismatch is surfaced as OQ-1 below. No stories have been added to reach 9.

---

## AC Numbering Convention
AC IDs are scoped per story: `US-N/AC-M`. Downstream traceability uses the combined form (e.g., `US-3/AC-2`).

---

## Stories

---

### US-1 — cpp_get_definition

**Story:** As an LLM agent, I want to locate the exact definition of any C++ symbol at a given file position, so that I can navigate to the authoritative declaration site without reading surrounding context.

**Acceptance criteria:**
- AC-1: Given a valid `file_path`, `line`, `col` pointing to a symbol (function, variable, type, macro, template), when `cpp_get_definition` is called, then the response contains `{ file, line, col, usr }` where `file` is an absolute path and `usr` is a non-empty libclang USR string.
- AC-2: Given a symbol that resolves to a different file than `file_path`, when called, then the returned `file` path is the definition site's absolute path (cross-file navigation succeeds).
- AC-3: Given `build_path` pointing to a directory containing `compile_commands.json`, when called, then compilation flags are sourced from that database (flags_source is `"compilation_db"`).
- AC-4: Given `build_path=None` or the file absent from the compilation database, when called, then the TU is parsed with `default_flags = ["-std=c++20", "-I.", "-x", "c++"]` and the response includes `flags_source: "default"`.
- AC-5: Given an invalid `file_path` (file does not exist), when called, then the response is a structured MCP error `{ code: "FILE_NOT_FOUND", message: <string> }` — no stack trace exposed.
- AC-6: Given `line` or `col` outside the file's valid range, when called, then the response is a structured MCP error `{ code: "INVALID_POSITION", message: <string> }`.
- AC-7: Given `build_path` that exists but contains no `compile_commands.json`, when called, then the tool falls back to `default_flags` and the response includes `flags_source: "default"` (not an error).
- AC-8: Given a `file_path` that contains path-traversal sequences (e.g., `../../etc/passwd`), when called, then the response is a structured MCP error `{ code: "PATH_VIOLATION", message: <string> }` and no file read is attempted.
- AC-9: Given a symbol with no definition reachable by libclang (forward-declared only, external linkage), when called, then the response includes `definition_found: false` and an empty or null location — no error thrown.

**Priority:** P0 — core navigation; required for minimum useful agent capability.

**Dependencies:** NFR stories US-8 (stateless build), US-9 (default_flags), US-10 (TU cache), US-12 (path validation).

**Open questions:**
- OQ-1: Dispatch brief references 9 tools vs. 7 in raw requirements. Architect to confirm authoritative tool list.
- OQ-2: Should `flags_source` field be included in all navigation tool responses or in a separate metadata envelope?

**References:** `requirements-raw.md` §3.A, §4, §5; `CHARTER.md` invariant I1.

---

### US-2 — cpp_get_references

**Story:** As an LLM agent, I want to find all usages of a C++ symbol across the translation unit and linked files, so that I can assess impact of changes without grep-based approximation.

**Acceptance criteria:**
- AC-1: Given a valid `file_path`, `line`, `col` pointing to a symbol, when `cpp_get_references` is called, then the response contains a list of `{ file, line, col, context_snippet }` entries, one per reference site, where each `file` is an absolute path.
- AC-2: Given a symbol with zero references in the parsed TU, when called, then the response contains an empty list (not an error).
- AC-3: Given `build_path=None`, when called, then `default_flags` are applied (per US-1/AC-4 behavior).
- AC-4: Given a non-existent `file_path`, when called, then the response is `{ code: "FILE_NOT_FOUND" }`.
- AC-5: Given an out-of-range `line`/`col`, when called, then the response is `{ code: "INVALID_POSITION" }`.
- AC-6: Given a `file_path` with path-traversal sequences, when called, then the response is `{ code: "PATH_VIOLATION" }`.
- AC-7: Given a large file with many references (>1000), when called, then the response includes all reference entries or a `truncated: true` flag with the count of omitted entries — no silent data loss.

**Priority:** P0 — essential for change-impact analysis.

**Dependencies:** US-8, US-9, US-10, US-12.

**Open questions:**
- OQ-3: Does reference search span only the current TU or all TUs in the compilation database? Architect to decide (affects performance contract).

**References:** `requirements-raw.md` §3.A.

---

### US-3 — cpp_get_type_info

**Story:** As an LLM agent, I want to retrieve the fully qualified type name, canonical type, size, and alignment for a C++ symbol at a given position, so that I can resolve `auto`, template instantiations, and typedef chains without manual expansion.

**Acceptance criteria:**
- AC-1: Given a valid `file_path`, `line`, `col`, when `cpp_get_type_info` is called, then the response contains `{ display_type, canonical_type, size_bytes, alignment_bytes, is_pod, is_const, is_reference, is_pointer }`.
- AC-2: Given a position pointing to an `auto`-declared variable, when called, then `canonical_type` resolves to the deduced concrete type (not `"auto"`).
- AC-3: Given a template instantiation, when called, then `display_type` includes the template arguments and `canonical_type` is fully expanded.
- AC-4: Given a type whose size cannot be determined (incomplete type, forward declaration), when called, then `size_bytes: null` and `alignment_bytes: null` are returned — not an error.
- AC-5: Given `build_path=None`, when called, then `default_flags` are applied.
- AC-6: Given a non-existent file or out-of-range position, when called, then the appropriate structured error is returned (`FILE_NOT_FOUND` or `INVALID_POSITION`).
- AC-7: Given a `file_path` with path-traversal sequences, when called, then the response is `{ code: "PATH_VIOLATION" }`.

**Priority:** P0 — required for template-heavy C++ comprehension.

**Dependencies:** US-8, US-9, US-10, US-12.

**Open questions:** None additional.

**References:** `requirements-raw.md` §3.A.

---

### US-4 — cpp_get_ast

**Story:** As an LLM agent, I want to retrieve a scoped, annotated AST subtree for a C++ file, so that I can understand code structure at a level of detail appropriate to my context window.

**Acceptance criteria:**
- AC-1: Given a valid `file_path` and `format="json"`, when `cpp_get_ast` is called, then the response is a valid JSON tree where each node contains `{ kind, spelling, usr, type, storage_class, start_line, start_col, end_line, end_col, children }`.
- AC-2: Given `format="graph"`, when called, then the response contains `{ nodes: [{ id, kind, spelling, usr, type }], edges: [{ source_id, target_id, edge_type }] }` where `edge_type` is one of `CHILD`, `TYPE_REF`, `CALL`.
- AC-3: Given `depth=N`, when called, then the returned tree contains at most N levels of nesting (root = level 0); nodes beyond depth N are omitted and their omission is indicated by `truncated: true` on the parent node.
- AC-4: Given `start_line` and `end_line` specified, when called, then only AST nodes whose source range overlaps `[start_line, end_line]` are included.
- AC-5: Given `depth` not specified, when called, then the default depth of 3 is applied.
- AC-6: Given `build_path=None`, when called, then `default_flags` are applied.
- AC-7: Given a file that fails to parse (unresolvable includes, syntax errors), when called, then the response includes any partially recovered AST plus a `parse_errors: [{ severity, message, file, line, col }]` list — not a total failure.
- AC-8: Given a non-existent `file_path`, when called, then the response is `{ code: "FILE_NOT_FOUND" }`.
- AC-9: Given `start_line > end_line`, when called, then the response is `{ code: "INVALID_RANGE" }`.
- AC-10: Given a `file_path` with path-traversal sequences, when called, then the response is `{ code: "PATH_VIOLATION" }`.

**Priority:** P0 — structural analysis; required for code comprehension agent tasks.

**Dependencies:** US-8, US-9, US-10, US-12.

**Open questions:**
- OQ-4: Maximum response size cap for AST output (token budget) — architect to define a node count ceiling or byte limit to prevent context-window overrun.
- OQ-5: Should `format="graph"` edge types be extensible or fixed to the three listed? Defer to architect.

**References:** `requirements-raw.md` §3.B.

---

### US-5 — cpp_get_header_info

**Story:** As an LLM agent, I want to inspect the include graph and exported public symbols of a C++ header file, so that I can understand a module's API surface without reading implementation files.

**Acceptance criteria:**
- AC-1: Given a valid `file_path`, when `cpp_get_header_info` is called, then the response contains `{ direct_includes: [path], transitive_includes: [path], exported_symbols: [{ kind, name, usr, signature }], missing_includes: [path], orphaned_includes: [path] }`.
- AC-2: Given a header file with no includes, when called, then `direct_includes` and `transitive_includes` are empty lists — not an error.
- AC-3: Given a header that includes a file that cannot be resolved, when called, then the unresolvable path appears in `missing_includes` (not a hard error).
- AC-4: Given an include that is present in the file system but exports no symbols referenced in `file_path`, when called, then that include path appears in `orphaned_includes`.
- AC-5: Given `build_path=None`, when called, then `default_flags` are applied.
- AC-6: Given a non-existent `file_path`, when called, then `{ code: "FILE_NOT_FOUND" }`.
- AC-7: Given a `file_path` with path-traversal sequences, when called, then `{ code: "PATH_VIOLATION" }`.

**Priority:** P1 — valuable for API surface discovery; not blocking for core navigation.

**Dependencies:** US-8, US-9, US-10, US-12.

**Open questions:**
- OQ-6: "Orphaned" definition: include not referenced in current TU, or include not referenced in entire project? Define scope for v1.

**References:** `requirements-raw.md` §3.C.

---

### US-6 — cpp_get_preprocessor_state

**Story:** As an LLM agent, I want to retrieve the active macro definitions and evaluated conditional compilation state for a C++ file, so that I can reason about which code branches are active under the current build configuration.

**Acceptance criteria:**
- AC-1: Given a valid `file_path`, when `cpp_get_preprocessor_state` is called, then the response contains `{ macros: [{ name, value, defined_at: { file, line } }], conditionals: [{ directive, condition, evaluated_result: true|false, start_line, end_line }] }`.
- AC-2: Given a macro defined via `-D` in the compilation flags, when called, then that macro appears in `macros` with `defined_at: null` (command-line origin).
- AC-3: Given a `#ifdef` block, when called, then `conditionals` includes an entry with `evaluated_result: true` or `false` matching the compiler's actual evaluation under the active flags.
- AC-4: Given a file with no macros or conditionals, when called, then both lists are empty — not an error.
- AC-5: Given `build_path=None`, when called, then `default_flags` are applied.
- AC-6: Given a non-existent `file_path`, when called, then `{ code: "FILE_NOT_FOUND" }`.
- AC-7: Given a `file_path` with path-traversal sequences, when called, then `{ code: "PATH_VIOLATION" }`.

**Priority:** P1 — important for conditional-compilation reasoning; not blocking P0 navigation.

**Dependencies:** US-8, US-9, US-10, US-12.

**Open questions:**
- OQ-7: Should transitive macros (defined in included headers) also appear, or only macros from `file_path` itself? Architect to decide.

**References:** `requirements-raw.md` §3.C.

---

### US-7 — cpp_export_to_graphdb

**Story:** As an LLM agent or operator, I want to export AST and symbol relationship data for a file or directory into a graph database, so that I can run persistent cross-file queries and build a knowledge graph of the codebase.

**Acceptance criteria:**
- AC-1: Given a valid `file_path_or_dir`, `build_path`, and reachable `db_uri`, when `cpp_export_to_graphdb` is called, then the tool ingests nodes of types `File`, `Namespace`, `Class`, `Function`, `Variable`, `Macro`, `TypeAlias` into the graph database and returns `{ files_processed, nodes_written, edges_written, errors: [] }`.
- AC-2: Given the graph schema, when exported, then edges include at minimum: `DEFINES`, `DECLARES`, `CALLS`, `INHERITS`, `REFERENCES`, `INCLUDES`, `MEMBER_OF`.
- AC-3: Given a `db_uri` that is unreachable or returns a connection error, when called, then the response is `{ code: "DB_UNREACHABLE", message: <string> }` — no source files are modified.
- AC-4: Given a directory input, when called, then all `.cpp`, `.h`, `.hpp`, `.cc`, `.cxx` files within the directory are processed (non-recursively by default; recursive if a `recursive=true` parameter is provided).
- AC-5: Given processing that partially fails (some files error), when called, then successfully processed files are committed and the `errors` list contains `{ file, code, message }` entries for failures — no all-or-nothing transaction required.
- AC-6: Given a non-existent `file_path_or_dir`, when called, then `{ code: "FILE_NOT_FOUND" }`.
- AC-7: Given a `file_path_or_dir` or `build_path` with path-traversal sequences, when called, then `{ code: "PATH_VIOLATION" }` and no database write occurs.
- AC-8: This tool MUST NOT write to, modify, or delete any source file. A write attempt to any path within `file_path_or_dir`'s directory tree must be treated as an implementation defect.
- AC-9: Given `build_path` or `db_uri` is absent, null, or empty string, when called, then the response is `{ code: "INVALID_ARGUMENT", message: <string> }` identifying the missing parameter — no partial execution occurs.

**Priority:** P2 — heaviest dependency (external graph DB); standalone value; not required for P0/P1 tools.

**Dependencies:** US-8, US-9, US-12. External: graph database service (e.g., Cognee, Neo4j) accessible at `db_uri`.

**Open questions:**
- OQ-8: Graph DB target: Cognee local vs. Neo4j? Driver abstraction needed? Architect to decide.
- OQ-9: Idempotency: should re-export of the same file upsert or duplicate nodes? Architect to decide.
- OQ-10: Is `recursive=true` in scope for v1 or deferred?

**References:** `requirements-raw.md` §3.D.

---

### US-8 — Stateless Build Context (NFR)

**Story:** As a developer integrating this server, I want the server to carry no mutable global project state between tool calls, so that multiple agents can interleave calls across different repositories in the same server session without configuration collisions.

**Acceptance criteria:**
- AC-1: Given two tool calls (concurrent or interleaved, depending on transport) with different `build_path` values (`/repo-a/build` and `/repo-b/build`), when both calls complete, then each call's flags are sourced from its own `build_path` — no cross-contamination of flags is observable in either response.
- AC-2: Given a tool call without `build_path`, followed by a tool call with a `build_path`, when both complete, then the first call used `default_flags` and the second used the compilation database — neither call mutates shared state.
- AC-3: Given a server restart, when a new tool call arrives, then no state from the previous session persists (TU cache starts empty; no stored project roots).
- AC-4: The server MUST NOT expose any tool or endpoint to set a global project root, active configuration, or default `build_path`.

**Priority:** P0 — architectural invariant; all functional stories depend on this.

**Dependencies:** None (foundational).

**Open questions:**
- OQ-11: Concurrency model: are concurrent tool calls expected (HTTP transport only) or serialized (stdio)? Architect to specify thread-safety requirements for `libclang` Index and TU cache. Known issue: `libclang`'s `Index` is not always reentrant.

**References:** `requirements-raw.md` §2, §4.

---

### US-9 — Default Flags Fallback (NFR)

**Story:** As an LLM agent, I want the server to fall back to standard C++20 compilation flags when no `build_path` is provided or the file is absent from the compilation database, so that I can inspect files without needing a build system.

**Acceptance criteria:**
- AC-1: Given `build_path=None`, when any tool requiring compilation context is called, then the TU is parsed with `default_flags = ["-std=c++20", "-I.", "-x", "c++"]`.
- AC-2: Given a valid `build_path` but the `file_path` is not listed in `compile_commands.json`, when called, then `default_flags` are applied and the response includes `flags_source: "default"`.
- AC-3: Given `build_path` points to a directory with a `compile_commands.json` that lists the file, when called, then the file's specific flags are used and the response includes `flags_source: "compilation_db"`.
- AC-4: The `default_flags` value MUST be configurable at server startup (environment variable or config file) without code changes.

**Priority:** P0 — usability gate; without it, server requires a build system for all operations.

**Dependencies:** US-8.

**Open questions:**
- OQ-12: Should `default_flags` be overridable per-call (as a tool parameter)? Defer to architect; flag as potential P1 enhancement.

**References:** `requirements-raw.md` §4.

---

### US-10 — TU Cache with LRU Eviction (NFR)

**Story:** As a server operator, I want the server to cache parsed Translation Units with LRU eviction, so that repeated queries on the same file are served without re-parsing, reducing latency.

**Acceptance criteria:**
- AC-1: Given a tool call for `(file_path, build_path)` that was parsed in a prior call within the same session, when the second call is made, then the TU is retrieved from cache without invoking `libclang` parse again (observable via response metadata `cache_hit: true`).
- AC-2: Given the cache holding N entries at its capacity, when a new `(file_path, build_path)` pair is parsed, then the least-recently-used entry is evicted before the new entry is inserted.
- AC-3: Given cache capacity N, when the server is queried for its status (e.g., via a health/stats endpoint), then `{ cache_size: <current>, cache_capacity: <N>, cache_hit_rate: <float> }` is returned.
- AC-4: Given two calls with the same `file_path` but different `build_path` values, when both are cached, then they occupy separate cache entries — sharing is not permitted.
- AC-5: The cache capacity MUST be configurable at server startup (environment variable or config file); default is 128 TUs.
- AC-6: Given a cached TU whose source file has been modified on disk (mtime changed), when the next call is made, then the stale TU is evicted and the file is re-parsed — stale data MUST NOT be served.

**Priority:** P1 — performance optimization; server is functionally correct without it, just slower.

**Dependencies:** US-8.

**Open questions:**
- OQ-13: mtime invalidation (AC-6): polling on each call vs. inotify/FSEvents watcher? Architect to decide.

**References:** `requirements-raw.md` §4.

---

### US-11 — Read-Only Enforcement (NFR)

**Story:** As a security-conscious operator, I want all semantic analysis tools (except `cpp_export_to_graphdb`) to be strictly read-only, so that agents cannot inadvertently or maliciously modify source files.

**Acceptance criteria:**
- AC-1: Given any tool call to US-1 through US-6, when the tool executes, then no file within the server's accessible filesystem is created, modified, or deleted — enforced at the implementation level (no write syscalls to source paths).
- AC-2: Given `cpp_export_to_graphdb` (US-7), when it executes, then no file within the `file_path_or_dir` directory tree is created, modified, or deleted; writes go only to the external `db_uri`.
- AC-3: The server MUST NOT expose any tool endpoint that accepts file content for writing back to disk.

**Priority:** P0 — safety property; must hold before any deployment.

**Dependencies:** None (cross-cutting).

**Open questions:** None.

**References:** `requirements-raw.md` §5.

---

### US-12 — Path Traversal Validation (NFR)

**Story:** As a security-conscious operator, I want all file path arguments to be validated against path-traversal and symlink-escape attacks, so that agents cannot access arbitrary filesystem locations outside intended project directories.

**Acceptance criteria:**
- AC-1: Given a `file_path` containing `..` components (e.g., `../../etc/passwd`), when any tool is called, then the response is `{ code: "PATH_VIOLATION", message: <string> }` before any file I/O is attempted.
- AC-2: Given a `build_path` containing `..` components, when any tool is called, then the response is `{ code: "PATH_VIOLATION" }`.
- AC-3: Given a `file_path` that is a symlink resolving to a path outside the server's allowed root, when called, then the response is `{ code: "PATH_VIOLATION" }`.
- AC-4: Given an absolute path within the server's allowed root, when called, then path validation passes and the tool proceeds normally.
- AC-5: The server's allowed root directory MUST be configurable at startup (environment variable); if not set, the server MUST refuse all tool calls and return a startup error.

**Priority:** P0 — security property; must hold before any deployment.

**Dependencies:** None (cross-cutting).

**Open questions:**
- OQ-14: Should the server enforce a single allowed root or a list of allowed roots (e.g., multiple repos)? Architect to decide.
- OQ-15: Symlink handling: fully resolve (follow all symlinks, check resolved path) or deny all symlinks? Architect to decide.

**References:** `requirements-raw.md` §5.

---

### US-13 — Structured Error Envelope (NFR)

**Story:** As an LLM agent consuming tool responses, I want all error responses to use a consistent structured envelope, so that I can programmatically handle errors without parsing free-text strings.

**Acceptance criteria:**
- AC-1: Given any tool call that results in an error, when the response is returned, then it conforms to `{ code: "<ERROR_CODE>", message: "<human-readable string>", tool: "<tool_name>", request_id: "<uuid>" }`.
- AC-2: Given an unexpected server-side exception, when the response is returned, then the error code is `"INTERNAL_ERROR"` and no stack trace or internal path is exposed in `message`.
- AC-3: The set of valid error codes is: `FILE_NOT_FOUND`, `INVALID_POSITION`, `INVALID_RANGE`, `INVALID_ARGUMENT`, `PATH_VIOLATION`, `DB_UNREACHABLE`, `PARSE_ERROR`, `INTERNAL_ERROR`. No tool returns an unstructured string as its error.

**Priority:** P0 — required for agent-side error handling; no additional implementation cost if designed in from the start.

**Dependencies:** None (cross-cutting).

**Open questions:**
- OQ-16: Should partial-success responses (e.g., AST with parse errors, graphdb export with some file failures) use the error envelope or a separate `warnings` field? Architect to decide.

**References:** `requirements-raw.md` §3 (implied by all tools), CHARTER.md.

---

### US-14 — Transport: stdio and HTTP (NFR)

**Story:** As a developer integrating this server, I want the MCP server to support both local stdio and HTTP transport modes, so that it can be embedded in CLI tooling (stdio) and called from remote agents (HTTP) without separate deployments.

**Acceptance criteria:**
- AC-1: Given the server started in `stdio` mode, when a valid MCP JSON-RPC request is written to stdin, then the response is written to stdout within the same session.
- AC-2: Given the server started in `http` mode with a configurable `--port`, when an HTTP POST to `/mcp` is made with a valid MCP request body, then the response is returned with HTTP 200 and a valid MCP response body.
- AC-3: Both transport modes expose the same set of tools (US-1 through US-7) with identical behavior.
- AC-4: The server MUST NOT require Kubernetes, Docker Compose, or any orchestration system to run in either transport mode.

**Priority:** P1 — stdio is P0 for CLI use; HTTP is P1 for remote agent use.

**Dependencies:** US-8.

**Open questions:**
- OQ-17: HTTP authentication (API key, bearer token) for the HTTP transport in v1? Given local-only stated scope, likely out of scope — architect to confirm.

**References:** `requirements-raw.md` §1 (implied), CHARTER.md (local stdio/HTTP, not k8s).

---

## Open Questions Summary

| ID | Question | Owned by |
|---|---|---|
| OQ-1 | Dispatch says 9 tools, raw requirements list 7. Confirm authoritative tool count. | Coordinator / architect |
| OQ-2 | `flags_source` field: per-response or in a metadata envelope? | Architect |
| OQ-3 | `cpp_get_references` scope: single TU or all TUs in compilation database? | Architect |
| OQ-4 | AST response node count ceiling / byte limit to prevent context-window overrun. | Architect |
| OQ-5 | `format="graph"` edge types: fixed set or extensible? | Architect |
| OQ-6 | "Orphaned include" definition: TU-scope or project-scope? | Architect |
| OQ-7 | `cpp_get_preprocessor_state`: transitive macros (from included headers) included or not? | Architect |
| OQ-8 | Graph DB target: Cognee vs. Neo4j; driver abstraction needed? | Architect |
| OQ-9 | GraphDB export idempotency: upsert or duplicate on re-export? | Architect |
| OQ-10 | `recursive=true` directory traversal for graphdb export: in scope for v1? | Architect |
| OQ-11 | Concurrency model for HTTP transport: thread-safety of libclang Index and TU cache. | Architect |
| OQ-12 | Per-call `default_flags` override as a tool parameter: P1 enhancement? | Architect |
| OQ-13 | Cache invalidation on mtime change: poll-per-call vs. filesystem watcher? | Architect |
| OQ-14 | Allowed root: single directory or list of allowed roots? | Architect |
| OQ-15 | Symlink handling: follow-and-check vs. deny-all? | Architect |
| OQ-16 | Partial-success responses: error envelope or `warnings` field? | Architect |
| OQ-17 | HTTP transport authentication in v1: in scope or deferred? | Architect |

---

## Priority Rollup

| Priority | Stories |
|---|---|
| P0 | US-1, US-2, US-3, US-4, US-8, US-9, US-11, US-12, US-13 |
| P1 | US-5, US-6, US-10, US-14 |
| P2 | US-7 |

---

## Story Dependency Graph

```
US-8 (stateless) ← US-1, US-2, US-3, US-4, US-5, US-6, US-7, US-14
US-9 (default_flags) ← US-1, US-2, US-3, US-4, US-5, US-6
US-10 (TU cache) ← US-1, US-2, US-3, US-4, US-5, US-6
US-11 (read-only) ← US-1, US-2, US-3, US-4, US-5, US-6, US-7
US-12 (path validation) ← US-1, US-2, US-3, US-4, US-5, US-6, US-7
US-13 (error envelope) ← all functional stories
```

All P0 functional stories (US-1..US-4) depend on NFR stories US-8, US-9, US-11, US-12, US-13 being designed concurrently — the architect MUST address these as a unit.
