# ADR-1: ADR-11 lives at v2/adr-9.md; v1/adr-10.md status line is updated in place

Status: accepted
Context:
  - OQ-1: Where does ADR-11 (FastMCP supersession of ADR-10) live — `v1/adr-11.md` continuing the historical series, or under `v2/` per CHARTER blackboard paths?
  - CHARTER (v2/CHARTER.md) blackboard names ADRs as `v2/adr-<n>.md`.
  - US-M9/AC-1 textually requires a file named `adr-11.md` with `Status: accepted` and header `Supersedes: ADR-10`.
  - US-M9/AC-2 requires the v1 ADR-10 `Status:` line to be updated to `superseded by ADR-11`, which is a cross-handoff write.

Decision:
  - Storage path: this run's supersession ADR is `v2/adr-9.md` (per CHARTER numbering inside this handoff). The file's first-line header carries the logical identifier `ADR-11` so the project-wide ADR series continues unambiguously (`ADR-1..10` from v1 + `ADR-11` = supersession).
  - The v1 file `~/workspace/cpp-mcp/.claude/handoff/v1/adr-10.md` MUST be updated in place to change its `Status:` line to `superseded by ADR-11`. This single-line edit is authorised under this ADR's acceptance: the architect role-boundary forbids modifying production code / k8s manifests / CI, not v1 ADR markdown lineage.
  - The wiki page `[[pages/code/cpp-mcp]]` ADR table MUST be updated by the doc-writer stage to reflect ADR-11 accepted + ADR-10 superseded.

Alternatives considered:
  - `v1/adr-11.md` (continue historical series in v1 directory): rejected — CHARTER invariant binds ADR storage to the active handoff dir; mixing v1 and v2 ADR storage breaks the blackboard path contract.
  - `v2/adr-1.md` reset numbering, drop the `ADR-11` logical name: rejected — US-M9/AC-1 names `adr-11.md` literally and the wiki ADR table indexes by logical number; resetting would orphan ADR-10's `superseded by` pointer.
  - Defer the v1 status-line edit to docs-changes stage: rejected — US-M9/AC-2 is a hard AC; deferring leaves the lineage incoherent at developer dispatch.

Consequences:
  - Positive: blackboard contract honoured (storage in v2/), historical series preserved (logical ADR-11), supersession discoverable from both v1 and v2 directions.
  - Negative: dual identity (file `adr-9.md` carries header `ADR-11`) requires a one-line explanation in design.md §ADR-index.
  - Follow-up: doc-writer updates `[[pages/code/cpp-mcp]]` ADR table.

References:
  - CHARTER.md (blackboard paths)
  - v1/adr-10.md
  - requirements.md US-M9
  - `[[pages/code/cpp-mcp]]`
