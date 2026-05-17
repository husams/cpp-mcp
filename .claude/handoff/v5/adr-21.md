# ADR-21: Authoritative grep gate for `cpp_` residue (OQ-3)

Status: accepted
Context:
- AC-R2-4 specifies `grep -RE 'cpp_(get|export)_' src/ tests/` but lists exceptions (CHANGELOG, README) that are outside the grep's target directories — the exception list as written is vacuous.
- The repo also contains `.claude/handoff/`, `docs/`, and (out-of-tree) wiki pages where intentional `cpp_*` references must survive (historical ADR text, migration tables).
- OQ-3 asked QA to nail down the authoritative command.

Decision:
- The authoritative gate command, run from repo root, is:

  ```bash
  grep -RIE 'cpp_(get|export)_' src/ tests/
  ```

  This MUST return exit code 1 (no matches). `-I` excludes binary files; scope is exactly `src/` and `tests/`.
- The README migration table and `CHANGELOG.md` are NOT scanned by this gate (they live at repo root, outside `src/`/`tests/`). The original AC-R2-4 exception clause is therefore explanatory only and adds no `--exclude` flags.
- A secondary informational check (non-gating, for reviewer awareness):

  ```bash
  grep -RIE 'cpp_(get|export)_' --exclude-dir=.git --exclude-dir=.claude --exclude=CHANGELOG.md --exclude=README.md .
  ```

  Non-zero exit is a warning, not a blocker — `.claude/handoff/` retains historical task text and is excluded.

Decision (exception handling):
- The "shim from US-V5-R4 (if any)" clause in AC-R2-4 is **dead**: AC-R4-3 forbids aliases. No `--exclude` for shim code is needed. If a future patch (0.3.1) reintroduces aliases, this ADR must be superseded.

Alternatives considered:
- Broaden scope to repo root with explicit excludes — rejected: noisier, and `.claude/handoff/` historical content would require an ever-growing exclude list.
- Match a stricter pattern (only the 7 specific old names) — rejected: the `(get|export)_` family pattern is already tight and catches typos; widening to exact names provides no extra safety.

Consequences:
- Positive: a single deterministic command that QA can encode as the exit-criteria check in plan.md.
- Negative: a stray `cpp_*` in `docs/` would slip through this gate; mitigated by AC-R3-* doc-review acceptance criteria.
- Follow-up: senior-developer encodes this exact command as an exit-criteria gate in plan.md for US-V5-R2.

References: requirements.md OQ-3, AC-R2-4, AC-R4-3, EC-5.
