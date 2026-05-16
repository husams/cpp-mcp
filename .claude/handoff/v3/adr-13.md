# ADR-13: `DEPENDENCY_MISSING` error code (amends ADR-2 / ADR-8)
Status: accepted
Date: 2026-05-16
Run: graphdb-multi-v3

## Context

When the `neo4j` Python driver is not installed and an operator calls
`cpp_export_to_graphdb` with a `bolt://` URI, the current code path returns
an envelope with `code = "DB_UNREACHABLE"` and a message about Bolt
connectivity. The root cause is at `src/cpp_mcp/graphdb/neo4j_driver.py:51-54`:
`ImportError` is mapped to `DBUnreachableError`. This misclassification was
observed on 2026-05-16 during a fmt-test run and is the trigger for US-G1.

`DB_UNREACHABLE` semantically means "the daemon is reachable in principle but
this client cannot talk to it right now" (network, auth, daemon-down). A
missing Python package is a **setup error** — the user must install
something, not check connectivity. Calling these the same forces the
operator to read the message text to distinguish the cases, which contradicts
the fixed-shape envelope contract (ADR-8).

Adding a second backend (IndraDB) makes this worse: a future user with
`indradb://` URI and no `indradb` package would see `DB_UNREACHABLE` and
spend time debugging the daemon.

## Decision

Add a new error code `DEPENDENCY_MISSING` to the closed enum and a matching
exception class:

```python
# core/error_envelope.py
class ErrorCode(StrEnum):
    ...
    DB_UNREACHABLE      = "DB_UNREACHABLE"
    DEPENDENCY_MISSING  = "DEPENDENCY_MISSING"      # NEW
    ...

class DependencyMissingError(Exception):
    """Raised when an optional Python package required for a backend is
    not importable. Message MUST include the install command."""
```

Wire it in `_EXC_TO_CODE` **before** `DBUnreachableError`:

```python
_EXC_TO_CODE = [
    ...,
    (DependencyMissingError, ErrorCode.DEPENDENCY_MISSING),  # NEW — before DBUnreachable
    (DBUnreachableError,     ErrorCode.DB_UNREACHABLE),
    ...,
]
```

Both `Neo4jDriver.connect` and `IndraDBDriver.connect` raise
`DependencyMissingError` (not `DBUnreachableError`) on `ImportError`. Message
shape:

```
'<pkg> Python driver is not installed. '
'Install with: pip install "cpp-mcp[graphdb-<backend>]"'
```

The envelope wire shape is unchanged: `{code, message, tool, request_id}`
(constraint C-G3). The new code is **additive** to the existing 8 codes —
clients that switch on `code` keep working; clients can add a new case for
the precise install instruction.

The error fires **inside** `connect()`, before any socket is opened —
satisfies C-G6 and the scenario "DEPENDENCY_MISSING fires before any database
I/O attempt".

OQ resolution recorded:
- **OQ-G4**: `DependencyMissingError` is classified as a **setup error**
  (actionable install hint). If/when we add metrics labels, the tag is
  `errors{class="setup"}`, distinct from `errors{class="runtime"}` for
  `DB_UNREACHABLE`. This is forward-guidance; v3 ships no metrics changes.

## Alternatives considered

1. **Keep `DB_UNREACHABLE` and improve the message** — rejected. The fixed
   envelope shape (ADR-8) explicitly forbids relying on message text for
   classification. Operators reading dashboards / alerting on `code` would
   continue to see false positives for "DB down".

2. **Reuse `INVALID_ARGUMENT`** — rejected. The user's argument is valid
   (`bolt://` is a known scheme). The fault is on the server side (package
   not installed). Mislabeling deflects investigation to the client.

3. **New error code `MISSING_EXTRA` instead of `DEPENDENCY_MISSING`** —
   considered. `DEPENDENCY_MISSING` chosen because "dependency" is the
   Python-ecosystem term users will recognise; "extra" is a packaging
   detail. Either name is fine; we lock in `DEPENDENCY_MISSING`.

## Consequences

Positive:
- Operators can distinguish "install something" from "fix the network" at a
  glance via `code`.
- The misclassification observed 2026-05-16 is closed (US-G1/AC-3).
- Ordering of `_EXC_TO_CODE` puts `DependencyMissingError` above
  `DBUnreachableError`, so even if a future refactor accidentally makes one
  inherit from the other, classification stays stable.

Negative / follow-ups:
- The closed `ErrorCode` enum grows from 8 → 9 values. Any downstream
  exhaustive `match` on `ErrorCode` must add a case. The codebase's own
  `tests/unit/test_envelope_codes.py` and runbook error-code table must be
  updated. (`US-G6/AC-2` covers the runbook.)
- A future operator may legitimately ask "did the package install fail or is
  the daemon down?" — `DEPENDENCY_MISSING` answers only the former; daemon
  health-check is OQ-G5 / out of v3 scope.

## References

- ADR-2 (error envelope shape).
- ADR-8 (closed `ErrorCode` enum, sanitizer).
- `requirements.md` US-G1 (AC-1..AC-4).
- `scenarios.md` Feature "DEPENDENCY_MISSING error code".
- `src/cpp_mcp/graphdb/neo4j_driver.py:51-54` (current miswire).
- `src/cpp_mcp/core/error_envelope.py` (`_EXC_TO_CODE`).
- adr-12 (dispatch, calls into connect that raises this).
