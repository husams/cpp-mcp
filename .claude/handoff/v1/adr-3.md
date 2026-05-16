# ADR-3: Allowed roots — list, configured via environment variable
Status: accepted
Context:
  - OQ-14: should the server enforce a single allowed root or a list?
  - ASM-1 in scenarios.md provisionally assumed single root.
  - Realistic agent workloads span multiple repos under `~/workspace/`; forcing a single root means a separate server process per repo.
  - US-12/AC-5 mandates that allowed root is required at startup; unset = startup error.

Decision:
  - Configuration variable: `CPP_MCP_ALLOWED_ROOTS` (note: plural).
  - Value: **colon-separated list of absolute paths** (POSIX `PATH`-style). On Windows, semicolon — but v1 targets POSIX only.
  - Empty / unset → server exits with non-zero code at startup and prints `CONFIG_ERROR: CPP_MCP_ALLOWED_ROOTS is required` to stderr.
  - Each entry must be an existing directory and absolute; any non-absolute or non-existent entry → startup error listing offending entry.
  - At validation time (path_guard), a file is allowed iff its resolved realpath is `commonpath` equal to at least one allowed root.

Alternatives considered:
  - Single root only: rejected — forces N-process deployments for multi-repo agents.
  - Config file (TOML/JSON): rejected — adds parsing surface and a file-watch decision for v1; env var is sufficient.
  - Per-call allowed-root parameter: rejected — defeats the security property (caller-controlled = no protection).

Consequences:
  - Positive: one server handles multi-repo workflows; trivially testable.
  - Negative: operator must remember plural variable name; we document this prominently in runbook.
  - Follow-up: if config grows past 3 vars, migrate to a config file in a later ADR.

References:
  - requirements.md US-12/AC-5, OQ-14
  - scenarios.md ASM-1 (now superseded)
  - design.md §6
