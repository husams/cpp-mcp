---
run_id: fastmcp-migration-v2
story: S7 — Cleanup, documentation, wiki ingestion (latest; see logs/ for S1-S6 history)
stage: developer
date: 2026-05-16
---

# Implementation Notes — S7

## Files changed

- `.claude/handoff/v2/runbook.md` — authored (new). Five sections: (1) stdio startup, (2) HTTP startup + non-loopback warning, (3) env-var table (10 vars), (4) FastMCP upgrade-check procedure (`~=3.1.0` pin rationale, evaluation steps, revert via `uv.lock`), (5) install-footprint audit (`uv tree` snapshot: 99 packages resolved, fastmcp 3.1.1 transitive deps listed).
- `README.md` — added FastMCP paragraph (transport layer description, link to runbook), added HTTP transport run section, updated test count from 327 to 457.
- `tests/unit/test_runbook_present.py` — new. Asserts runbook.md exists and contains `fastmcp` and `~=3.1.0`.
- `tests/bdd/features/entrypoint.feature` — new. SC_C10_ENTRY scenario.
- `tests/bdd/test_entrypoint.py` — new. Step-defs for entrypoint.feature; spawns `cpp-mcp` console script via subprocess, sends JSON-RPC initialize, asserts response frame on stdout and no error lines on stderr.
- `pyproject.toml` — added `SC_C10_ENTRY` marker registration to suppress PytestUnknownMarkWarning.
- `~/workspace/wiki/pages/code/cpp-mcp.md` — **skipped** per dispatch instruction ("the doc-writer role runs after you for the wiki page").

## Tests added/run

```
uv run pytest -q tests/unit/test_runbook_present.py   # 3 passed
uv run pytest -q tests/bdd/test_entrypoint.py         # 1 passed
uv run pytest -q                                       # 457 passed, 4 skipped
uv run --with build python -m build                    # sdist + wheel produced without error
```

## Deviations from plan

1. **Wiki edit skipped**: plan.md §S7 item 2 lists updating `~/workspace/wiki/pages/code/cpp-mcp.md`. The dispatch instruction explicitly overrides this: "the doc-writer role runs after you for the wiki page." No wiki edits were made. Tagged for doc-writer follow-up.

2. **`test_entrypoint.py` step file added**: plan.md lists only `tests/bdd/features/entrypoint.feature` (the `.feature` file), but pytest-bdd requires a paired step-defs `.py` file. `tests/bdd/test_entrypoint.py` was added. This matches the convention established across all prior BDD features (see also S6 notes re `transport_http.feature` naming deviation).

3. **Exit-criteria `pytest` invocation with `.feature` path**: plan.md line 339 runs `uv run pytest -q tests/unit/test_runbook_present.py tests/bdd/features/entrypoint.feature`. Passing a `.feature` path directly to pytest collects 0 items from it (pytest-bdd requires the `.py` step file). The exit gate is satisfied by the full `uv run pytest -q` command on line 340 which collects `test_entrypoint.py` normally.

4. **`python -m build` invoked as `uv run --with build python -m build`**: `build` is not in `[project.optional-dependencies].dev` and not in the venv. Invoked with `--with build` flag to avoid polluting the venv. Build succeeded. Tagged as follow-up: add `build` to dev extras if the exit-criteria command should work without `--with`.

5. **Test count updated to 457**: README said "327 tests pass"; plan only asks for a FastMCP paragraph + runbook link in README, but leaving "327" was a clear factual error (S6 already brought it to 453+4 new S7 tests). Updated to 457.

## Follow-ups

- `@doc-writer`: update `~/workspace/wiki/pages/code/cpp-mcp.md` — env-var table, ADR-11 supersession, transport section. See plan.md §S7 files-to-change item 2.
- `@senior-developer`: consider adding `build` to `[project.optional-dependencies].dev` so `uv run python -m build` works without `--with build`.
- `@senior-developer`: `SC_US_14_CALL_ENVELOPE` marker is not registered in `pyproject.toml` (pre-existing from S6); emits PytestUnknownMarkWarning. Recommend registering it alongside the other markers.

## References

- plan.md lines 315-383
- scenarios SC_C10_ENTRY, SC_USM1_1, SC_USM8_3
- adr-8.md (observability deferred), adr-9.md (ADR-11 FastMCP supersedes v1 ADR-10)
- design §6 (R-1, R-8), §7 (out-of-scope)
