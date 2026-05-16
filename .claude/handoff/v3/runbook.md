---
run_id: graphdb-multi-v3
stage: developer
date: 2026-05-16
covers: US-G6/AC-1, US-G6/AC-2, US-G6/AC-3
supersedes: v2/runbook.md (graphdb section extended)
---

# cpp-mcp v3 Operations Runbook — Pluggable GraphDB Backends

This runbook extends the v2 runbook (`.claude/handoff/v2/runbook.md`) with
v3-specific content: URI scheme dispatch, backend install commands, daemon
bring-up, the new `DEPENDENCY_MISSING` error code, and license posture.

For FastMCP startup, transport config, upgrade-check procedure, and general
troubleshooting see the v2 runbook.

---

## 1. Graph database URI scheme → driver mapping

`cpp_export_to_graphdb` selects a backend driver by inspecting the scheme
component of the `db_uri` argument before making any network connection.

| URI scheme | Driver class | Example URI |
|---|---|---|
| `bolt://` | `Neo4jDriver` | `bolt://localhost:7687` |
| `bolt+s://` | `Neo4jDriver` | `bolt+s://neo4j.corp:7687` |
| `bolt+ssc://` | `Neo4jDriver` | `bolt+ssc://neo4j.corp:7687` |
| `neo4j://` | `Neo4jDriver` | `neo4j://localhost:7687` |
| `neo4j+s://` | `Neo4jDriver` | `neo4j+s://neo4j.corp:7687` |
| `neo4j+ssc://` | `Neo4jDriver` | `neo4j+ssc://neo4j.corp:7687` |
| `indradb://` | `IndraDBDriver` | `indradb://localhost:27615` |
| `grpc://` | `IndraDBDriver` | `grpc://localhost:27615` |
| `indradb+grpc://` | `IndraDBDriver` | `indradb+grpc://localhost:27615` |

Any other scheme (including empty string or a URI with no `://`) raises
`INVALID_ARGUMENT` **before** path validation or database connection is
attempted. This ordering is enforced by design §2 and tested in
`tests/unit/test_driver_dispatch.py`.

---

## 2. Install commands

### Neo4j backend only

```bash
pip install "cpp-mcp[graphdb-neo4j]"
# or with uv:
uv sync --extra graphdb-neo4j
```

Pulls in: `neo4j>=5,<6` (Bolt driver).

### IndraDB backend only

```bash
pip install "cpp-mcp[graphdb-indradb]"
# or with uv:
uv sync --extra graphdb-indradb
```

Pulls in: `indradb>=3.0,<4` (gRPC client; transitively `grpcio`, `protobuf`).

### Both backends

```bash
pip install "cpp-mcp[graphdb]"
# or with uv:
uv sync --extra graphdb
```

The `graphdb` meta-extra is equivalent to `graphdb-neo4j` + `graphdb-indradb`.
If you only need one backend, install the specific extra to avoid pulling in
the other backend's dependencies.

---

## 3. Daemon bring-up

### Neo4j (Community Edition, Bolt)

```bash
docker run --rm -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=none \
  neo4j:5
```

Default Bolt URI: `bolt://localhost:7687`

Enable real-Neo4j integration tests:

```bash
export NEO4J_TEST_URI="bolt://localhost:7687"
uv run pytest -q tests/bdd/test_export_to_graphdb.py
```

### IndraDB (RocksDB backend)

A `docker compose` fragment is provided at `tests/fixtures/indradb-compose.yml`:

```bash
docker compose -f tests/fixtures/indradb-compose.yml up -d
```

Default gRPC URI: `indradb://localhost:27615`

Enable real-IndraDB integration tests:

```bash
export INDRADB_TEST_URI="indradb://localhost:27615"
uv run pytest -q tests/bdd/test_export_to_indradb.py
```

Live integration tests are gated on the environment variable; they are skipped
when it is unset (US-G5/AC-3). The fake-driver BDD scenarios run without a
daemon (no environment variable required).

---

## 4. Error code reference

The full error envelope shape is:

```json
{ "code": "...", "message": "...", "tool": "cpp_export_to_graphdb", "request_id": "..." }
```

### v3 error codes (extended from v2)

