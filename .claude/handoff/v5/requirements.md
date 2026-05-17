# v5 Requirements — Tool Rename (drop `cpp_` prefix, `export_to_graphdb` → `ingest_code`)

**Status:** ready-for-architect
**Date:** 2026-05-17
**run_id:** cpp-mcp-v5-rename
**Predecessor:** handoff/v4 (618 unit + 18 integration green; live-verified against {fmt})
**Plan reference:** `[[~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap]]`

---

## Context

The seven MCP tools currently registered are:

| Old name | New name |
|---|---|
| `cpp_get_ast` | `get_ast` |
| `cpp_get_definition` | `get_definition` |
| `cpp_get_references` | `get_references` |
| `cpp_get_type_info` | `get_type_info` |
| `cpp_get_header_info` | `get_header_info` |
| `cpp_get_preprocessor_state` | `get_preprocessor_state` |
| `cpp_export_to_graphdb` | `ingest_code` |

**Why now.** The `cpp_` prefix predates the v5 graphdb roadmap (`[[pages/planning/cpp-mcp-codexgraph-gap]]`). Once the planned query-side tools land, the surface will read more naturally without the language prefix, and `ingest_code` describes the operation (graph ingestion) rather than the backend (`export_to_graphdb`).

**Breaking change.** All wire names change. Any existing MCP client config (Claude Desktop, Cursor, automation) breaks on upgrade. Version bumps to **0.3.0** and the README ships a migration table.

---

## Story US-V5-R1 — Rename tool wire names in the server registry

As an MCP client author, I want the seven tools registered under their new short names, so that the surface reads naturally and matches the v5 roadmap.

**Acceptance criteria:**
- AC-R1-1: Each tool module in `src/cpp_mcp/tools/*.py` declares its new `name=` per the table above.
- AC-R1-2: `cpp_export_to_graphdb` is renamed to `ingest_code` (both the registered tool name and the Python function/module symbol where it would otherwise drift).
- AC-R1-3: Schema fixtures under `tests/fixtures/expected_schemas/` and `tests/fixtures/expected_tool_descriptions.py` are regenerated and reflect the new names.
- AC-R1-4: `tests/unit/test_tool_registration.py` passes with the new name set; the registry exposes exactly seven tools and no name contains the `cpp_` prefix.
- AC-R1-5: The `DEPENDENCY_MISSING` error envelope (`src/cpp_mcp/core/error_envelope.py`) and any other error wording that names a tool uses the new names.

**Priority:** P0 — gates every other rename story.

**Dependencies:** none upstream.

**Open questions:** none.

**References:** `.claude/handoff/v5/requirements-raw.md`; `[[pages/planning/cpp-mcp-codexgraph-gap]]`.

---

## Story US-V5-R2 — Update all tests to call tools by their new names

As a maintainer, I want every test to invoke tools by the new names, so the suite passes against the renamed registry without compatibility shims.

**Acceptance criteria:**
- AC-R2-1: Every `client.call_tool("cpp_...")` call in `tests/` is updated to the new name.
- AC-R2-2: BDD feature files and step modules under `tests/bdd/` are renamed where the file name encodes the tool:
  - `test_export_to_graphdb.py` → `test_ingest_code.py`
  - `test_export_to_indradb.py` → `test_ingest_code_indradb.py`
  - (other `test_get_*.py` BDD modules keep their filenames — only the tool name inside changes.)
- AC-R2-3: `uv run pytest` reports the same pass/skip counts as v4 (618 pass / 6 skip baseline; 18 pass under `-m integration`). No flake, no behavior regression.
- AC-R2-4: `grep -RE 'cpp_(get|export)_' src/ tests/` returns no hits except in the migration shim from US-V5-R4 (if any), changelog, and README's migration table.

**Priority:** P0.

**Dependencies:** US-V5-R1.

**Open questions:** none.

**References:** `.claude/handoff/v5/requirements-raw.md`; v4 baseline counts from `project_v4_e2e_tests_shipped.md`.

