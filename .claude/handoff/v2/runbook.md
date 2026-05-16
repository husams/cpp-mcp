---
run_id: fastmcp-migration-v2
stage: devops
date: 2026-05-16
covers: US-M8/AC-3, R-1, R-8
supersedes: S7 draft (bug-fixed: env var names, CLI flags, warning text)
---

# cpp-mcp Operations Runbook

---

## 1. Start — stdio transport

Stdio mode is the default and the only transport used by Claude Code and Claude Desktop.

```bash
# Required: at least one existing absolute directory
export CPP_MCP_ALLOWED_ROOTS="/absolute/path/to/your/cpp/project"

# Run via console script (installed package)
cpp-mcp

# Run via uv (development checkout)
uv run python -m cpp_mcp

# Run via uv with explicit project path
uv run --project /path/to/cpp-mcp python -m cpp_mcp
```

Log output goes to **stderr only**. Stdout carries MCP JSON-RPC frames exclusively (C-9).

The server blocks reading stdin until the MCP client closes it or sends a shutdown.

To select stdio explicitly when `CPP_MCP_TRANSPORT` is set in environment:

```bash
export CPP_MCP_TRANSPORT=stdio
cpp-mcp
```

---

## 2. Start — HTTP transport

HTTP mode is for programmatic HTTP/SSE clients. It is not used by Claude Code or Claude
Desktop.

**There are no CLI flags for transport selection.** All configuration is env-var driven.

```bash
export CPP_MCP_ALLOWED_ROOTS="/absolute/path/to/your/cpp/project"
export CPP_MCP_TRANSPORT=http

# Optional: override bind address and port (defaults: 127.0.0.1:8000)
export CPP_MCP_HTTP_BIND=127.0.0.1
export CPP_MCP_HTTP_PORT=8000

cpp-mcp
```

The server binds at startup. Verify it is listening:

```bash
# In a separate terminal:
curl http://127.0.0.1:8000/health   # returns: OK
```

The MCP endpoint (SSE) is at `POST http://127.0.0.1:8000/mcp`.

**Non-loopback bind warning**: if `CPP_MCP_HTTP_BIND` resolves to anything other than
`127.0.0.1`, `::1`, or `localhost`, the server emits one WARNING line to stderr:

```
HTTP transport bound to non-loopback address '<bind>'; do not expose to untrusted networks — no authentication is configured
```

No authentication is implemented in v2 (US-M2/AC-5 deferred — ADR-8; v3 work).

To stop the HTTP server: send SIGTERM or press Ctrl-C. The lifespan `finally` block runs
`ClangSession.aclose()` before exit.

---

## 3. Environment variables and defaults

All configuration is read at process startup via `src/cpp_mcp/server/config.py`. There is
no config file; all tuning is via environment variables.

| Variable | Required | Default | Description |
|---|---|---|---|
| `CPP_MCP_ALLOWED_ROOTS` | **yes** | — | Colon-separated absolute directory paths the server may read. Missing or empty → `ConfigError` at startup (rc=1, message on stderr). |
| `CPP_MCP_DEFAULT_FLAGS` | no | `-std=c++20 -I. -x c++` | Space-separated compiler flags used when no `compile_commands.json` covers a file. Tokenized via `shlex.split`. |
| `CPP_MCP_CACHE_CAPACITY` | no | `128` | LRU translation-unit cache size. Use `16` on hosts with < 4 GiB free RAM. |
| `CPP_MCP_AST_MAX_NODES` | no | `5000` | Node-count ceiling for `cpp_get_ast`; truncated responses include `"truncated": true`. |
| `CPP_MCP_AST_MAX_BYTES` | no | `1048576` | Byte ceiling (1 MiB) for serialized AST responses. |
| `CPP_MCP_LIBCLANG_PATH` | no | auto-detected | Absolute path to `libclang.so` / `libclang.dylib`. Set when libclang is not on the default search path. |
| `CPP_MCP_LOG_LEVEL` | no | `INFO` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Applies to stderr output. |
| `CPP_MCP_TRANSPORT` | no | `stdio` | Transport selector: `stdio` or `http`. |
| `CPP_MCP_HTTP_BIND` | no | `127.0.0.1` | Bind address for HTTP transport. Non-loopback values emit a WARNING. |
| `CPP_MCP_HTTP_PORT` | no | `8000` | TCP port for HTTP transport. Must be a positive integer. |

---

## 4. FastMCP upgrade-check procedure

### Pin rationale

`pyproject.toml` pins FastMCP with a compatible-release specifier:

