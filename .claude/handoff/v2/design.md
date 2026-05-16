---
run_id: fastmcp-migration-v2
stage: architect
date: 2026-05-16
sources:
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/scenarios.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-10.md
  - /Users/husam/workspace/wiki/pages/manuals/fastmcp/servers.md
  - /Users/husam/workspace/wiki/pages/manuals/fastmcp/getting-started.md
  - /Users/husam/workspace/wiki/pages/code/cpp-mcp.md
---

# Design: FastMCP Migration (v2)

## 0. ADR index

All 9 OQs from requirements.md are resolved by ADRs in this directory. Every ADR `Status: accepted`.

| ADR file        | Logical ID | Topic                                                            | Resolves    |
|-----------------|------------|------------------------------------------------------------------|-------------|
| `adr-1.md`      | ADR-1 (v2) | ADR-11 file location + lineage handling                          | OQ-1        |
| `adr-2.md`      | ADR-2 (v2) | Error envelope delivery: return-dict + `wrap_tool`               | OQ-2        |
| `adr-3.md`      | ADR-3 (v2) | Dependency injection via FastMCP `Depends`                       | OQ-3        |
| `adr-4.md`      | ADR-4 (v2) | Stdio entrypoint: sync `mcp.run()` from `main()`                 | OQ-4 = OQ-8 |
| `adr-5.md`      | ADR-5 (v2) | HTTP endpoint path `/mcp` + `GET /health` custom route           | OQ-5        |
| `adr-6.md`      | ADR-6 (v2) | Frozen schemas moved to `tests/fixtures/expected_schemas/`       | OQ-6        |
| `adr-7.md`      | ADR-7 (v2) | Lifespan owns `ClangSession`; sync handlers via executor         | OQ-9        |
| `adr-8.md`      | ADR-8 (v2) | Observability middleware deferred to v3                          | OQ-7        |
| `adr-9.md`      | ADR-11 (logical, project-wide) | FastMCP supersedes v1 ADR-10                       | US-M9       |

Note on numbering (per ADR-1): `adr-9.md` carries the logical project-wide identifier **ADR-11** in its header to continue the v1 series (ADR-1..10 + ADR-11). The file name follows the CHARTER blackboard contract (`v2/adr-<n>.md`).

## 1. Goals and constraints

- Replace hand-rolled stdio transport and stub HTTP transport with FastMCP `mcp.run()`.
- Preserve wire contract for 7 tools: names (C-1), argument schemas (C-2), success responses (C-3), error envelope (C-4), 10 env vars (C-5), path-guard (C-6), pytest baseline 327/1 (C-7), thread-affinity (C-8), stderr-only logs (C-9), `cpp-mcp` entry-point (C-10).
- Close v1 US-14/AC-2 (HTTP transport actually works).
- No new auth, no middleware, no observability changes.

## 2. Component map (post-migration)

```
src/cpp_mcp/
├── __main__.py          # python -m cpp_mcp -> main()
├── server/
│   ├── app.py           # build_server() -> FastMCP; main(); registers 7 @mcp.tool functions
│   ├── http_transport.py  # REMOVED (FastMCP handles HTTP)
│   ├── stdio_transport.py # REMOVED (FastMCP handles stdio)
│   └── schemas.py       # REMOVED (FastMCP generates from type hints)
├── core/
│   ├── deps.py          # NEW: get_session(), get_allowed_roots(), AppLifespanContext TypedDict
│   ├── error_envelope.py  # unchanged: wrap_tool decorator, _sanitize_message
│   ├── clang_session.py # +aclose() async method (executor.shutdown(wait=True) + cache.clear)
│   ├── path_guard.py    # unchanged (C-6)
│   └── config.py        # unchanged (C-5)
└── tools/
    ├── definition.py    # converted: async def -> def + @mcp.tool + @wrap_tool + Depends(...)
    ├── references.py
    ├── type_info.py
    ├── ast.py
    ├── header_info.py
    ├── preprocessor_state.py
    └── export_graphdb.py

tests/
├── unit/
│   └── test_schema_parity.py  # NEW: live FastMCP -> frozen fixture diff
├── fixtures/
│   └── expected_schemas/      # NEW: 7 frozen v1 schema dicts (moved from src/.../schemas.py)
└── bdd/                       # existing — unchanged step files for SC_US_1..7
```

