# cpp-mcp — C++ Semantic Analysis MCP Server

A local Python MCP (Model Context Protocol) server that wraps `libclang` to expose seven read-only C++ semantic analysis tools to LLM agents. Every tool call is stateless — no global project state is held between calls. A TU (Translation Unit) LRU cache avoids redundant parses.

**Transport layer:** cpp-mcp uses [FastMCP](https://github.com/jlowin/fastmcp) (`~=3.1.0`) as its MCP transport layer. FastMCP provides production-quality stdio and HTTP/SSE transports, `@mcp.tool` decorator registration, auto-generated JSON schemas from type hints, `lifespan` context management for the libclang session, and `Depends`-based dependency injection. See [`.claude/handoff/v2/runbook.md`](.claude/handoff/v2/runbook.md) for startup instructions, upgrade-check procedure, and install-footprint audit.

**618 tests pass** (unit + BDD). Python 3.11+. Tested on macOS and Linux.

---

## Prerequisites

- **Python 3.11+**
- **libclang 17–19** (system library — the Python `clang` package wraps it but does not bundle it)
- **`uv`** (recommended) or pip

**macOS — Xcode Command Line Tools (recommended):**

```bash
xcode-select --install
```

**macOS — Homebrew LLVM (alternative):**

```bash
brew install llvm
export CPP_MCP_LIBCLANG_PATH=/opt/homebrew/opt/llvm/lib/libclang.dylib
```

**Linux (Debian/Ubuntu):**

```bash
apt install libclang-dev
```

---

## Install

```bash
git clone <repo-url> cpp-mcp
cd cpp-mcp

# Runtime only
uv sync

# With development tools (ruff, mypy, pytest, hypothesis)
uv sync --extra dev

# With Neo4j graphdb support (for ingest_code)
uv sync --extra graphdb-neo4j

# With IndraDB graphdb support (for ingest_code)
uv sync --extra graphdb-indradb

# With both graphdb backends
uv sync --extra graphdb
```

Or with pip in a virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Configuration (required before starting)

`CPP_MCP_ALLOWED_ROOTS` must be set. The server refuses to start if it is absent.

```bash
export CPP_MCP_ALLOWED_ROOTS="/absolute/path/to/your/cpp/project"
```

Multiple roots (colon-separated):

```bash
export CPP_MCP_ALLOWED_ROOTS="/path/to/repo-a:/path/to/repo-b"
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `CPP_MCP_ALLOWED_ROOTS` | **yes** | — | Colon-separated absolute paths the server may read. |
| `CPP_MCP_DEFAULT_FLAGS` | no | `-std=c++20 -I. -x c++` | Compile flags when no `compile_commands.json` is found. |
| `CPP_MCP_CACHE_CAPACITY` | no | `128` | LRU cache size. Use `16` on hosts with less than 4 GiB free RAM. |
| `CPP_MCP_AST_MAX_NODES` | no | `5000` | Node-count ceiling for `get_ast`. |
| `CPP_MCP_AST_MAX_BYTES` | no | `1048576` | Byte ceiling (1 MiB) for serialized AST responses. |
| `CPP_MCP_LIBCLANG_PATH` | no | (auto-detected) | Absolute path to `libclang.so`/`libclang.dylib`. |
| `CPP_MCP_LOG_LEVEL` | no | `INFO` | Python logging level. |

---

## Run (stdio transport)

```bash
CPP_MCP_ALLOWED_ROOTS="/path/to/your/project" cpp-mcp

# Or with uv run (development)
CPP_MCP_ALLOWED_ROOTS="/path/to/your/project" uv run python -m cpp_mcp
```

Log output goes to stderr; stdout is reserved for the MCP protocol.

## Run (HTTP transport)

```bash
CPP_MCP_ALLOWED_ROOTS="/path/to/your/project" uv run python -m cpp_mcp http
```

MCP endpoint: `POST http://127.0.0.1:8000/mcp`. Health check: `GET http://127.0.0.1:8000/health`.

See [`.claude/handoff/v2/runbook.md`](.claude/handoff/v2/runbook.md) for full startup and configuration details.

---

## Integrate with Claude Code

Add to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "cpp-mcp": {
      "command": "uv",
      "args": ["--project", "/absolute/path/to/cpp-mcp", "run", "python", "-m", "cpp_mcp"],
      "env": {
        "CPP_MCP_ALLOWED_ROOTS": "/absolute/path/to/your/cpp/project",
        "CPP_MCP_DEFAULT_FLAGS": "-std=c++20 -I. -x c++"
      }
    }
  }
}
```

**Claude Desktop (macOS):** add the same JSON to `~/Library/Application Support/Claude/claude_desktop_config.json`.
**Claude Desktop (Linux):** use `~/.config/Claude/claude_desktop_config.json`.

---

## Tools (7 total — all read-only)

| Tool | What it returns |
|---|---|
| `get_definition` | Jump-to-definition: `{file, line, col, usr, definition_found}` |
| `get_references` | All references in the current TU: `[{file, line, col, context_snippet}]` |
| `get_type_info` | `{display_type, canonical_type, size_bytes, alignment_bytes, is_pod, is_const, is_reference, is_pointer}` — resolves `auto` and templates |
| `get_ast` | AST subtree with optional `depth`, `start_line`/`end_line`, and `format` (`json` or `graph`) |
| `get_header_info` | Include graph + exported symbols + `missing_includes` + `orphaned_includes` |
| `get_preprocessor_state` | Active macros (including transitive) + evaluated `#ifdef`/`#ifndef` conditionals |
| `ingest_code` | Export symbol graph to Neo4j or IndraDB (requires `--extra graphdb`) |