| Code | Meaning | Common cause | Fix |
|---|---|---|---|
| `FILE_NOT_FOUND` | Source file or build directory does not exist | Path typo; file deleted | Check the path exists and is accessible |
| `INVALID_POSITION` | `line`/`col` out of range for the file | Off-by-one in caller | Use 1-based line/col within the file's actual range |
| `INVALID_RANGE` | `start_line`/`end_line` invalid or reversed | Swapped bounds | Ensure `start_line <= end_line` and both are within range |
| `INVALID_ARGUMENT` | Malformed or unknown `db_uri` scheme; `build_path` is a file not a directory | Unknown URI scheme; wrong build path type | Use a supported URI scheme (see §1); pass a directory for `build_path` |
| `PATH_VIOLATION` | Resolved path falls outside `CPP_MCP_ALLOWED_ROOTS` | `..` traversal; symlink outside root | Run `realpath` on the path; ensure it is under an allowed root |
| `DEPENDENCY_MISSING` | The Python driver package for the selected backend is not installed | `neo4j` or `indradb` package absent from the environment | Install the appropriate extra (see §2): `pip install "cpp-mcp[graphdb-neo4j]"` or `pip install "cpp-mcp[graphdb-indradb]"` |
| `DB_UNREACHABLE` | Driver package is installed but the database refused the connection | Daemon not running; wrong host/port; firewall | Start the daemon (see §3); verify the URI matches the listening address |
| `PARSE_ERROR` | libclang produced zero AST nodes for the file | Invalid C++; missing includes | Check the file compiles cleanly; verify `CPP_MCP_DEFAULT_FLAGS` includes necessary `-I` paths |
| `INTERNAL_ERROR` | Unexpected Python exception in the tool handler | Bug; libclang crash | Enable `CPP_MCP_LOG_LEVEL=DEBUG` and inspect stderr |

### `DEPENDENCY_MISSING` detail

`DEPENDENCY_MISSING` was introduced in v3 (ADR-13) to distinguish the case
where the Python driver package is simply not installed from the case where the
database is installed but not reachable (`DB_UNREACHABLE`). The error message
always includes the exact install command:

- For Neo4j: `'neo4j Python driver is not installed. Install with: pip install "cpp-mcp[graphdb-neo4j]"'`
- For IndraDB: `'indradb Python driver is not installed. Install with: pip install "cpp-mcp[graphdb-indradb]"'`

`DEPENDENCY_MISSING` is mapped **above** `DB_UNREACHABLE` in the exception
dispatch table so it is never shadowed (ADR-13 / `error_envelope.py`).

---

## 5. License posture

Both graphdb backends run as separate daemons; their licenses apply only to
the daemon binaries, not to the `cpp-mcp` Python package itself.

| Component | License | Notes |
|---|---|---|
| **Neo4j Community** daemon | GPLv3 | The Neo4j Community Edition container image (`neo4j:5`) is GPL-licensed. The `neo4j` Python Bolt driver (`neo4j>=5,<6`) is Apache 2.0. Running the daemon and connecting via Bolt does not impose GPL obligations on `cpp-mcp` callers. |
| **IndraDB** daemon | MPL-2.0 | The IndraDB server binary and gRPC API are MPL-2.0. The `indradb` Python client library (`indradb>=3.0,<4`) is also MPL-2.0. MPL-2.0 is a file-level copyleft; it does not extend to code outside the IndraDB source files. `cpp-mcp` does not incorporate IndraDB source, so no MPL obligations propagate to `cpp-mcp` users. |
| **cpp-mcp** package itself | (project license) | No GPL or MPL code is vendored into `cpp-mcp`. The optional extras pull runtime deps that must be installed separately. |

If your deployment policy prohibits GPL or MPL dependencies at the daemon
level, do not run the corresponding daemon. The `cpp-mcp` server package
remains usable without either backend.

---

## 6. References

- v2 runbook: `.claude/handoff/v2/runbook.md` (FastMCP startup, transport, upgrade-check)
- CHARTER: `.claude/handoff/v3/CHARTER.md`
- Design: `.claude/handoff/v3/design.md`
- ADR-12 (URI dispatch): `.claude/handoff/v3/adr-12.md`
- ADR-13 (DEPENDENCY_MISSING): `.claude/handoff/v3/adr-13.md`
- ADR-14 (USR→UUID namespace): `.claude/handoff/v3/adr-14.md`
- ADR-15 (property serialization): `.claude/handoff/v3/adr-15.md`
- Plan: `.claude/handoff/v3/plan.md` §S6
- Cognee tags: `task:graphdb-multi`, `role:developer`