Net file count: -3 in `src/`, +2 in `core/` and `tests/`.

## 3. Build-server skeleton (illustrative)

```python
# src/cpp_mcp/server/app.py
from contextlib import asynccontextmanager
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_context
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from cpp_mcp.core.clang_session import ClangSession
from cpp_mcp.core.config import load_config, ConfigError
from cpp_mcp.core.deps import AppLifespanContext

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    cfg = load_config()                          # raises ConfigError -> ADR-4 main() catch
    session = ClangSession(capacity=cfg.cache_capacity)
    try:
        yield AppLifespanContext(
            session=session,
            allowed_roots=cfg.allowed_roots,
            default_flags=cfg.default_flags,
            ast_max_nodes=cfg.ast_max_nodes,
            ast_max_bytes=cfg.ast_max_bytes,
        )
    finally:
        await session.aclose()

def build_server() -> FastMCP:
    mcp = FastMCP(
        "cpp-mcp",
        instructions=None,                       # US-M1/AC-2: leave empty (additive only allowed)
        lifespan=app_lifespan,
        mask_error_details=True,                 # US-M5/AC-4
    )
    # tool functions imported here trigger @mcp.tool registration:
    from cpp_mcp.tools import (
        definition, references, type_info, ast,
        header_info, preprocessor_state, export_graphdb,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    return mcp

def main() -> int:
    try:
        mcp = build_server()
        cfg = load_config()                      # second load: cheap; for transport routing
        if cfg.transport == "http":
            _warn_if_non_loopback(cfg.http_bind)
            mcp.run(transport="http", host=cfg.http_bind, port=cfg.http_port)
        else:
            mcp.run()                            # stdio default
        return 0
    except ConfigError as exc:
        import sys
        from cpp_mcp.core.error_envelope import _sanitize_message
        print(_sanitize_message(str(exc)), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
```

The tool modules use the registration pattern of ADR-7:

```python
# src/cpp_mcp/tools/definition.py
from typing import Annotated, Any
from pathlib import Path
from fastmcp.dependencies import Depends

from cpp_mcp.server._registry import mcp     # or app.py exposes the singleton
from cpp_mcp.core.deps import get_session, get_allowed_roots, get_default_flags
from cpp_mcp.core.error_envelope import wrap_tool
from cpp_mcp.core.clang_session import ClangSession

@mcp.tool(name="cpp_get_definition", description="Resolve a symbol's definition location.")
@wrap_tool(name="cpp_get_definition")
def cpp_get_definition(
    file_path: Annotated[str, "Absolute path to the .cpp/.h source file."],
    line: Annotated[int, "1-based line number of the cursor."],
    column: Annotated[int, "1-based column number of the cursor."],
    *,
    session: ClangSession = Depends(get_session),
    allowed_roots: tuple[Path, ...] = Depends(get_allowed_roots),
    default_flags: tuple[str, ...] = Depends(get_default_flags),
) -> dict[str, Any]:
    return session.executor.submit(
        _do_get_definition, file_path, line, column, allowed_roots, default_flags
    ).result()
```

Decorator stack order (per advisor SC_USM5_1 note): `@mcp.tool` is outermost (registration only); `@wrap_tool` is the outermost *function* decorator (closest to the def). FastMCP invokes the function returned by `wrap_tool`, so the envelope contract owns the return value before FastMCP serializes it.

## 4. Cross-cutting design notes

### 4.1 Schema parity (ADR-6, US-M4)
- `tests/fixtures/expected_schemas/__init__.py` exports `EXPECTED = {tool_name: dict}` for all 7 tools — the verbatim v1 dicts from `server/schemas.py`.
- `tests/unit/test_schema_parity.py`:
  - Builds `mcp = build_server()` (no transport).
  - Gets each tool's schema via the public FastMCP API (`mcp.get_tools()` returns Tool objects with `.input_schema`).
  - Normalises generated and expected schemas with a helper `_normalize(schema) -> dict` that: inlines `$ref`/`$defs`, collapses `["string","null"]` ↔ `{"type":"string"}` + nullable marker, drops `title`, normalises `description` only for emptiness check.
  - Asserts equal `required` sets, equal property name sets, equal property `type` keys post-normalisation, equal enum values, equal defaults, `additionalProperties is False` on every schema, and non-empty descriptions for every argument (US-M4/AC-4).
