# ADR-1: Tool surface and per-tool scope decisions
Status: accepted
Context:
  - Dispatch brief mentions 9 tools; requirements-raw.md lists 7 (OQ-1).
  - Several tool-scope questions are open: reference search scope (OQ-3), graph edge types (OQ-5), orphaned include definition (OQ-6), preprocessor transitive macros (OQ-7), graphdb recursive directory walk (OQ-10).
  - Senior-developer needs an unambiguous tool surface before implementation.

Decision:
  - v1 exposes **exactly 7 tools**: cpp_get_definition, cpp_get_references, cpp_get_type_info, cpp_get_ast, cpp_get_header_info, cpp_get_preprocessor_state, cpp_export_to_graphdb. The dispatch brief's "9" is treated as a typo; no additional tools are added.
  - OQ-3: `cpp_get_references` searches **only the current translation unit**. Cross-TU reference search is out of scope for v1 (would require parsing every entry in compile_commands.json — multi-second latency per call, breaks the cache model).
  - OQ-5: graph `edge_type` is a **fixed enum**: `CHILD`, `TYPE_REF`, `CALL`. Future edge types added by ADR superseding this one.
  - OQ-6: orphaned include = "header included by `file_path` but no symbol exported by that header is referenced inside `file_path`'s TU". TU-scope only.
  - OQ-7: `cpp_get_preprocessor_state` returns macros from `file_path` AND transitively from included headers; each macro's `defined_at.file` distinguishes origin. `-D` flags have `defined_at: null` (US-6/AC-2).
  - OQ-10: `recursive=false` by default; `recursive=true` supported in v1 for `cpp_export_to_graphdb` only. Other tools take a single file.

Alternatives considered:
  - Expand to 9 tools by adding cpp_get_call_graph + cpp_get_inheritance: rejected — not in requirements-raw.md, would slip schedule.
  - Cross-TU references via compilation_db enumeration: rejected — O(N) parse cost per call breaks the latency contract implied by the TU cache.
  - Open-ended `edge_type` strings: rejected — agents need to enumerate known cases; an enum is the contract.

Consequences:
  - Positive: tight, testable surface; one BDD scenario file per tool.
  - Negative: cross-file impact analysis requires multiple calls or graphdb export; documented as limitation.
  - Follow-up: track agent-side complaints about TU-only references; revisit in v2.

References:
  - requirements.md US-1..US-7, OQ-1, OQ-3, OQ-5, OQ-6, OQ-7, OQ-10
  - design.md §7