```toml
fastmcp~=3.1.0
```

This means `>=3.1.0, <3.2.0`. `uv.lock` pins the exact resolved version (currently
`3.1.1`). The `~=3.1.0` pin was chosen because:

- FastMCP 3.x introduced `@mcp.tool` decorator registration, `Depends` DI, and
  `mcp.run()` as the unified entrypoint (ADR-11 / v2 adr-9.md).
- Patch versions (`3.1.x`) are safe to accept automatically via `uv update`.
- Minor bumps (`3.2.x`) may change tool-schema generation or transport internals and
  require evaluation before adoption (R-1).

### Accepting a new patch version (`3.1.x`)

Patch-level bumps within the locked minor are safe. To update:

```bash
uv update fastmcp
uv run pytest -q   # 472 passed (or higher) required
git add uv.lock && git commit -m "chore: update fastmcp patch"
```

### Evaluating a new minor version (e.g. `3.1.x → 3.2.0`)

1. **Read the FastMCP changelog** for `3.2.0`. Look for:
   - Changes to `@mcp.tool` argument inspection or schema generation.
   - Changes to `mcp.run()` signature or transport selection.
   - Changes to `Depends` resolution behaviour.
   - Breaking changes to the `lifespan` context type.

2. **Widen the pin in a feature branch — do NOT touch main yet:**
   ```bash
   git checkout -b fastmcp-3.2-eval
   # Edit pyproject.toml: fastmcp~=3.2.0
   uv lock
   ```

3. **Run the full test suite:**
   ```bash
   uv run pytest -q
   ```
   Pass criteria: all tests pass (baseline 472 passed, 4 skipped as of v2).
   Specifically verify:
   - `tests/unit/test_schema_parity.py` — schema shape must still match frozen fixtures.
   - `tests/bdd/test_transport_stdio.py` — stdio handshake unchanged.
   - `tests/bdd/test_transport_http.py` — HTTP + health route unchanged.

4. **Run static analysis:**
   ```bash
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy --strict src/
   ```

5. If all gates pass, update `pyproject.toml` pin, commit `uv.lock`, open a PR.

### Reverting via `uv.lock`

If a bad version is accidentally resolved (e.g. `uv update` pulls a breaking `3.1.x`
patch):

```bash
# Restore the known-good lock from git
git checkout HEAD -- uv.lock

# Reinstall exactly what the lock says — no resolution
uv sync --frozen
```

---

## 5. Install footprint audit

Run `uv tree --depth 1` to inspect direct and transitive dependencies.

Snapshot as of `fastmcp~=3.1.0` (resolved to `3.1.1`), `uv tree --depth 1`:

```
cpp-mcp v0.1.0
├── clang v19.1.7
├── fastmcp v3.1.1
├── mcp v1.27.1
├── mypy v2.1.0 (extra: dev)
├── pytest v9.0.3 (extra: dev)
├── pytest-asyncio v1.3.0 (extra: dev)
├── pytest-bdd v8.1.0 (extra: dev)
├── pytest-cov v7.1.0 (extra: dev)
├── ruff v0.15.13 (extra: dev)
├── neo4j v6.2.0 (extra: graphdb)
└── hypothesis v6.152.7 (group: dev)
```

`uv tree --depth 2` (fastmcp transitive deps):

```
fastmcp v3.1.1
├── authlib v1.7.2
├── cyclopts v4.12.0
├── exceptiongroup v1.3.1
├── httpx v0.28.1
├── jsonref v1.1.0
├── jsonschema-path v0.4.6
├── mcp v1.27.1
├── openapi-pydantic v0.5.1
├── opentelemetry-api v1.41.1
├── packaging v26.2
├── platformdirs v4.9.6
├── py-key-value-aio[filetree, keyring, memory] v0.4.4
├── pydantic[email] v2.13.4
├── pyperclip v1.11.0
├── python-dotenv v1.2.2
├── pyyaml v6.0.3
├── rich v15.0.0
├── uncalled-for v0.3.2
├── uvicorn v0.47.0
├── watchfiles v1.1.1
└── websockets v16.0
```

Total resolved packages: **99** (including runtime + dev + graphdb extras).
Runtime-only (no dev/graphdb extras): approximately 40 packages.

**Footprint note:** FastMCP pulls in `authlib`, `opentelemetry-api`, `httpx`, and
`uvicorn` as runtime deps. These are acceptable for the HTTP transport and observability
readiness (ADR-8 defers middleware but keeps the hook points).

---

## 6. Troubleshooting

