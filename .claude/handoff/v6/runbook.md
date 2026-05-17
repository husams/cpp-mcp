# Runbook — cpp-mcp v0.4.0 Release + Post-Install Smoke Test

Run: cpp-mcp-v6
Date: 2026-05-17
Scope: git commit/tag, GitHub release, post-install smoke test of query_graphdb + describe_graph_schema

---

## Trigger

When all of the following are true:
- QA sign-off in test-report.md (no open QA_DEFECT entries) — confirmed
- `uv build` produces `dist/cpp_mcp-0.4.0.tar.gz` + `dist/cpp_mcp-0.4.0-py3-none-any.whl` — confirmed
- Human reviewer has inspected `git diff`

---

## Prerequisites

- Working directory: `/Users/husam/workspace/cpp-mcp`
- GitHub remote: `origin` → `github.com/husams/cpp-mcp`
- `gh` CLI authenticated
- `uv` available (`uv --version`)
- For smoke test: IndraDB daemon running (or `INDRADB_AUTOSTART=1`) and a compile_commands.json-bearing repo on disk

---

## Steps

### 1. Final build verification (read-only, safe to re-run)

```bash
cd /Users/husam/workspace/cpp-mcp

# Confirm version
uv run python -c "import importlib.metadata as m; print(m.version('cpp-mcp'))"
# Expected: 0.4.0

# Confirm build artifacts exist
ls dist/cpp_mcp-0.4.0-py3-none-any.whl dist/cpp_mcp-0.4.0.tar.gz
```

### 2. Stage changes (exclude handoff dir)

```bash
cd /Users/husam/workspace/cpp-mcp

# Stage all modified source, tests, docs
git add \
  CHANGELOG.md README.md pyproject.toml \
  src/cpp_mcp/core/error_envelope.py \
  src/cpp_mcp/core/query_config.py \
  src/cpp_mcp/graphdb/exporter.py \
  src/cpp_mcp/graphdb/neo4j_driver.py \
  src/cpp_mcp/graphdb/indradb_query_executor.py \
  src/cpp_mcp/graphdb/neo4j_query_executor.py \
  src/cpp_mcp/graphdb/query_executor.py \
  src/cpp_mcp/graphdb/schema_introspector.py \
  src/cpp_mcp/graphdb/schema_version.py \
  src/cpp_mcp/server/app.py \
  src/cpp_mcp/tools/describe_graph_schema.py \
  src/cpp_mcp/tools/query_graphdb.py \
  tests/fixtures/fake_indradb.py \
  tests/bdd/features/query_graphdb.feature \
  tests/bdd/test_query_graphdb_bdd.py \
  tests/integration/test_describe_graph_schema_e2e.py \
  tests/integration/test_query_graphdb_e2e.py \
  tests/unit/core/ \
  tests/unit/graphdb/ \
  tests/unit/tools/ \
  tests/unit/test_envelope_codes.py \
  tests/unit/test_envelope_decorator_order.py \
  tests/unit/test_error_envelope.py \
  tests/unit/test_rename_invariant.py \
  tests/unit/test_server_app.py \
  tests/unit/test_tool_registration.py

# Do NOT stage .claude/handoff/v6/
```

### 3. Commit

```bash
git config user.name "Claude"
git config user.email "claude@senussi.me"

git commit -m "$(cat <<'EOF'
v6: add query_graphdb + describe_graph_schema (0.4.0)

Closes S1 of cpp-mcp-codexgraph-gap roadmap. Additive surface;
no breaking changes to existing 7 tools. 880 unit+BDD + 10
integration tests pass. ADRs 22/23/24 accepted.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### 4. Tag

```bash
git tag -a v0.4.0 -m "Release 0.4.0 — graph query surface (query_graphdb + describe_graph_schema)"
```

### 5. Push branch and tag

```bash
git push origin main
git push origin v0.4.0
```

### 6. Create GitHub release with artifacts

```bash
gh release create v0.4.0 \
  dist/cpp_mcp-0.4.0.tar.gz \
  dist/cpp_mcp-0.4.0-py3-none-any.whl \
  --title "v0.4.0 — Graph query surface" \
  --notes "$(cat <<'EOF'
## What's new

- `query_graphdb` — read-only property-graph queries against Neo4j (Cypher, EXPLAIN-enforced) or IndraDB (7-verb JSON subset per ADR-23)
- `describe_graph_schema` — live schema discovery for both backends; surfaces schema_version stamps and mismatch notes (ADR-24)

## Additive release

No breaking changes to the existing 7 tools from v0.3.0.

## Backends

- Neo4j: Cypher read-only enforcement via EXPLAIN plan-walk (ADR-22)
- IndraDB: 7-verb JSON query subset (all_vertices, all_edges, vertex_with_id, vertex_with_type, edge_with_id, edge_with_type, edge_between_vertices)

## Test coverage

880 unit + BDD tests, 10 IndraDB live integration tests.
EOF
)"
```

### 7. (Optional) Publish to PyPI

```bash
uv publish
# Prompts for PyPI token; or set TWINE_USERNAME/__TOKEN__ env before running
```

---

## Verification (post-release)

```bash
# Confirm GitHub release exists
gh release view v0.4.0

# Confirm tag on remote
git ls-remote origin refs/tags/v0.4.0
```

---

## Post-install smoke test — query_graphdb + describe_graph_schema

Run after installing the wheel into a test environment against a live IndraDB or Neo4j instance.

### Setup

```bash
# Create isolated env
uv venv /tmp/cpp-mcp-smoke
source /tmp/cpp-mcp-smoke/bin/activate
pip install /Users/husam/workspace/cpp-mcp/dist/cpp_mcp-0.4.0-py3-none-any.whl

