# cpp-mcp — C++ Semantic Analysis MCP Server

A local Python MCP (Model Context Protocol) server that wraps `libclang` to expose seven read-only C++ semantic analysis tools to LLM agents. Every tool call is stateless — no global project state is held between calls. A TU (Translation Unit) LRU cache avoids redundant parses.

**Transport layer:** cpp-mcp uses [FastMCP](https://github.com/jlowin/fastmcp) (`~=3.1.0`) as its MCP transport layer. FastMCP provides production-quality stdio and HTTP/SSE transports, `@mcp.tool` decorator registration, auto-generated JSON schemas from type hints, `lifespan` context management for the libclang session, and `Depends`-based dependency injection. See [`.claude/handoff/v2/runbook.md`](.claude/handoff/v2/runbook.md) for startup instructions, upgrade-check procedure, and install-footprint audit.

**453 tests pass** (unit + BDD). Python 3.11+. Tested on macOS and Linux.

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

# With Neo4j graphdb support (for cpp_export_to_graphdb)
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
| `CPP_MCP_AST_MAX_NODES` | no | `5000` | Node-count ceiling for `cpp_get_ast`. |
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
| `cpp_get_definition` | Jump-to-definition: `{file, line, col, usr, definition_found}` |
| `cpp_get_references` | All references in the current TU: `[{file, line, col, context_snippet}]` |
| `cpp_get_type_info` | `{display_type, canonical_type, size_bytes, alignment_bytes, is_pod, is_const, is_reference, is_pointer}` — resolves `auto` and templates |
| `cpp_get_ast` | AST subtree with optional `depth`, `start_line`/`end_line`, and `format` (`json` or `graph`) |
| `cpp_get_header_info` | Include graph + exported symbols + `missing_includes` + `orphaned_includes` |
| `cpp_get_preprocessor_state` | Active macros (including transitive) + evaluated `#ifdef`/`#ifndef` conditionals |
| `cpp_export_to_graphdb` | Export symbol graph to Neo4j via Bolt (requires `--extra graphdb`) |

Every successful response includes `flags_source` (`"compilation_db"` or `"default"`), `cache_hit` (bool), and `request_id` (UUID4).

Errors always use a structured envelope:

```json
{ "code": "PATH_VIOLATION", "message": "...", "tool": "cpp_get_definition", "request_id": "..." }
```

Valid codes: `FILE_NOT_FOUND`, `INVALID_POSITION`, `INVALID_RANGE`, `INVALID_ARGUMENT`, `PATH_VIOLATION`, `DEPENDENCY_MISSING`, `DB_UNREACHABLE`, `PARSE_ERROR`, `INTERNAL_ERROR`.

---

## Graph database backends

`cpp_export_to_graphdb` supports two backends selected automatically by URI scheme.

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

# Start a local IndraDB instance (docker compose fragment provided)
docker compose -f tests/fixtures/indradb-compose.yml up -d
```

License posture: IndraDB daemon and Python client are MPL-2.0 (file-level copyleft; does not propagate to cpp-mcp callers).

To enable the real-IndraDB integration test: `export INDRADB_TEST_URI="indradb://localhost:27615"`.

### Both backends

```bash
uv sync --extra graphdb   # installs neo4j + indradb drivers
```

See [`.claude/handoff/v3/runbook.md`](.claude/handoff/v3/runbook.md) for the full URI scheme table, daemon bring-up commands, error-code reference, and license posture details.

---

## Testing

```bash
uv run pytest -q
```

Expected: 327 passed, 1 skipped (Neo4j integration test — skipped when `NEO4J_TEST_URI` is unset).

Full pre-release verification:

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy --strict src
uv run pytest -q
```

---

## Troubleshooting

**libclang not found:** set `CPP_MCP_LIBCLANG_PATH` to the absolute path of `libclang.dylib`/`libclang.so`.

**Server refuses to start (`CPP_MCP_ALLOWED_ROOTS not set`):** export the variable before launching.

**`PATH_VIOLATION` on a valid file:** run `realpath /path/to/file` and confirm the resolved path is under one of your allowed roots. Paths with `..` components are always rejected.

**High memory usage:** set `CPP_MCP_CACHE_CAPACITY=16`.

**`PARSE_ERROR` response:** file produced zero AST nodes. Confirm it is valid UTF-8 C++ and that include paths are reachable via `CPP_MCP_DEFAULT_FLAGS` or a `compile_commands.json`.
