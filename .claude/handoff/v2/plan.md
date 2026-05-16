---
run_id: fastmcp-migration-v2
stage: senior-developer
date: 2026-05-16
sources:
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/scenarios.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/design.md
  - /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/adr-1.md .. adr-9.md
---

# Plan: FastMCP Migration (v2)

## Goal

Migrate the cpp-mcp server from the hand-rolled stdio transport + stub HTTP transport to FastMCP `mcp.run()`, preserving the wire contract for all 7 tools (names, schemas, success/error envelopes, env vars, path-guard, stderr-only logs) while closing v1 US-14/AC-2 (real HTTP transport) and removing ~300 lines of glue code.

## Toolchain (canonical, project-detected)

- Package manager: `uv` (project has `uv.lock` per US-M8; if not yet committed, story S1 ensures it).
- Formatter: `uv run ruff format .`
- Linter: `uv run ruff check .`
- Type checker (strict on `src/`): `uv run mypy --strict src/`
- Test runner: `uv run pytest -q`
- Build smoke: `uv run python -m build`

Every story uses the same exit-criteria command set unless explicitly extended (story-specific commands listed under that story's `exit-criteria:`).

## Compatibility gates (apply to every story; gating, not exit-criteria)

- C-1..C-10 from `requirements.md`. The aggregate pytest baseline `327 passed, 1 skipped` is the global non-regression gate — every story must run `uv run pytest -q` and end at that count (or higher when a story explicitly adds tests, in which case the baseline becomes the new floor).
- Charter invariant I3: every story below has an `exit-criteria` block of executable commands.
- Charter invariant I2: all 9 ADRs already `Status: accepted` (verified at dispatch).

## Story ordering and parallel-safety

```
S1 (US-M8, US-M9)  ─┐
                    ├─►  S2 (US-M6 + US-M1 stdio skeleton) ──►  S3 (US-M3 + US-M7 tools)  ──►  S4 (US-M5 envelope)  ──►  S5 (US-M4 schema parity)  ──►  S6 (US-M2 HTTP)  ──►  S7 (cleanup + docs)
S1 parallel-safe with no other story (touches pyproject + ADR files only)
S2..S6 are strictly sequential — each builds on the previous file state
S7 parallel-safe with S6 (S7 touches runbook + wiki only)
```

Parallel-safe count: 2 (S1, S7). The middle 5 stories must run sequentially because they mutate overlapping files (`server/app.py`, `tools/*.py`).

---

## Story S1 — Pin `fastmcp` and supersede ADR-10

Covers AC: US-M8/AC-1, US-M8/AC-2, US-M8/AC-3, US-M9/AC-1, US-M9/AC-2, US-M9/AC-3, US-M9/AC-4.
Driving ADRs: ADR-1 (v2), ADR-9 (v2 = logical ADR-11).

### Files to change
- `/Users/husam/workspace/cpp-mcp/pyproject.toml` — add `fastmcp~=3.1.0` to `[project].dependencies`; keep `mcp>=1.0` for now (S7 may remove it). Drop the optional `http` extra (`uvicorn`) — FastMCP bundles its own ASGI runner. (US-M8/AC-1)
- `/Users/husam/workspace/cpp-mcp/uv.lock` — regenerate via `uv lock`; commit. (US-M8/AC-2)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-10.md` — update `Status:` line to `superseded by ADR-11`. (US-M9/AC-2, EC-10)
- `/Users/husam/workspace/wiki/pages/code/cpp-mcp.md` — ADR table: add ADR-11 row (`accepted`), mark ADR-10 as `superseded by ADR-11`. (US-M9/AC-3)

### New files
- None. `v2/adr-9.md` (the logical ADR-11) already exists and carries `Status: accepted` per design §0. No new ADR file is created in this story.

### Tests
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_pyproject_pin.py` (new): parse `pyproject.toml`, assert the `fastmcp` specifier matches `~=3.1.<patch>` (regex `^~=3\.1\.\d+$`). (US-M8/AC-1)
- Manual: `uv lock --check` returns 0. (US-M8/AC-2)
- Lint: a docstring/comment scan of `~/workspace/wiki/pages/code/cpp-mcp.md` is out of scope for pytest; verified via human review at PR time.

### Exit criteria (executable)
```bash
uv lock --check
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
uv run pytest -q tests/unit/test_pyproject_pin.py
uv run pytest -q                                     # must end "327 passed, 1 skipped"
grep -q "superseded by ADR-11" /Users/husam/workspace/cpp-mcp/.claude/handoff/v1/adr-10.md
grep -q "Status: accepted" /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/adr-9.md
```

### Risks / Out of scope
- Out of scope: adding `runbook.md` upgrade-check section — deferred to S7.
- Risk: `uv sync` may pull a `fastmcp` minor that breaks something; mitigated because subsequent stories will exercise FastMCP and fail fast.

### References
- design §0 (ADR index), §5 row US-M8/US-M9; adr-1.md (file naming), adr-9.md (logical ADR-11); `[[pages/manuals/fastmcp/getting-started]]`.

---

## Story S2 — Lifespan + stdio skeleton (`build_server()` + `main()`)

Covers AC: US-M1/AC-1, US-M1/AC-2, US-M1/AC-4, US-M1/AC-5, US-M6/AC-1, US-M6/AC-2, US-M6/AC-4, US-M6/AC-5.
Driving ADRs: ADR-4 (v2) sync `mcp.run()` entrypoint, ADR-7 (v2) lifespan owns `ClangSession`.

### Files to change
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/app.py` — replace contents with `build_server()` returning `FastMCP("cpp-mcp", lifespan=app_lifespan, mask_error_details=True)` plus `main() -> int` per design §3. Keep file path so `python -m cpp_mcp` and the `cpp-mcp` console-script resolve. Configure `logging.basicConfig(stream=sys.stderr, ...)` first thing in `main()`. (US-M1/AC-1, US-M1/AC-5)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/__main__.py` — point to new `main()` (likely already does; verify import path).
- `/Users/husam/workspace/cpp-mcp/pyproject.toml` — update `[project.scripts] cpp-mcp` to `cpp_mcp.server.app:main` (currently `cpp_mcp.server.stdio_transport:main`). (US-M1/AC-1, C-10)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/stdio_transport.py` — DELETE. (design §2)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/clang_session.py` — add `async def aclose(self) -> None` that calls `self.executor.shutdown(wait=True)` then `self._cache.clear()`. (US-M6/AC-2, EC-4)

### New files
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/deps.py` — `AppLifespanContext` TypedDict, plus stubbed `get_session()`, `get_allowed_roots()`, `get_default_flags()`, `get_ast_max_nodes()`, `get_ast_max_bytes()` resolvers that read `get_context().lifespan_context`. Tools start consuming these in S3. (ADR-3, ADR-7)

### Tests
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_lifespan.py` (new):
  - `test_lifespan_constructs_session_and_yields_context` — enters `app_lifespan` manually, asserts `AppLifespanContext` shape. (US-M6/AC-1)
  - `test_lifespan_aclose_called_on_teardown` — exit lifespan, assert `ClangSession.aclose` was awaited and executor is shut down. (US-M6/AC-2, EC-4)
  - `test_lifespan_raises_config_error_when_allowed_roots_unset` — monkeypatch env, expect `ConfigError`. (US-M6/AC-5, EC-11)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_main_entrypoint.py` (new):
  - `test_main_exits_1_on_config_error_with_no_traceback` — invoke `main()` in subprocess with `CPP_MCP_ALLOWED_ROOTS` unset; assert rc=1, stderr non-empty, stderr does not contain `Traceback`, stdout empty. (US-M1/AC-5, SC_USM1_5b)
  - `test_main_exits_0_on_stdin_eof` — subprocess closes stdin immediately; assert rc=0. (US-M1/AC-5, SC_USM1_5a)
- All existing 327 tests continue to pass (C-7).

### Exit criteria (executable)
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
test ! -e /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/stdio_transport.py
uv run pytest -q tests/unit/test_lifespan.py tests/unit/test_main_entrypoint.py
uv run pytest -q                                     # 327 passed, 1 skipped (or higher)
uv pip install -e . && cpp-mcp --help >/dev/null 2>&1 || true   # smoke: console-script resolves
```

### Risks / Out of scope
- Out of scope: tool functions are not yet wired (`tools/*.py` still `async def` with v1 handlers). FastMCP will register zero tools at end of S2. **S2 deliberately leaves `tools/list` empty**; SC_USM1_2 / SC_USM1_3 / SC_C1_TOOLS_LIST cannot pass yet — they pass after S3.
- Risk: `mcp.run()` blocking behavior in tests — tests for `main()` must use `subprocess.Popen` with a short stdin EOF, not invoke `main()` in-process.

### References
- design §3 (build_server skeleton), §4.4 (lifespan invocation count), §4.6 (stdout discipline); adr-4.md, adr-7.md; scenarios SC_USM1_1, SC_USM1_4, SC_USM1_5a/b, SC_USM6_*.

---

## Story S3 — Convert 7 tool handlers to `@mcp.tool` + sync + executor

Covers AC: US-M3/AC-1, US-M3/AC-2, US-M3/AC-3, US-M3/AC-4, US-M3/AC-5, US-M7/AC-1, US-M7/AC-2, US-M7/AC-4.
Driving ADRs: ADR-3 (v2, `Depends`), ADR-7 (v2, sync + executor).

### Files to change
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/definition.py`
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/references.py`
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/type_info.py`
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/ast.py`
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/header_info.py`
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/preprocessor_state.py`
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/export_graphdb.py`

For each: (a) convert `async def` → `def`; (b) add `@mcp.tool(name="<existing-name>", description="<existing-description-from-_TOOL_SPECS>")` as the outermost decorator; (c) inject deps via `Depends(get_session)`, `Depends(get_allowed_roots)`, `Depends(get_default_flags)` (and the two ast-specific resolvers for `ast.py`); (d) replace direct libclang calls with `session.executor.submit(_do_<work>, ...).result()` so the single-worker invariant holds; (e) `Annotated[type, "description"]` on every user-facing argument (the v1 description text from `server/schemas.py` is the authoritative source). (US-M3/AC-2..4, US-M7/AC-1..2, EC-6)

- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/app.py` — remove `_TOOL_SPECS` and `_HANDLERS` if any remnants remain from S2. Add tool-module imports inside `build_server()` so decorator side-effects fire. (US-M3/AC-1)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/_registry.py` (NEW, optional) — exposes the FastMCP singleton so tool modules can `from cpp_mcp.server._registry import mcp`. Alternative per design §3: have `build_server()` import the tool modules after assigning to a module-level `mcp`. Either pattern is acceptable; pick one and apply uniformly.

### Tests
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_tool_registration.py` (new):
  - `test_seven_tools_registered_with_v1_names` — build server, assert `set(mcp.get_tools()) == {7 names}`. (US-M3/AC-1, US-M3/AC-2, SC_USM3_1, SC_USM3_2)
  - `test_dependency_params_excluded_from_input_schema` — for each tool, assert no schema property named `session`, `allowed_roots`, `default_flags`, `ast_max_nodes`, `ast_max_bytes`. (US-M3/AC-4, EC-6, SC_USM3_4)
  - `test_tool_descriptions_non_empty_match_v1` — load v1 description map (extracted into `tests/fixtures/expected_tool_descriptions.py`), assert each registered tool's description string equals the v1 string. (US-M3/AC-3, SC_USM3_3)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_executor_dispatch.py` (new):
  - `test_each_tool_calls_executor_submit` — monkeypatch `ClangSession.executor.submit` to a spy; invoke each tool; assert spy called exactly once per call. (US-M7/AC-1, US-M7/AC-2, SC_USM7_2)
- Existing 327 pytest cases must continue to pass; their handler invocation paths now go through FastMCP but assertions on response shape are unchanged (C-3, C-7).

### Exit criteria (executable)
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
# Static check: no async def in tools/
! grep -rn "^async def " /Users/husam/workspace/cpp-mcp/src/cpp_mcp/tools/
# Static check: no _TOOL_SPECS / _HANDLERS remnants
! grep -rn "_TOOL_SPECS\|_HANDLERS" /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/
uv run pytest -q tests/unit/test_tool_registration.py tests/unit/test_executor_dispatch.py
uv run pytest -q                                     # baseline maintained
```

### Risks / Out of scope
- Out of scope: error envelope wiring (S4) and schema parity test (S5).
- Risk: `Depends` import path — design §3 shows `from fastmcp.dependencies import Depends`; verify against installed FastMCP 3.1.x via `python -c "from fastmcp.dependencies import Depends"`. If the path differs (e.g., `fastmcp.server.dependencies`), update uniformly. The developer MUST `uv run python -c "import fastmcp; from fastmcp import Depends"` (try a few paths) before bulk-editing 7 files.
- Risk: the 327 baseline test suite may invoke handler functions directly with positional args — `Depends` defaults will still resolve to the lifespan context only inside a request. If existing tests bypass the lifespan, they will break; mitigation: in `conftest.py`, provide a `pytest` fixture that enters `app_lifespan` once per session and patches `get_context()` to return a stub. Add this fixture in S3.

### References
- design §3 (tool example), §4.3 (concurrency); adr-3.md, adr-7.md; scenarios SC_USM3_*, SC_USM7_1/2/4.

---

## Story S4 — Error envelope wiring (`wrap_tool` outermost-function decorator)

Covers AC: US-M5/AC-1, US-M5/AC-2, US-M5/AC-3, US-M5/AC-4, US-M5/AC-5.
Driving ADR: ADR-2 (v2) return-dict + `wrap_tool`.

### Files to change
- All 7 tool files (same set as S3) — apply `@wrap_tool(name="<tool>")` between `@mcp.tool(...)` and the `def`. Per design §3 footnote: `@mcp.tool` is outermost (registration only); `@wrap_tool` is the outermost *function* decorator (closest to `def`) so FastMCP serializes the envelope dict, not a raw exception. (US-M5/AC-1, SC_USM5_1)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/app.py` — verify `FastMCP(..., mask_error_details=True)` is present (set in S2). (US-M5/AC-4, SC_USM5_4)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/error_envelope.py` — no change expected; if `wrap_tool` was previously async-aware only, add a sync branch. (US-M5/AC-1)

### New files
- None.

### Tests
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_envelope_decorator_order.py` (new):
  - For each of the 7 tool callables imported from `cpp_mcp.tools.*`, walk `__wrapped__` chain and assert `wrap_tool` appears in the closure between the function body and FastMCP's registration shim. (US-M5/AC-1, SC_USM5_1)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_envelope_codes.py` (new or extend existing):
  - Parametrize over the 8 codes (`FILE_NOT_FOUND`, `INVALID_POSITION`, `INVALID_RANGE`, `INVALID_ARGUMENT`, `PATH_VIOLATION`, `DB_UNREACHABLE`, `PARSE_ERROR`, `INTERNAL_ERROR`); for each, drive a tool call that produces that code and assert `set(response.keys()) == {"code","message","tool","request_id"}` plus `code == <expected>`. (US-M5/AC-2, SC_USM5_2)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_envelope_mask_error_details.py` (new):
  - Register a temp tool that raises bare `RuntimeError`; assert client response has no `Traceback` substring and `code` is `INTERNAL_ERROR` or an opaque FastMCP-masked error. (US-M5/AC-4, EC-3, SC_USM5_6)
- Existing path-violation tests (e.g., `test_path_guard.py`) must continue to pass (SC_C6_PATH_GUARD, SC_USM5_3).

### Exit criteria (executable)
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
# Every tool function carries both decorators
python -c "
from cpp_mcp.tools import get_definition, get_references, get_type_info, get_ast, get_header_info, get_preprocessor_state, export_to_graphdb
TOOL_FNS = [
    (get_definition, 'get_definition'),
    (get_references, 'get_references'),
    (get_type_info, 'get_type_info'),
    (get_ast, 'cpp_get_ast'),
    (get_header_info, 'cpp_get_header_info'),
    (get_preprocessor_state, 'cpp_get_preprocessor_state'),
    (export_to_graphdb, 'cpp_export_to_graphdb'),
]
for mod, fn_name in TOOL_FNS:
    fn = getattr(mod, fn_name)
    assert hasattr(fn, '__wrapped__'), f'{mod.__name__}.{fn_name}: not wrapped'
print('OK')
"
uv run pytest -q tests/unit/test_envelope_decorator_order.py tests/unit/test_envelope_codes.py tests/unit/test_envelope_mask_error_details.py
uv run pytest -q                                     # baseline maintained
```

### Risks / Out of scope
- Out of scope: HTTP transport envelope round-trip — covered in S6.
- Risk: FastMCP may unwrap `dict` returns and apply its own structured-content shaping. If `mask_error_details=True` interferes with the envelope on the success path, narrow the mask to error paths only by raising a sentinel exception inside `wrap_tool` and letting FastMCP serialize it — but the ADR-2 default is return-dict, and the design says this is sufficient. Run `SC_USM5_5` shape assertions early.

### References
- design §4.2 (error envelope), §3 (decorator stack order note); adr-2.md; scenarios SC_USM5_1..6.

---

## Story S5 — Schema parity test + remove `server/schemas.py`

Covers AC: US-M4/AC-1, US-M4/AC-2, US-M4/AC-3, US-M4/AC-4.
Driving ADR: ADR-6 (v2) move schemas to `tests/fixtures/expected_schemas/`.

### Files to change
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/schemas.py` — DELETE after moving content. (US-M4/AC-1, SC_USM4_1)
- Any `src/` import of `server.schemas` — replace with FastMCP-derived access (likely none after S3, but grep to verify).

### New files
- `/Users/husam/workspace/cpp-mcp/tests/fixtures/expected_schemas/__init__.py` — `EXPECTED: dict[str, dict[str, Any]]` holding the 7 v1 schema dicts verbatim (copied from `server/schemas.py`). (ADR-6, US-M4/AC-1)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_schema_parity.py` — implements the parity test per design §4.1:
  - Build `mcp = build_server()` (no transport).
  - For each of 7 tools, fetch generated schema via FastMCP public API (`mcp.get_tools()[name].input_schema` or equivalent — developer to confirm against installed FastMCP 3.1.x).
  - Apply `_normalize(schema)` helper: inline `$ref`/`$defs`, collapse `["string","null"]` ↔ `Optional`, drop `title`, normalize `description` to `(present, non-empty)` boolean.
  - Assert: equal `required` sets, equal property-name sets, equal property `type` keys, equal enum values, equal defaults, `additionalProperties is False`, every argument has non-empty description.
  - Includes negative tests `test_parity_fails_on_rename` and `test_parity_fails_on_empty_description` per SC_USM4_3/4 (use pytest's `monkeypatch` of the EXPECTED dict, or a separate `tests/unit/test_schema_parity_meta.py` to avoid polluting the canonical test).
  - (US-M4/AC-2..4, SC_USM4_2/3/4/5/6, EC-7, EC-8, EC-14, C-2)

### Tests
- See `tests/unit/test_schema_parity.py` and `tests/unit/test_schema_parity_meta.py` above.

### Exit criteria (executable)
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
test ! -e /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/schemas.py
test -e /Users/husam/workspace/cpp-mcp/tests/fixtures/expected_schemas/__init__.py
uv run pytest -q tests/unit/test_schema_parity.py tests/unit/test_schema_parity_meta.py
uv run pytest -q                                     # baseline maintained
```

### Risks / Out of scope
- Out of scope: changing tool argument semantics — parity is the strict gate.
- Risk: FastMCP defaults `additionalProperties: true` per design §4.1. Developer chooses between (1) Pydantic `BaseModel` wrapper with `extra="forbid"` and (2) post-hoc override. Option (1) is preferred for mypy-strict cleanliness. If neither path works on installed FastMCP 3.1.x, this surfaces a `BUILD_FAIL`/`TEST_FAIL` early — escalate to senior-developer before forcing.
- Risk: the public API to read input schemas may be `mcp.get_tools()`, `mcp._tool_manager`, or `mcp.list_tools()`; the developer must verify against the installed version, not the design example.

### References
- design §4.1 (schema parity), §2 (file moves); adr-6.md; scenarios SC_USM4_*.

---

## Story S6 — HTTP transport + `/health` custom route

Covers AC: US-M2/AC-1, US-M2/AC-2, US-M2/AC-3, US-M2/AC-4, US-M2/AC-5.
Driving ADR: ADR-5 (v2) path `/mcp` + `GET /health`.

### Files to change
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/app.py` — extend `main()` HTTP branch: when `cfg.transport == "http"`, call `mcp.run(transport="http", host=cfg.http_bind, port=cfg.http_port, path="/mcp")`. Register `@mcp.custom_route("/health", methods=["GET"])` returning `PlainTextResponse("OK")`. Call `_warn_if_non_loopback(cfg.http_bind)` before `mcp.run()`. (US-M2/AC-1, US-M2/AC-3, US-M2/AC-4, ADR-5)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/config.py` — add (or move from v1) `_warn_if_non_loopback(bind: str) -> None` with loopback set `{"127.0.0.1", "::1", "localhost"}`. Anything else (including `0.0.0.0` and `::`) emits one WARNING log line on stderr. (US-M2/AC-3, EC-2, design §4.5)
- `/Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/http_transport.py` — DELETE. (design §2)

### Tests
- `/Users/husam/workspace/cpp-mcp/tests/bdd/features/http_transport.feature` (new) — implements scenarios SC_USM2_1..5 and SC_USM2_3b. Step files under `tests/bdd/steps/test_http_transport_steps.py` spawn a subprocess on a free port, do `requests`-based `POST /mcp` and `GET /health`, and compare outputs to stdio. (US-M2/AC-1..4)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_warn_non_loopback.py` (new):
  - Parametrize `(bind, warns)` over `("127.0.0.1", False)`, `("::1", False)`, `("localhost", False)`, `("0.0.0.0", True)`, `("::", True)`, `("192.168.1.10", True)`; assert WARNING log emitted iff expected. (US-M2/AC-3, EC-2)
- `/Users/husam/workspace/cpp-mcp/tests/bdd/steps/test_concurrent_ast_steps.py` (new) — implements SC_USM7_3: 3 concurrent HTTP `cpp_get_ast` calls on a fixture, assert all succeed, `parse_count == 1`, no `clang.cindex` exception. (US-M7/AC-3, C-8)

### Exit criteria (executable)
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
test ! -e /Users/husam/workspace/cpp-mcp/src/cpp_mcp/server/http_transport.py
uv run pytest -q tests/unit/test_warn_non_loopback.py
uv run pytest -q tests/bdd/features/http_transport.feature
uv run pytest -q tests/bdd/steps/test_concurrent_ast_steps.py
uv run pytest -q                                     # full suite; baseline now 327 + new tests, all passing
```

### Risks / Out of scope
- Out of scope: HTTP authentication (US-M2/AC-5 explicitly defers; v3 work).
- Risk: FastMCP 3.x may bind to a default path other than `/mcp`. Design §4.5 mandates explicit `path="/mcp"`. The BDD scenario should `POST` to `http://127.0.0.1:<port>/mcp` and not rely on FastMCP defaults.
- Risk: BDD subprocess port management — use `tests/bdd/conftest.py` to allocate a free port and pass via env; tear the process down with SIGTERM and verify `aclose()` runs.

### References
- design §3 (HTTP branch), §4.5 (non-loopback warning); adr-5.md, adr-7.md; scenarios SC_USM2_*, SC_USM7_3, EC-2.

---

## Story S7 — Cleanup, documentation, wiki ingestion

Covers AC: US-M1/AC-2 final confirmation, US-M8/AC-3 runbook entry, US-M9/AC-3 wiki update (if not done in S1), plus C-10 final smoke.
Driving ADRs: ADR-8 (v2) observability deferred (documented), ADR-9 (v2) wiki lineage.

### Files to change
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/runbook.md` — author. Sections: (1) start stdio, (2) start HTTP, (3) env vars and defaults, (4) FastMCP upgrade-check procedure (`~=3.1.0` pin rationale; how to evaluate a new minor; how to revert via `uv.lock`), (5) install footprint audit (`uv tree` snapshot). (US-M8/AC-3, R-1, R-8)
- `/Users/husam/workspace/wiki/pages/code/cpp-mcp.md` — update env-var table only if changed (it should not be), update ADR table to reflect ADR-11 supersession if not already done in S1, update transport section to describe FastMCP. (US-M9/AC-3)
- `/Users/husam/workspace/cpp-mcp/README.md` — short paragraph noting FastMCP as the transport layer; link to runbook.

### New files
- None in `src/`. Documentation only.

### Tests
- `/Users/husam/workspace/cpp-mcp/tests/bdd/features/entrypoint.feature` (new) — SC_C10_ENTRY: `uv pip install -e .` then run `cpp-mcp` with `CPP_MCP_ALLOWED_ROOTS` set, send a single `initialize` over stdio, assert one JSON-RPC frame returned and no stderr noise before it. (US-M1/AC-1, C-10, SC_USM1_1, SC_C10_ENTRY)
- `/Users/husam/workspace/cpp-mcp/tests/unit/test_runbook_present.py` (new): assert `runbook.md` exists and contains the strings `fastmcp` and `~=3.1.0`. (US-M8/AC-3)

### Exit criteria (executable)
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/
test -f /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/runbook.md
grep -q "~=3.1.0" /Users/husam/workspace/cpp-mcp/.claude/handoff/v2/runbook.md
uv run pytest -q tests/unit/test_runbook_present.py tests/bdd/features/entrypoint.feature
uv run pytest -q                                     # full suite green
uv run python -m build                               # sdist + wheel produced without error
```

### Risks / Out of scope
- Out of scope: middleware/observability — ADR-8 defers explicitly. Do not add `LoggingMiddleware`/`TimingMiddleware` here.
- Risk: wiki write is in `~/workspace/wiki/`; the developer should use the `llm-wiki` workflow rather than direct edits, and follow the wiki-first rule.

### References
- design §6 (R-1, R-8), §7 (out-of-scope); adr-8.md, adr-9.md; scenarios SC_USM1_1, SC_C10_ENTRY, SC_USM8_3.

---

## Cross-cutting risks

| ID  | Risk                                                              | Mitigation owner | Mitigation step                                       |
|-----|-------------------------------------------------------------------|------------------|-------------------------------------------------------|
| R-1 | FastMCP minor-version breakage                                    | S1, S7           | `~=3.1.0` pin + runbook upgrade check                 |
| R-2 | Schema drift                                                      | S5               | `test_schema_parity.py` with normalization; CI gate   |
| R-3 | Concurrent libclang access                                        | S3, S6           | Single-worker executor + SC_USM7_3 regression         |
| R-4 | Error envelope vs `ToolError` mismatch                            | S4               | Return-dict + `mask_error_details=True`               |
| R-5 | Sync vs async handler regression                                  | S3               | Uniform sync `def`; executor dispatch test            |
| R-6 | Console-script regression                                         | S2, S7           | `[project.scripts]` updated; SC_C10_ENTRY             |
| R-7 | Empty schema descriptions                                         | S5               | Parity test fails on empty descriptions               |
| R-8 | Install footprint bloat                                           | S7               | `uv tree` audit documented in runbook                 |

## Out of scope (whole-plan)

- FastMCP middleware (`LoggingMiddleware`, `TimingMiddleware`) — ADR-8 defers to v3.
- HTTP authentication — US-M2/AC-5 + v1 ADR-10 carry-over.
- Renaming tools, adding tool arguments, altering path-guard semantics (C-1, C-2, C-6).
- Removing the `mcp` package from `pyproject.toml` — S1 keeps it; future cleanup story can evaluate after the migration stabilizes.

## References

- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/CHARTER.md` (invariants I1..I4, paths, failure taxonomy)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/requirements.md` (AC IDs)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/scenarios.md` (SC tags)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/design.md` (component map, traceability §5)
- `/Users/husam/workspace/cpp-mcp/.claude/handoff/v2/adr-1.md` .. `adr-9.md`
- `[[pages/manuals/fastmcp/servers]]`, `[[pages/manuals/fastmcp/getting-started]]`, `[[pages/manuals/fastmcp/cli]]`
- `[[pages/code/cpp-mcp]]`
- Cognee dataset: `agent-memory` (tags: `task:fastmcp-migration`, `role:senior-developer`)
