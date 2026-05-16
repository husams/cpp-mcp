# ADR-4: Symlink policy — resolve then check, reject if resolved path leaves allowed roots
Status: accepted
Context:
  - OQ-15: symlinks may be used innocently (build trees, vendored deps via symlink) or maliciously (escape allowed root).
  - US-12/AC-3 mandates rejection of symlinks resolving outside allowed root.
  - Two viable policies: (a) resolve fully then check inclusion, (b) reject any symlinked input outright.

Decision:
  - **Resolve then check**. Specifically, `path_guard.validate_path` performs:
    1. Reject if literal `..` segments appear in the raw input (catches obvious traversal before any syscall).
    2. Compute `realpath` = `os.path.realpath(os.path.abspath(input))` — this follows ALL symlinks recursively.
    3. Reject if `os.path.commonpath([realpath, root])` != `root` for every configured root.
    4. Reject (FILE_NOT_FOUND) if path does not exist after resolution.
  - The `realpath` value is what gets passed to libclang and used as the cache key.
  - Same algorithm for both `file_path` and `build_path`.

Alternatives considered:
  - Deny all symlinks (option b): rejected — breaks common C++ workflows (CMake symlinks generated headers, Bazel sandboxes, Nix store paths). Would be hostile to legitimate users.
  - Resolve but don't check (just trust the realpath): rejected — defeats the security boundary.
  - Use `os.path.relpath` instead of `commonpath`: rejected — `relpath` doesn't detect escapes cleanly (`relpath("/etc", "/projects")` returns `"../etc"`, not an error).

Consequences:
  - Positive: legitimate symlink-heavy build systems work transparently.
  - Negative: a symlink target outside allowed roots produces the same `PATH_VIOLATION` regardless of intent; user sees the input path in the error, not the resolved target (to avoid information leak about the FS layout). Documented.
  - Edge case: TOCTOU — symlink could change between validate and parse. Mitigation: we pass the already-resolved realpath downstream; libclang opens that, not the original symlink. Race window is closed.

References:
  - requirements.md US-12/AC-3, US-12/AC-4, US-12/AC-6, OQ-15
  - scenarios.md SC-US-1-12, SC-US-12-3, SC-US-12-4
  - design.md §2 (path_guard)
