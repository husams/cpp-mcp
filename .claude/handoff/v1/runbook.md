# Runbook: C++ Semantic Analysis MCP Server (cpp-mcp)

run_id: cpp-mcp-1
stage: devops
date: 2026-05-16
inputs:
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/design.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/implementation-notes.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/test-report.md
  - /Users/husam/workspace/cpp-mcp/pyproject.toml

---

## 1. Prerequisites

### Python

Python 3.11 or newer is required. Check with:

```bash
python3 --version
```

Recommended: use `uv` for environment management (faster, reproducible).

```bash
# Install uv if not present
curl -Ls https://astral.sh/uv/install.sh | sh
```

### libclang (system library)

`cpp-mcp` uses `clang.cindex` (the libclang Python bindings). The Python package
(`clang>=17,<20`) ships a wrapper but requires the native `libclang` shared library on the system.

**macOS — Xcode Command Line Tools (recommended):**

```bash
xcode-select --install
```

This installs the Xcode toolchain including `libclang.dylib` under
`/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/`.

**macOS — Homebrew LLVM (alternative, gives a specific LLVM version):**

```bash
brew install llvm
# libclang.dylib lands at $(brew --prefix llvm)/lib/libclang.dylib
```

If `cpp-mcp` cannot find libclang at startup, set the path explicitly:

```bash
export CPP_MCP_LIBCLANG_PATH=/opt/homebrew/opt/llvm/lib/libclang.dylib
```

**Linux (Debian/Ubuntu):**

```bash
apt install libclang-dev
# Or for a specific version:
apt install libclang-18-dev
```

**Linux (Fedora/RHEL):**

```bash
dnf install clang-devel
```

---

## 2. Install

### Option A — uv (recommended)

```bash
git clone <repo-url> cpp-mcp
cd cpp-mcp

# Runtime only
uv sync

# With development tools (ruff, mypy, pytest, hypothesis)
uv sync --extra dev

# With Neo4j graphdb support
uv sync --extra graphdb

# All extras
uv sync --extra dev --extra graphdb
```

### Option B — pip in a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate

# Runtime only
pip install -e .

# With dev tools
pip install -e ".[dev]"

# With Neo4j graphdb support
pip install -e ".[graphdb]"
```

---

## 3. Configuration

### Required environment variable

`CPP_MCP_ALLOWED_ROOTS` must be set before starting the server. The server refuses to start
if this variable is absent. It is a colon-separated list of absolute paths; the server will
only parse files whose resolved absolute path falls under one of these roots.

```bash
# Single root
export CPP_MCP_ALLOWED_ROOTS="/home/user/myproject"

# Multiple roots (colon-separated)
export CPP_MCP_ALLOWED_ROOTS="/home/user/myproject:/home/user/shared/libs"
```

### Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `CPP_MCP_DEFAULT_FLAGS` | `-std=c++20 -I. -x c++` | Space-separated compile flags applied when no `compile_commands.json` is found. Parsed via `shlex.split`. |
| `CPP_MCP_CACHE_CAPACITY` | `128` | Number of translation units held in the LRU cache. Reduce to `16` on hosts with less than 4 GiB free RAM. |
| `CPP_MCP_AST_MAX_NODES` | `5000` | Node-count cap for `cpp_get_ast` responses. |
| `CPP_MCP_AST_MAX_BYTES` | `1048576` | Byte cap (1 MiB) for serialized AST responses. |
| `CPP_MCP_LIBCLANG_PATH` | (auto-detected) | Absolute path to `libclang.so`/`libclang.dylib` when auto-detection fails. |
| `CPP_MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` (default) or `http` (P1, not yet implemented). |
| `CPP_MCP_LOG_LEVEL` | `INFO` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## 4. Run as MCP stdio server

The server communicates over stdin/stdout using the MCP JSON-RPC protocol. It is intended to
be launched by an MCP host (Claude Desktop, Claude Code, etc.) rather than run interactively.

```bash
# Using the installed entry point
CPP_MCP_ALLOWED_ROOTS="/path/to/your/project" cpp-mcp

# Using python -m (equivalent)
CPP_MCP_ALLOWED_ROOTS="/path/to/your/project" python -m cpp_mcp