# For IndraDB smoke: start daemon
# INDRADB_AUTOSTART=1 or start indradb-server separately and note the URI
INDRADB_URI="indradb://127.0.0.1:27615"

# For Neo4j smoke: have a running Neo4j instance
# NEO4J_URI="bolt://localhost:7687"
```

### Step A — Ingest a codebase first

```python
# run in python -c or a small script
import subprocess, json

result = subprocess.run(
    ["python", "-m", "cpp_mcp.cli", "call", "ingest_code"],
    input=json.dumps({
        "compile_commands_path": "/path/to/compile_commands.json",
        "db_uri": "indradb://127.0.0.1:27615"
    }),
    capture_output=True, text=True
)
print(json.loads(result.stdout))
# Expected: {"status": "ok", "vertices_written": N, "edges_written": M, ...}
```

### Step B — describe_graph_schema

```python
result = subprocess.run(
    ["python", "-m", "cpp_mcp.cli", "call", "describe_graph_schema"],
    input=json.dumps({
        "db_uri": "indradb://127.0.0.1:27615"
    }),
    capture_output=True, text=True
)
schema = json.loads(result.stdout)
assert schema["schema_version"] == "v1", f"Expected v1, got {schema['schema_version']}"
assert len(schema["node_types"]) > 0, "Expected at least one node type"
print("node_types:", [t["name"] for t in schema["node_types"]])
print("edge_types:", [t["name"] for t in schema["edge_types"]])
# Expected for {fmt}/os.cc: Variable, TypeAlias, Function, Class, Namespace, File
#              DEFINES, REFERENCES
```

### Step C — query_graphdb (all_vertices)

```python
result = subprocess.run(
    ["python", "-m", "cpp_mcp.cli", "call", "query_graphdb"],
    input=json.dumps({
        "db_uri": "indradb://127.0.0.1:27615",
        "query": json.dumps({"query": "all_vertices"})
    }),
    capture_output=True, text=True
)
qr = json.loads(result.stdout)
assert qr["status"] == "ok"
assert isinstance(qr["rows"], list)
assert isinstance(qr["stats"]["truncated"], bool)
print(f"total vertices returned: {len(qr['rows'])}, truncated: {qr['stats']['truncated']}")
```

### Step D — query_graphdb (vertex_with_type, row_limit)

```python
result = subprocess.run(
    ["python", "-m", "cpp_mcp.cli", "call", "query_graphdb"],
    input=json.dumps({
        "db_uri": "indradb://127.0.0.1:27615",
        "query": json.dumps({"query": "vertex_with_type", "args": {"t": "Function"}}),
        "row_limit": 10
    }),
    capture_output=True, text=True
)
qr = json.loads(result.stdout)
assert qr["status"] == "ok"
assert len(qr["rows"]) <= 10
print(f"Function vertices (capped to 10): {len(qr['rows'])}")
```

### Step E — read-only enforcement (Neo4j path only)

```python
# Should return QUERY_UNSUPPORTED or READ_ONLY_VIOLATION, NOT execute the write
result = subprocess.run(
    ["python", "-m", "cpp_mcp.cli", "call", "query_graphdb"],
    input=json.dumps({
        "db_uri": "bolt://localhost:7687",
        "query": "CREATE (n:Test) RETURN n"
    }),
    capture_output=True, text=True
)
qr = json.loads(result.stdout)
assert qr["status"] == "error"
assert qr["code"] in ("READ_ONLY_VIOLATION", "QUERY_PARSE_ERROR")
print("Write blocked correctly:", qr["code"])
```

### Expected pass criteria

| Check | Pass condition |
|---|---|
| `describe_graph_schema` returns `schema_version = "v1"` | yes |
| `node_types` list is non-empty and sorted by count desc | yes |
| `query_graphdb` `all_vertices` returns rows list | yes |
| `query_graphdb` with `row_limit=10` returns <= 10 rows | yes |
| Neo4j `CREATE` statement returns error code in (READ_ONLY_VIOLATION, QUERY_PARSE_ERROR) | yes |

---

## Rollback

**Before push:**
```bash
git reset HEAD~1        # undo commit, keep staged files
git tag -d v0.4.0       # delete local tag
```

**After push (before PyPI):**
```bash
git push origin --delete v0.4.0
git revert HEAD --no-edit
git push origin main
# Delete GitHub release:
gh release delete v0.4.0 --yes
```

**After PyPI publish:**
PyPI does not support yanking by default. Contact PyPI support or publish a 0.4.1 patch.

---

## On-call notes

- No cluster resources touched. All rollback is git-only.
- `query_graphdb` is read-only by design; it cannot mutate the graph. Any data-loss concern traces to `ingest_code`, not to v6 additions.
- Integration test runtime is ~415s (7 min) per test-report.md observation — a known performance smell (no shared ingest fixture). Unit suite (880 tests) runs in seconds.
- If IndraDB daemon is not running, `query_graphdb` and `describe_graph_schema` return `{"status":"error","code":"DB_UNREACHABLE"}` — not a crash.
- Timeout is controlled by `CPP_MCP_QUERY_TIMEOUT_SECONDS` env var (default 30, clamped [1, 120]).

---

## References

- deploy-notes.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/deploy-notes.md
- test-report.md: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/test-report.md
- plan.md stories S6 exit criteria: /Users/husam/workspace/cpp-mcp/.claude/handoff/v6/plan.md
- wiki: pages/code/cpp-mcp-v6.md
- ADR-22 (Neo4j EXPLAIN read-only), ADR-23 (IndraDB query subset), ADR-24 (schema discovery)