---

## Story US-V5-R3 — Update documentation and wiki

As a reader of the project docs, I want every reference to the old tool names updated, so I can paste the docs into a client config and have it work.

**Acceptance criteria:**
- AC-R3-1: `README.md` lists the new tool names; a "Migration from 0.2.x" section maps old → new (the table above).
- AC-R3-2: ADR-16, ADR-17, ADR-18 reference the new names where they appear in body text (historical claims about v3/v4 may retain the old names as historical artifacts — flag with an inline "(renamed to `…` in v5)" note rather than rewriting history).
- AC-R3-3: Wiki pages updated:
  - `~/workspace/wiki/pages/code/cpp-mcp.md`
  - `~/workspace/wiki/pages/code/cpp-mcp-v4.md` (add a note: tools renamed in v5)
  - `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md` (S1 / S2 proposed names align with the unprefixed scheme; reaffirm `query_graphdb` and `translate_query`, not `cpp_query_graphdb` / `cpp_translate_query`)
- AC-R3-4: `index.md` description lines for the cpp-mcp pages mention v0.3.0 with the new tool names.

**Priority:** P1 — must ship in the same release as the rename; can land in the same PR.

**Dependencies:** US-V5-R1.

**Open questions:** none.

**References:** `.claude/handoff/v5/requirements-raw.md`; `~/workspace/wiki/pages/code/cpp-mcp-v4.md`.

---

## Story US-V5-R4 — Version bump and changelog

As a user upgrading from 0.2.x, I want a clear changelog and version bump so I know to update my client config.

**Acceptance criteria:**
- AC-R4-1: `pyproject.toml` (or wherever the version lives) bumps from `0.2.0` to `0.3.0`.
- AC-R4-2: A `CHANGELOG.md` entry (create the file if missing) documents the rename with the old→new table and a one-line rationale linking to `pages/planning/cpp-mcp-codexgraph-gap.md`.
- AC-R4-3: No compatibility aliases. Clients on 0.2.x calling `cpp_get_ast` receive the standard MCP "tool not found" error. (Decision: clean break is acceptable because there are no known external integrators as of 2026-05-17. If that turns out to be wrong, add aliases in a 0.3.1 patch.)

**Priority:** P1.

**Dependencies:** US-V5-R1, US-V5-R2, US-V5-R3.

**Open questions:** none.

**References:** `.claude/handoff/v5/requirements-raw.md`; `[[pages/planning/cpp-mcp-codexgraph-gap]]`.

---

## Non-functional requirements

- **No behavior change.** This is a pure rename. Argument shapes, return shapes, error codes, cache keys, schema versions for the graph payload, and the IndraDB / Neo4j wire format are untouched.
- **Single PR.** All four stories land together — a half-renamed surface is worse than either pre- or post-rename.
- **Test parity gate (hard).** `uv run pytest` must report exactly 618 pass / 6 skip (unit) and 18 pass (integration, `-m integration`) post-rename. Any deviation is a blocker — rename or deletion of a test must be explicitly justified and approved before merge.

---

## Out of scope

- New tools (`query_graphdb`, `translate_query`) — those are S1 / S2 in `[[pages/planning/cpp-mcp-codexgraph-gap]]` and ship in their own handoff.
- Schema changes (S3 `access_kind`, S4 FIELD/GLOBAL_VARIABLE split) — separate handoffs.
- Compatibility aliases for old tool names (see AC-R4-3 for rationale).
- Behavioral changes to argument shapes, return shapes, error codes, cache semantics, or graph wire format.

---

## References

- Plan: `~/workspace/wiki/pages/planning/cpp-mcp-codexgraph-gap.md`
- Predecessor handoff: `.claude/handoff/v4/`
- Current code page: `~/workspace/wiki/pages/code/cpp-mcp-v4.md`
- Memory: `project_v4_live_verification.md`, `project_v4_e2e_tests_shipped.md`
- Raw requirements: `.claude/handoff/v5/requirements-raw.md`