# Using uv run (development)
CPP_MCP_ALLOWED_ROOTS="/path/to/your/project" uv run python -m cpp_mcp
```

The server writes log output to stderr; stdout is reserved for the MCP protocol.

---

## 5. Integration with Claude Code

Add the server to `~/.claude/mcp.json` (Claude Code CLI):

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

Replace `/absolute/path/to/cpp-mcp` with the directory where you cloned/installed cpp-mcp,
and `/absolute/path/to/your/cpp/project` with the root of the C++ codebase you want to analyze.

### Integration with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

On Linux, the config file is `~/.config/Claude/claude_desktop_config.json`.

**Using an installed wheel instead of `uv run`:**

If you installed with `pip install cpp-mcp` (or `pip install -e .`):

```json
{
  "mcpServers": {
    "cpp-mcp": {
      "command": "/path/to/venv/bin/cpp-mcp",
      "env": {
        "CPP_MCP_ALLOWED_ROOTS": "/absolute/path/to/your/cpp/project"
      }
    }
  }
}
```

---

## 6. Optional: Neo4j for cpp_export_to_graphdb

The `cpp_export_to_graphdb` tool exports C++ symbol graphs to a Neo4j database over Bolt.
This tool is only fully functional when the `graphdb` extra is installed.

### Install with graphdb support

```bash
uv sync --extra graphdb
# or
pip install -e ".[graphdb]"
```

### Configure Neo4j connection

Pass `db_uri` and `build_path` directly to the tool call. The Bolt URI format:

```
bolt://localhost:7687
bolt://neo4j:7687
neo4j://localhost:7687
```

No server-level env var is required for the URI; it is passed per-call. For testing or CI,
set `NEO4J_TEST_URI` to enable the real-Neo4j integration test:

```bash
export NEO4J_TEST_URI="bolt://localhost:7687"
uv run pytest -q tests/bdd -k "SC_US_7" -m "neo4j"
```

Neo4j Community Edition 5.x is sufficient. Start a local instance with Docker:

```bash
docker run --rm -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=none \
  neo4j:5
```

---

## 7. Troubleshooting

### libclang not found at startup

Symptom: `OSError: libclang.so: cannot open shared object file` or similar.

Fix:

```bash
# macOS — find the library
find /Applications /opt/homebrew /usr/local -name "libclang.dylib" 2>/dev/null | head -5

# Linux — find the library
find /usr /lib -name "libclang*.so*" 2>/dev/null | head -5

# Set the path explicitly
export CPP_MCP_LIBCLANG_PATH=/opt/homebrew/opt/llvm/lib/libclang.dylib
```

### Server refuses to start: CPP_MCP_ALLOWED_ROOTS not set

Symptom: `ConfigError: CPP_MCP_ALLOWED_ROOTS is required but not set`.

Fix: set the env var to a colon-separated list of absolute paths before launching.

```bash
export CPP_MCP_ALLOWED_ROOTS="/path/to/my/project"
```

### PATH_VIOLATION error on a valid file

Symptom: tool returns `{"code": "PATH_VIOLATION", ...}` for a file that exists.

Causes:
1. The file is outside all configured `CPP_MCP_ALLOWED_ROOTS`.
2. The path contains a `..` component (even if the resolved path is within a root).
3. The path is a symlink that resolves outside an allowed root.

Fix: ensure the file's resolved absolute path (`realpath`) is under one of the allowed roots.
Use `readlink -f /path/to/file` (Linux) or `realpath /path/to/file` (macOS) to check.

### Parse errors in tool responses

Tools return `parse_errors: [...]` in the response body (not as an error envelope) when
libclang parses the file with recoverable diagnostics. This is expected for files with
missing includes. Supply a correct `build_path` pointing to a directory containing
`compile_commands.json` to give libclang the right flags:

```json
{
  "tool": "cpp_get_definition",
  "arguments": {
    "file_path": "/path/to/my/file.cpp",
    "line": 42,
    "col": 10,
    "build_path": "/path/to/my/build/dir"
  }
}
```

### High memory usage

The TU cache holds up to `CPP_MCP_CACHE_CAPACITY` parsed translation units. On large C++
codebases each TU can consume hundreds of MiB. Reduce the cache on memory-constrained hosts:

```bash
export CPP_MCP_CACHE_CAPACITY=16
```

### Tool returns PARSE_ERROR

Symptom: `{"code": "PARSE_ERROR", ...}` — the file produced zero AST nodes and fatal
diagnostics. This usually means the file is binary, completely unparseable, or libclang
cannot find any headers. Check:

1. The file is valid UTF-8 text C++.
2. `CPP_MCP_DEFAULT_FLAGS` or a `compile_commands.json` provides correct include paths.

---

## 8. Available tools (7 total)

| Tool name | Description |
|---|---|
| `cpp_get_definition` | Jump-to-definition: resolves a symbol at (file, line, col) to its definition location. |
| `cpp_get_references` | Find all references to a symbol within the same translation unit. |
| `cpp_get_type_info` | Type information (display, canonical, size, alignment, POD, const, pointer, reference). |
| `cpp_get_ast` | Subtree of the AST rooted at a cursor, with optional depth and line-range filters. |
| `cpp_get_header_info` | Included headers, symbols exported by each, and orphaned-include detection. |
| `cpp_get_preprocessor_state` | Macro definitions, conditional compilation state at a point in the file. |
| `cpp_export_to_graphdb` | Export the C++ symbol graph of a directory to a Neo4j database over Bolt. |

All tools are read-only; the server makes no filesystem writes.

---

References:
- design.md §5 (transport), §6 (config), §4 (error codes)
- implementation-notes.md (Story 1–8 deviations)
- test-report.md (QD-TRANS-001 resolved)
