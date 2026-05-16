---
task: fastmcp-migration
story: S3 — Convert 7 tool handlers to @mcp.tool + sync + executor
role: developer
date: 2026-05-16
---

## Skills loaded
- `python-conventions` (loaded; `uv.lock` present, ruff/mypy/pytest toolchain)

## Skills considered but not loaded
- `implement-story` — not loaded; implementation pattern was clear from plan.md and prior S1/S2 context
- `cpp-conventions` — not loaded; project is Python, no C++ code being written
- `google-agents-cli-workflow` — not loaded; not an ADK agent task
- `claude-api` — not loaded; no Anthropic SDK usage

## Commands run

### Orientation
```bash
ls src/cpp_mcp/tools/      # confirmed tool files present from prior S1/S2 work
ls src/cpp_mcp/server/     # confirmed _registry.py, app.py present
uv run python -c "from cpp_mcp.server.app import build_server; ..."  # verified 7 tools registered
uv run python -c "... tools[0].parameters ..."  # confirmed parameters dict structure
```

### Code generation
- Created `tests/fixtures/expected_tool_descriptions.py`
- Created `tests/unit/test_tool_registration.py`
- Created `tests/unit/test_executor_dispatch.py`

### Syntax fix
```python
# Bulk regex fix for ctx["response"] =\n    FUNC(...) syntax errors in 5 BDD files
# Manual fix for test_tu_cache_bdd.py (orphaned block)
python3 -m py_compile tests/bdd/test_get_ast.py ...  # verified all OK
```

### Format gate (pass 1)
```bash
uv run ruff format .   # 12 files reformatted
uv run ruff format --check .   # 70 files already formatted — PASS
```

### Lint gate (pass 1 — fail)
```bash
uv run ruff check .
# B008 (7x): Depends(...) in argument defaults
# F401 (20x): unused asyncio imports from bulk replacement
```

### Lint gate (pass 2 — pass)
```bash
uv run ruff check --fix .   # auto-fixed F401 (22 fixable)
# Added ignore = ["B008"] to pyproject.toml
uv run ruff check .   # All checks passed
```

### Mypy gate (pass 1 — fail)
```bash
uv run mypy --strict src/
# 15 errors: untyped-decorator (7x), no-any-return (7x), build_app attr-defined (1x)
```

### Mypy gate (pass 2 — fail)
```bash
# Fixed http_transport.py (build_app → build_server)
# Added # type: ignore[untyped-decorator] to @mcp.tool( lines
# Added result: dict[str, Any] = ... in get_ast.py
uv run mypy --strict src/
# 1 error: unused type: ignore[assignment] in get_ast.py
```

### Mypy gate (pass 3 — pass)
```bash
# Removed unnecessary # type: ignore[assignment] from get_ast.py
uv run mypy --strict src/
# Success: no issues found in 31 source files
```

### Static checks (pass)
```bash
! grep -rn "^async def " src/cpp_mcp/tools/   # PASS
! grep -rn "_TOOL_SPECS\|_HANDLERS" src/cpp_mcp/server/   # Initially FAIL (comment in app.py)
# Removed shim names from docstring comment
! grep -rn "_TOOL_SPECS\|_HANDLERS" src/cpp_mcp/server/   # PASS
```

### Test gate (pass 1 — fail)
```bash
uv run pytest -q
# 1 failed: test_http_transport_responds_on_mcp_endpoint_us14ac2
# AttributeError: 'FastMCP' object has no attribute 'create_initialization_options'
# Root: http_transport.py passed FastMCP to StreamableHTTPSessionManager which expects raw MCP server
```

### http_transport.py fix
- Tried `mcp.http_app()` with `additional_routes` — no such parameter
- Wrapped `mcp.http_app()` with Starlette + custom lifespan that delegates to `mcp_app.lifespan`
- First attempt used `contextlib.asynccontextmanager(mcp_app.lifespan)(app)` — wrong (already a CM)
- Fixed to `async with mcp_app.lifespan(app):`

### Test gate (pass 2 — pass)
```bash
uv run pytest -q
# 378 passed, 4 skipped, 2 xpassed, 4 warnings — PASS
```

### xfail cleanup (S2 deferred markers)
```bash
# Removed _S2_DEFERRED_TESTS dict and pytest_collection_modifyitems from tests/bdd/conftest.py
uv run pytest -q
# 380 passed, 4 skipped, 0 xpassed, 4 warnings — PASS (clean)
```

## Deviations from plan.md
1. `http_transport.py` update was out-of-plan scope but required by `build_app` removal
2. `pyproject.toml` B008 ignore added for FastMCP Depends pattern
3. mypy `type: ignore[untyped-decorator]` needed on `@mcp.tool(...)` lines because `mcp: Any`

## Tool failures / retries
- Bulk syntax-error fix script created `ctx["response"] =\n    FUNC(...)` errors in 7+ files — required second regex script to fix
- `type: ignore[misc]` was wrong error code; needed `type: ignore[untyped-decorator]`
- `mcp_app.lifespan` delegation: two failed attempts before correct `async with mcp_app.lifespan(app):` pattern
