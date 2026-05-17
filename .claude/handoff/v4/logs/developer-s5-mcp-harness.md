---
task: cpp-mcp-v4
story: S5 in-memory-client-harness-and-integration-scaffold
role: developer
date: 2026-05-17
model: claude-sonnet-4-6
---

# Developer Session Log — S5

## Skills loaded

- `python-conventions` — loaded before writing any code; confirmed ruff/mypy/pytest toolchain and conventions
- `implement-story` — considered but not loaded; story is straightforward file-by-file implementation with clear plan
- `cpp-conventions` — not loaded; project is Python, not C++

## Orientation phase

Read CHARTER.md, plan.md, design.md, adr-18.md, scenarios.md in parallel.
Read existing `tests/conftest.py` and `pyproject.toml` to understand current state.
Confirmed `tests/integration/` directory exists with `__init__.py` and `test_install.py` (from S2).
Read `src/cpp_mcp/server/app.py` lines 1-102 to understand `build_server()` API.
Read `tests/bdd/test_transport_stdio.py` and `test_concurrent_ast.py` to understand existing `call_tool` usage patterns.

## Implementation steps

### Step 1 — Probe in-process client

```bash
uv run python -c "
import os; os.environ['CPP_MCP_ALLOWED_ROOTS'] = '/Users/husam/workspace/cpp-mcp/test-repo'
from fastmcp import Client; from cpp_mcp.server.app import build_server; import asyncio
async def test():
    server = build_server()
    async with Client(server) as client:
        tools = await client.list_tools()
        print([t.name for t in tools])
asyncio.run(test())" 
# Output: ['cpp_get_definition', 'cpp_get_references', 'cpp_get_type_info', 'cpp_get_ast', 'cpp_get_header_info', 'cpp_get_preprocessor_state', 'cpp_export_to_graphdb']
```

Discovered: `CPP_MCP_ALLOWED_ROOTS` must be set before `Client(server).__aenter__()` calls lifespan's `load_config()`.

### Step 2 — Probe tool result structure

Confirmed `result.data` is a dict and `result.is_error` is a bool. For `cpp_export_to_graphdb` with `bolt://invalid`: returns `{'code': 'DEPENDENCY_MISSING', ...}` (neo4j not installed in dev venv).

### Step 3 — Called advisor

Advisor confirmed:
1. Set `CPP_MCP_ALLOWED_ROOTS` in fixture body (not monkeypatch — session-scoped)
2. Use distinct file paths for cache-hit toggle vs all-tools smoke
3. Assert `code in {"DB_UNREACHABLE", "DEPENDENCY_MISSING"}` for export smoke

### Step 4 — Implement

Added `mcp_client` fixture to `tests/conftest.py`, registered `integration` marker in `pyproject.toml`, created three new files.

### Step 5 — First integration test run (FAIL — deadlock)

```
uv run pytest -m integration tests/integration/test_harness_smoke.py::test_sc_v4_1_01_mcp_client_is_connected -v
# Process stuck after "PASSED" label never appeared; killed after 20s
```

Root cause: pytest-asyncio 1.3.0 defaults `asyncio_default_test_loop_scope=function`. Session fixture's Client lives on session event loop; test coroutine runs on function-scoped loop. Cross-loop `await` → deadlock.

### Step 6 — Fix event loop scope

Added to pyproject.toml:
```toml
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
```

Also added `loop_scope="session"` kwarg to `@pytest_asyncio.fixture` decorator.

### Step 7 — All gates passed

```
uv run ruff format --check ... → 0
uv run ruff check ... → 0
uv run mypy src/ → 0 (30 files)
uv run pytest -q → 602 passed, 6 skipped, 11 deselected
uv run pytest -m integration test_harness_smoke.py test_all_tools_smoke.py -q → 9 passed
uv run pytest --collect-only -m integration -q | grep -E 'test_harness_smoke|test_all_tools_smoke' → 9 items
```

## Commands run + outcomes

| Command | Outcome |
|---|---|
| `uv run ruff format --check tests/conftest.py tests/integration pyproject.toml` | 0 (pass 1 reformatted test_all_tools_smoke.py, pass 2 clean) |
| `uv run ruff check tests/conftest.py tests/integration` | 0 |
| `uv run mypy src/` | 0, 30 files |
| `uv run pytest -q` | 602 passed, 6 skipped |
| `uv run pytest -m integration test_harness_smoke.py test_all_tools_smoke.py -q` | 9 passed |

## Deviations from plan.md

See implementation-notes.md §S5 Deviations — reproduced here for completeness:
1. `asyncio_default_test_loop_scope = "session"` added (pytest-asyncio deadlock fix)
2. `loop_scope="session"` on fixture decorator
3. `CPP_MCP_ALLOWED_ROOTS` managed in fixture body
4. fmt-c.cc used for cache-hit toggle (cold cache isolation)
5. Export smoke asserts set membership, not specific code

## Tool failures or retries

- First integration run deadlocked (cross-loop await). Diagnosed via `ps aux` (pytest at 0% CPU) and confirmed killed with SIGTERM. Fixed with session loop scope settings. No further retry needed.
- `ruff format` reformatted `test_all_tools_smoke.py` on first pass (long assert line); second pass clean.