### `CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS is required` on startup

The server exits rc=1 with this message on stderr when `CPP_MCP_ALLOWED_ROOTS` is unset
or empty. Set it to at least one existing absolute directory:

```bash
export CPP_MCP_ALLOWED_ROOTS="/path/to/project"
cpp-mcp
```

If the path does not exist you will see:
`CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS entry does not exist or is not a directory: '/path'`

### libclang load failure at first tool call

Symptom: `cpp_get_definition` (or any tool) returns `{"code": "INTERNAL_ERROR", ...}` and
stderr contains `libclang shared library not found`.

Fix: set `CPP_MCP_LIBCLANG_PATH` to the absolute path of your `libclang.so` /
`libclang.dylib`:

```bash
export CPP_MCP_LIBCLANG_PATH=/usr/lib/llvm-19/lib/libclang.so
# macOS:
export CPP_MCP_LIBCLANG_PATH=$(brew --prefix llvm)/lib/libclang.dylib
```

### `/health` returns 404 or connection refused

The `/health` endpoint is only available in HTTP transport mode. If you are running in
stdio mode (the default), there is no HTTP listener — this is expected. Set
`CPP_MCP_TRANSPORT=http` to enable it.

If `CPP_MCP_TRANSPORT=http` is set and the endpoint is unreachable, check that the server
is still running and that you are hitting the correct bind address/port:

```bash
curl http://${CPP_MCP_HTTP_BIND:-127.0.0.1}:${CPP_MCP_HTTP_PORT:-8000}/health
```

### Port already in use (HTTP transport)

```
OSError: [Errno 48] Address already in use
```

Change the port:

```bash
export CPP_MCP_HTTP_PORT=8001
cpp-mcp
```

Or find and kill the conflicting process:

```bash
lsof -ti :8000 | xargs kill -9
```

### Stdout contamination breaks JSON-RPC (stdio mode)

Symptom: the MCP client receives malformed frames; `json.JSONDecodeError` in client logs.

Cause: something printed to stdout before or during tool execution (a third-party library,
`print()` in user code, or libclang writing to stdout).

All logging from cpp-mcp goes to stderr (C-9). If you suspect a third-party lib, run with
`CPP_MCP_LOG_LEVEL=DEBUG` and inspect stderr:

```bash
export CPP_MCP_LOG_LEVEL=DEBUG
echo '...' | cpp-mcp 2>debug.log
cat debug.log
```

### Schema changed after FastMCP update

`tests/unit/test_schema_parity.py` will fail with a diff showing which property changed.
The frozen expected schemas are in `tests/fixtures/expected_schemas/__init__.py`. If the
change is intentional (e.g. a new FastMCP minor added a required field), update the
frozen fixtures and regenerate — but first confirm no wire-contract breakage by running
the full BDD suite.

### `ConfigError: CPP_MCP_TRANSPORT must be 'stdio' or 'http'`

The `CPP_MCP_TRANSPORT` variable only accepts literal `stdio` or `http` (lowercase).
Any other value (including `HTTP`, `Stdio`, `sse`) causes a `ConfigError` at startup.

---

## 7. Registered tools

The 7 tools exposed over both transports (verified against installed `fastmcp 3.1.1`):

| Tool name | Description (summary) |
|---|---|
| `cpp_get_definition` | Resolve a symbol's definition location |
| `cpp_get_references` | Find all references to a symbol |
| `cpp_get_type_info` | Return type information for a cursor position |
| `cpp_get_ast` | Return the AST subtree at a cursor position |
| `cpp_get_header_info` | List includes and macros in a header file |
| `cpp_get_preprocessor_state` | Return preprocessor macro state at a position |
| `cpp_export_to_graphdb` | Export translation-unit graph to a Neo4j database |

All tool names, argument schemas, and error envelopes are frozen by the parity test suite.
Changes to any of these require updating `tests/fixtures/expected_schemas/__init__.py` and
a deliberate schema-bump story.

---

## References

- CHARTER: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/CHARTER.md`
- Design: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/design.md`
- Implementation notes: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/implementation-notes.md`
- Test report: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/test-report.md`
- Deploy notes: `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/deploy-notes.md`
- plan.md §S7 (files-to-change, exit criteria)
- ADR references: adr-4.md (stdio entrypoint), adr-5.md (HTTP path + /health), adr-7.md (lifespan + executor), adr-8.md (observability deferred), adr-11/adr-9.md (FastMCP supersedes v1)
- Cognee tags: `task:fastmcp-migration`, `role:devops`
