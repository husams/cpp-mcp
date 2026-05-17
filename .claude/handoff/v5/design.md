# Design — cpp-mcp v5 pure-rename release (0.2.0 → 0.3.0)

**Status:** ready-for-senior-developer
**Date:** 2026-05-17
**run_id:** cpp-mcp-v5-rename

## Scope reminder

Pure rename. No behavior change. Single PR. Test parity gate is hard (618 pass / 6 skip unit; 18 pass integration). See requirements.md for the seven name mappings.

## Decisions resolved (ADRs)

| ADR | Decision | Open question |
|---|---|---|
| ADR-19 | Cache-key schema is the unit of "untouched"; tool-name is not a cache dimension (verified in `tu_cache.py`). | OQ-1 |
| ADR-20 | Rename `export_to_graphdb.py` → `ingest_code.py` only; other six tool files already match new wire names. Use `git mv`. | OQ-2 |
| ADR-21 | Authoritative grep gate: `grep -RIE 'cpp_(get|export)_' src/ tests/` returning exit 1. No shim exclusion (aliases forbidden). | OQ-3 |

All three ADRs are `Status: accepted`. No `ADR_UNRESOLVED`.

## Dependency order (intra-PR)

The PR must touch four story-slices in this order to keep intermediate commits buildable. The end state is a single PR; intermediate commits within the branch are optional aids for review.

```
US-V5-R1 (server registry + symbol rename + fixtures)
    └─> US-V5-R2 (test call-sites + BDD file renames)
            └─> US-V5-R3 (README + ADR-16/17/18 inline notes + wiki)
                    └─> US-V5-R4 (pyproject version bump + CHANGELOG)
```

Rationale:
- **R1 first** — the registry/symbol rename is the only change that can break the build. All later stories depend on R1 being in place to compile/import.
- **R2 second** — tests cannot pass against the renamed registry until call-sites are updated; conversely, updating call-sites before R1 would break the suite immediately.
- **R3 third** — documentation can only be finalized once the names are stable in code.
- **R4 last** — version bump and changelog are the merge marker; doing them earlier risks shipping `0.3.0` with a half-renamed surface if the PR is split.

## Files to touch (high-level inventory; senior-developer expands into plan.md)

| Story | Path family | Action |
|---|---|---|
| R1 | `src/cpp_mcp/tools/*.py` (7 files) | Update `name=` per mapping; rename one module (ADR-20). |
| R1 | `src/cpp_mcp/tools/__init__.py`, registration site | Update import path for `ingest_code`. |
| R1 | `src/cpp_mcp/core/error_envelope.py` | Update `DEPENDENCY_MISSING` wording (AC-R1-5). |
| R1 | `tests/fixtures/expected_schemas/`, `tests/fixtures/expected_tool_descriptions.py` | Regenerate fixtures. |
| R2 | `tests/**/*.py` | Replace `call_tool("cpp_…")` and `git mv` two BDD files. |
| R3 | `README.md`, ADR-16/17/18, `~/workspace/wiki/pages/code/cpp-mcp.md`, `~/workspace/wiki/pages/code/cpp-mcp-v4.md`, `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md`, `~/workspace/wiki/index.md` | Update per AC-R3-*. |
| R4 | `pyproject.toml`, `CHANGELOG.md` (create) | Version + entry. |

## Exit-criteria commands (for plan.md)

Senior-developer MUST encode these in plan.md exit-criteria:

```bash
# Lint & format
uv run ruff format --check .
uv run ruff check .

# Unit parity (hard gate per NFR)
uv run pytest -q --no-header
# Expect: 618 passed, 6 skipped

# Integration parity (hard gate)
uv run pytest -m integration -q --no-header
# Expect: 18 passed

# Grep gate (ADR-21, authoritative)
! grep -RIE 'cpp_(get|export)_' src/ tests/

# Registry shape (AC-R1-4, EC-2, EC-3)
uv run python -c "from cpp_mcp.server import mcp; names = [t.name for t in mcp._tool_manager.list_tools()]; assert len(names) == 7, names; assert not any('cpp_' in n for n in names), names; print(names)"
```

(Senior-developer: confirm the FastMCP introspection path against the v4 server; the snippet above is illustrative for the gate, not a contract.)

## Single-PR delivery constraint

All four stories land in **one PR** against `main`. Rationale (from NFR):
- A half-renamed surface is worse than either pre- or post-rename.
- The version bump (R4) is the signal to clients that names changed; shipping it without R1–R3 complete misleads consumers.
- Test-parity gate is meaningful only over the full delta.

The developer may use a feature branch with sub-commits per story for review hygiene, but the merge unit is a single PR titled e.g. `v5: tool rename (drop cpp_ prefix; export_to_graphdb → ingest_code)`.

## Risks

| Risk | Mitigation |
|---|---|
| Hidden `cpp_*` string in a fixture or docstring slips past the grep gate | ADR-21 gate scopes `src/` and `tests/`; doc review (AC-R3-*) covers the rest. Reviewer spot-checks `docs/`. |
| BDD pytest collection drops a renamed file | After `git mv`, run `uv run pytest --collect-only -q tests/bdd/` and confirm count == v4 baseline. |
| Schema fixtures drift in ways unrelated to names | Diff fixtures before commit; only tool-name fields should change. |
| External integrator on 0.2.x breaks silently | AC-R4-3 accepts this; CHANGELOG + README migration table are the only mitigation (no aliases). |

## References

- requirements.md, scenarios.md (this handoff)
- ADR-19, ADR-20, ADR-21 (this handoff)
- ADR-6 (cache key schema, prior art)
- `[[pages/planning/cpp-mcp-codexgraph-gap]]`
- `project_v4_e2e_tests_shipped.md`, `project_v4_live_verification.md` (baseline counts)
