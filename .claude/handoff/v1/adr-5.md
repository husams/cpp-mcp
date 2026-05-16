# ADR-5: AST response size cap — dual node + byte limit with truncation flag
Status: accepted
Context:
  - OQ-4: `cpp_get_ast` can produce thousands of nodes for a moderate file; serialized as JSON it can overflow agent context windows.
  - Agents typically operate with 100K–1M token contexts; an unbounded AST will be either truncated by the transport layer (silently) or destroy the agent's remaining context.
  - US-4/AC-3 already defines a `truncated: true` flag at the per-node level for `depth` truncation, but we additionally need a global size budget.

Decision:
  - Two configurable hard caps applied during AST walk:
    - `CPP_MCP_AST_MAX_NODES` default **5000** nodes (counted in DFS order before serialization).
    - `CPP_MCP_AST_MAX_BYTES` default **1 MiB** (`1048576`) on serialized JSON length.
  - The walker tracks a running node count. Hitting either cap stops further traversal and the response top-level includes:
    ```
    "truncated": true,
    "truncation_reason": "max_nodes" | "max_bytes",
    "nodes_emitted": <int>,
    "nodes_omitted_estimate": <int|null>   // null if we can't estimate cheaply
    ```
  - Per-node `truncated: true` (US-4/AC-3 depth truncation) is preserved and orthogonal — a node can have `truncated:true` because its subtree exceeded `depth`, OR the whole response can be truncated because the global cap fired. Both signals can co-exist.
  - For `format="graph"`, the cap applies to total node count; partial edge sets are emitted only for nodes that made it in (no dangling edge references).

Alternatives considered:
  - Token-based cap: rejected — server doesn't know agent's tokenizer; bytes is universal and a good proxy.
  - Single cap (nodes only): rejected — pathological nodes (giant string literal `spelling`) blow byte budget at low node count.
  - Streaming response: rejected for v1 — MCP SDK and JSON-RPC don't have first-class streaming in the Python SDK yet.
  - Silent truncation: rejected — violates US-2/AC-7 spirit ("no silent data loss") and US-13 envelope discipline.

Consequences:
  - Positive: agent can detect truncation and re-call with smaller `depth` or narrower `start_line/end_line`.
  - Negative: defaults may need tuning; surfaced in config (operator can change without code edit).
  - Follow-up: collect telemetry on how often truncation fires; tune defaults in a follow-up ADR.

References:
  - requirements.md US-4/AC-3, US-4/AC-7, OQ-4
  - design.md §2 (ast_walker), §6 (config)