- **`additionalProperties: false` mechanism (EC-7).** FastMCP's auto-generation defaults to `additionalProperties: true` for plain function arguments. Two options for the developer:
  1. Wrap each tool's arguments in a Pydantic `BaseModel` with `model_config = ConfigDict(extra="forbid")`, then use that as the sole argument.
  2. Keep flat arguments and override the schema post-hoc: set `additionalProperties: False` via FastMCP's `@mcp.tool(output_schema=..., input_schema_overrides={"additionalProperties": False})` if supported, else use a small `@strict_schema` wrapper.
  - Senior-developer chooses; option (1) is cleaner for mypy --strict. The parity test fails if either approach drifts.

### 4.2 Error envelope (ADR-2, US-M5)
- `wrap_tool` is unchanged. It always returns a `dict` matching `ToolEnvelope` TypedDict:
  ```python
  class ToolEnvelope(TypedDict, total=False):
      # success path:
      ...payload fields...
      cache_hit: bool
      flags_source: str
      request_id: str
      # error path:
      code: str
      message: str
      tool: str
  ```
- FastMCP serialises the dict to `structuredContent` (plus a mirrored JSON text block in `content[]`). BDD step files asserting `response["structuredContent"]["code"] == "PATH_VIOLATION"` work directly.
- `mask_error_details=True` (US-M5/AC-4): only matters if an exception bypasses `wrap_tool` (EC-3 / SC_USM5_6). With wrap_tool outermost, this is bug-only territory; the masking ensures no stack-trace leak.

### 4.3 Concurrency (ADR-7, US-M7)
- FastMCP runs sync handlers on `anyio.to_thread.run_sync` workers. The number of FastMCP workers is irrelevant to libclang correctness because every handler dispatches via `session.executor.submit(...).result()`, where `session.executor = ThreadPoolExecutor(max_workers=1)`.
- Double thread-hop is intentional: FastMCP pool = request boundary; `ClangSession.executor` = libclang serializer.
- Regression: scenarios SC_USM7_3 launches 3 concurrent HTTP `cpp_get_ast` requests on the same file; asserts `parse_count == 1` (cache hit after first).

### 4.4 Lifespan invocation count (US-M6/AC-4, EC-13)
- `mcp.run()` (sync) calls the lifespan exactly once for the process. Stdio EOF triggers normal exit; HTTP transport runs until SIGTERM. Both paths invoke the `finally:` branch of `app_lifespan` exactly once → `session.aclose()` once.

### 4.5 Non-loopback bind warning (US-M2/AC-3, EC-2)
- `_warn_if_non_loopback(bind)` lives in `core/config.py`. Loopback set: `{"127.0.0.1", "::1", "localhost"}`. Anything else (including `0.0.0.0` and `::`) emits a single WARNING log line on stderr before `mcp.run()`. Resolves EC-2 (IPv6 `::` is non-loopback → WARNING).

### 4.6 stdout discipline (C-9, US-M1/AC-4)
- `logging.basicConfig(stream=sys.stderr, level=os.environ.get("CPP_MCP_LOG_LEVEL", "INFO"))` runs first in `main()` before any import that might log.
- FastMCP's internal logger is reconfigured to stderr by setting `logging.getLogger("fastmcp").handlers = [...]` at startup.
- EC-5 (third-party libclang writes warnings to stdout): mitigation deferred — the v1 baseline already accepts this risk (libclang typically writes to stderr); no change in v2.