Every successful response includes `flags_source` (`"compilation_db"` or `"default"`), `cache_hit` (bool), and `request_id` (UUID4).

Errors always use a structured envelope:

```json
{ "code": "PATH_VIOLATION", "message": "...", "tool": "get_definition", "request_id": "..." }
```

Valid codes: `FILE_NOT_FOUND`, `INVALID_POSITION`, `INVALID_RANGE`, `INVALID_ARGUMENT`, `PATH_VIOLATION`, `DEPENDENCY_MISSING`, `DB_UNREACHABLE`, `PARSE_ERROR`, `INTERNAL_ERROR`.

---

## Graph database backends

`ingest_code` supports two backends selected automatically by URI scheme.

### Neo4j (default — Bolt)

Supported schemes: `bolt://`, `bolt+s://`, `bolt+ssc://`, `neo4j://`, `neo4j+s://`, `neo4j+ssc://`.

```bash
# Install driver
uv sync --extra graphdb-neo4j

# Start a local Neo4j instance
docker run --rm -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=none neo4j:5
```

License posture: Neo4j Community Edition daemon is GPLv3; the `neo4j` Python Bolt driver is Apache 2.0.

To enable the real-Neo4j integration test: `export NEO4J_TEST_URI="bolt://localhost:7687"`.

### IndraDB (alternative — gRPC)

Supported schemes: `indradb://`, `grpc://`, `indradb+grpc://`. Default port: 27615.

```bash
# Install driver
uv sync --extra graphdb-indradb

# Start a local IndraDB instance (see ## Local development (IndraDB) below)
indradb-server memory
```

License posture: IndraDB daemon and Python client are MPL-2.0 (file-level copyleft; does not propagate to cpp-mcp callers).

To enable the real-IndraDB integration test: `export INDRADB_TEST_URI="indradb://localhost:27615"`.

### Both backends

```bash
uv sync --extra graphdb   # installs neo4j + indradb drivers
```

See [`.claude/handoff/v3/runbook.md`](.claude/handoff/v3/runbook.md) for the full URI scheme table, daemon bring-up commands, error-code reference, and license posture details.

---

## Local development (IndraDB)

The canonical path for running a local IndraDB daemon is `cargo install indradb`.
There is no supported Docker image (the `indradb/indradb` Docker Hub namespace is
empty — see ADR-16).

**One-time setup (requires Rust toolchain):**

```bash
# Install rustup if not already present
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install the IndraDB server binary (~30 seconds on a fast machine)
cargo install indradb
```

**Start the in-memory daemon (no disk state, ideal for testing):**

```bash
indradb-server memory
```

The gRPC endpoint listens on `127.0.0.1:27615` by default.

**Run integration tests against the live daemon:**

```bash
export INDRADB_TEST_URI="grpc://127.0.0.1:27615"
uv run pytest -m "integration and indradb" tests/integration/test_indradb_e2e.py -q
```

Or let the fixture autostart the daemon for you (requires `indradb-server` on `$PATH`):

```bash
INDRADB_AUTOSTART=1 uv run pytest -m "integration and indradb" tests/integration/test_indradb_e2e.py -q
```

---

## Testing

```bash
uv run pytest -q
```

Expected: 618 passed, 6 skipped (env-gated: `INDRADB_TEST_URI`, `NEO4J_TEST_URI`, `COGNEE_BASE_URL` unset).

Full pre-release verification:

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy --strict src
uv run pytest -q
```

---

## Migration from 0.2.x

In v0.3.0 all seven MCP tool wire names were renamed. The `cpp_` prefix was dropped and
`cpp_export_to_graphdb` was renamed to `ingest_code`. There are **no compatibility aliases**;
0.2.x clients will receive an MCP `tool not found` error until they are updated.

| 0.2.x name (old) | 0.3.0 name (new) |
|---|---|
| `cpp_get_definition` | `get_definition` |
| `cpp_get_references` | `get_references` |
| `cpp_get_type_info` | `get_type_info` |
| `cpp_get_ast` | `get_ast` |
| `cpp_get_header_info` | `get_header_info` |
| `cpp_get_preprocessor_state` | `get_preprocessor_state` |
| `cpp_export_to_graphdb` | `ingest_code` |

---

## Troubleshooting

**libclang not found:** set `CPP_MCP_LIBCLANG_PATH` to the absolute path of `libclang.dylib`/`libclang.so`.

**Server refuses to start (`CPP_MCP_ALLOWED_ROOTS not set`):** export the variable before launching.

**`PATH_VIOLATION` on a valid file:** run `realpath /path/to/file` and confirm the resolved path is under one of your allowed roots. Paths with `..` components are always rejected.

**High memory usage:** set `CPP_MCP_CACHE_CAPACITY=16`.

**`PARSE_ERROR` response:** file produced zero AST nodes. Confirm it is valid UTF-8 C++ and that include paths are reachable via `CPP_MCP_DEFAULT_FLAGS` or a `compile_commands.json`.
