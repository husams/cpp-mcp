# ADR-16: Local IndraDB distribution — cargo-install, not Docker

Status: accepted
Date: 2026-05-17
Resolves: OQ-6-1
Bound stories: US-V4-2, US-V4-6

## Context

The v3 ship referenced `tests/fixtures/indradb-compose.yml` pointing at the Docker image `indradb/indradb:5.0.0`. That image does not exist on Docker Hub (`docker pull` returns 404). Post-ship findings record this as defect 3 of `[[project-graphdb-v3-post-ship-findings]]`. Local-dev IndraDB has been broken since v3 ship; the live reproducer that surfaced defects 1–5 used the `cargo install indradb` path instead.

Forces:

- Need a **single canonical local-dev path** for v4 integration tests (US-V4-2) and any future engineer reading the README.
- Must not depend on an image that no public registry serves.
- Should not require running a private container registry just for one Rust binary.
- Test fixtures should autostart the daemon (`INDRADB_AUTOSTART=1`) without Docker-in-the-loop, since GitHub-style CI doesn't have rootful Docker by default and the project's GitLab runners are not yet configured for it (v5).

## Decision

Use `cargo install indradb` followed by `indradb-server memory` as the **only** supported local-dev path for IndraDB.

- Delete `tests/fixtures/indradb-compose.yml`.
- Document the cargo path in README under `## Local development (IndraDB)`.
- Update `.claude/handoff/v3/runbook.md` references to the broken image.
- The `indradb_daemon` pytest fixture (US-V4-2) shells out to `indradb-server memory` directly when `INDRADB_AUTOSTART=1`.

## Alternatives considered

a. **Self-built image pushed to `registry.senussi.me`.**
   Pros: single `docker compose up` for developers who prefer containers; CI can pull instead of installing Rust.
   Cons: requires maintaining a Dockerfile, a build job, a registry namespace, an image-rotation policy. Defers the actual fix and introduces ongoing infra cost for a tool that has a 30-second `cargo install` story. PM position (per OQ-6-1) explicitly favors cargo-only for "simpler, less infra overhead". No measured benefit to a custom image until v5 CI exists.

b. **Use the official upstream image at a working tag** (e.g. `indradb/indradb-server:<latest>`).
   Cons: there is no such image in Docker Hub under any tag. The `indradb` organization on Docker Hub publishes nothing — the project ships binaries via `cargo install` only. Verified manually on 2026-05-17.

c. **Status quo + skip-only fixture** (keep the broken compose file, just skip in tests).
   Cons: the compose file is a footgun — every new contributor will try `docker compose up` and hit 404 confusion. The defect must be fixed at source.

## Consequences

Positive:

- One supported path; documentation and fixtures align.
- No registry, no Dockerfile, no image-rotation maintenance.
- Removes a known-broken file from the repo.
- Matches the live reproducer that found defects 1–5.

Negative:

- Developers without Rust toolchain installed need to install `rustup` once (~2 minutes). Mitigated by README link.
- CI (v5) will need either a pre-built Rust binary cache or a `cargo install` step in its image. Recorded as a v5 follow-up, not a v4 blocker.

Follow-ups:

- v5 CI story: package the binary in the CI runner image or use a Rust-toolchain step.
- If `cargo install indradb` ever fails on a major version, the README must point to the pinned commit-SHA that v4 was tested against. Today (2026-05-17): the upstream `main` branch HEAD builds clean.

## References

- `[[project-graphdb-v3-post-ship-findings]]` — defect 3
- `tests/fixtures/indradb-compose.yml` (slated for deletion)
- `README.md` (slated for `## Local development (IndraDB)` addition)
- requirements.md US-V4-6, OQ-6-1
- scenarios.md SC-V4-6-01, SC-V4-6-02