### 4.7 Type hints & mypy --strict (US-M3/AC-5)
- All tool functions return `dict[str, Any]` (TypedDict `ToolEnvelope` for tooling clarity but `dict[str, Any]` at signature to satisfy FastMCP's structured-content expectation).
- DI parameter defaults use `Depends(get_x)` — mypy is satisfied because `Depends` returns the resolver's return-type annotation.
- `AppLifespanContext` is a `TypedDict` in `core/deps.py`; `get_context().lifespan_context` is cast to it.
- `from __future__ import annotations` NOT added (Python 3.12 project; native syntax used).

## 5. Story → ADR → file map (traceability seed for plan.md)

| Story | ACs                       | Driving ADRs        | Files touched                                                                                  |
|-------|---------------------------|---------------------|------------------------------------------------------------------------------------------------|
| US-M1 | AC-1..5                   | ADR-4, ADR-7        | `server/app.py` (new build_server, main), `server/stdio_transport.py` (DELETE)                |
| US-M2 | AC-1..5                   | ADR-5               | `server/app.py` (custom_route /health, http branch in main), `server/http_transport.py` (DELETE) |
| US-M3 | AC-1..5                   | ADR-3, ADR-7        | `tools/*.py` (7 files: add @mcp.tool, convert async→sync, add Depends), `server/app.py` (remove _TOOL_SPECS/_HANDLERS) |
| US-M4 | AC-1..4                   | ADR-6               | `server/schemas.py` (DELETE), `tests/fixtures/expected_schemas/__init__.py` (NEW), `tests/unit/test_schema_parity.py` (NEW) |
| US-M5 | AC-1..5                   | ADR-2               | `core/error_envelope.py` (unchanged), `tools/*.py` (apply @wrap_tool), `server/app.py` (mask_error_details=True) |
| US-M6 | AC-1..5                   | ADR-7, ADR-4        | `server/app.py` (app_lifespan), `core/clang_session.py` (+aclose), `core/deps.py` (NEW: AppLifespanContext) |
| US-M7 | AC-1..4                   | ADR-7               | `tools/*.py` (sync def + executor.submit.result), regression test under `tests/bdd/`         |
| US-M8 | AC-1..3                   | (no ADR)            | `pyproject.toml` (fastmcp~=3.1.0), `uv.lock`, `runbook.md`                                    |
| US-M9 | AC-1..4                   | ADR-1, ADR-9        | `v2/adr-9.md` (NEW), `v1/adr-10.md` (status line edit), `[[pages/code/cpp-mcp]]` ADR table   |

## 6. Risks and mitigations (architect-confirmed)

| ID  | Risk                                          | Mitigation in this design                                                              |
|-----|-----------------------------------------------|----------------------------------------------------------------------------------------|
| R-1 | FastMCP minor-version breakage                | US-M8 pin; runbook upgrade checklist                                                   |
| R-2 | Schema drift                                  | ADR-6 + test_schema_parity.py with normalisation; CI gate                              |
| R-3 | Concurrent libclang access                    | ADR-7 single-worker executor; SC_USM7_3 regression test                                |
| R-4 | Error envelope vs ToolError shape mismatch    | ADR-2 return-dict; mask_error_details=True defense-in-depth                            |
| R-5 | Sync vs async handler regression              | ADR-7 uniformly sync; SC_USM7_3 verifies serialization                                 |
| R-6 | Console-script regression                     | `main() -> int` signature unchanged; smoke test in BDD `@SC_C10_ENTRY`                |
| R-7 | Schema descriptions missing                   | US-M4/AC-4 + parity test fails on empty descriptions                                   |
| R-8 | Install footprint bloat                       | Audit `uv tree` post-migration; document in `runbook.md`                               |

## 7. Out-of-scope (re-stated)

- FastMCP middleware (LoggingMiddleware, TimingMiddleware) — deferred to v3 (ADR-8).
- HTTP authentication — deferred (US-M2/AC-5; v1 ADR-10 carry-over).
- Renaming tools, adding tool arguments, altering path-guard semantics (C-1, C-2, C-6).

## 8. Exit criteria for senior-developer dispatch

- All 9 ADRs `Status: accepted` (verified by CHARTER invariant I2 — see below).
- `design.md` (this file) lists story→ADR→files map (§5) for plan.md authoring.
- `core/deps.py` and `AppLifespanContext` TypedDict design captured (§3, ADR-3).
- Concurrency model captured (§4.3, ADR-7).
- Schema parity test design captured (§4.1, ADR-6).

## 9. References

- requirements.md, scenarios.md (this run)
- v1/adr-10.md (superseded by ADR-11; see ADR-9)
- v1/adr-2.md (libclang threading invariant; reaffirmed by ADR-7)
- v1/adr-8.md (error envelope; preserved by ADR-2)
- `[[pages/manuals/fastmcp/servers]]`, `[[pages/manuals/fastmcp/getting-started]]`, `[[pages/manuals/fastmcp/cli]]`
- `[[pages/code/cpp-mcp]]`
- Cognee dataset: `agent-memory` (tags: `task:fastmcp-migration`, `role:architect`)
