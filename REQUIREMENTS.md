# C++ Semantic Analysis MCP Server - Requirements

## 1. Objective
Build a Model Context Protocol (MCP) server that provides high-precision semantic tools for C++ codebase navigation, structural understanding, and graph-based persistence using `libclang`. The server enables LLM agents to deeply inspect and understand complex C++ code via compiler-level AST traversal.

## 2. Core Architectural Principle: Stateless Build Context
*   **No Global State:** The server does not maintain or "set" a global project root or active configuration.
*   **Explicit Parameters:** Every tool call requiring compilation context MUST accept an optional `build_path` (the directory containing `compile_commands.json`).
*   **Dynamic Flag Discovery:** The server uses `libclang`'s `CompilationDatabase` API to resolve compilation flags (include paths, macros, standards) per-file dynamically based on the provided `build_path`. This allows agents to seamlessly interleave tasks across multiple repositories in the same session without configuration collisions.

## 3. Functional Requirements & Toolset

### A. Semantic Navigation & Inspection
*   `cpp_get_definition(file_path, line, col, build_path=None)`
    *   Locate the exact definition of any symbol (resolving macros and templates).
*   `cpp_get_references(file_path, line, col, build_path=None)`
    *   Find all usages of a symbol.
*   `cpp_get_type_info(file_path, line, col, build_path=None)`
    *   Returns fully qualified type name, size, alignment, and canonical type (useful for resolving `auto` or complex templates).

### B. Structural Analysis & AST
*   `cpp_get_ast(file_path, build_path=None, format="json", depth=3, start_line=None, end_line=None)`
    *   **Annotated AST:** Returns a hierarchical tree of nodes (Declarations, Statements, Expressions).
    *   **Annotation:** Each node includes resolved types, storage classes, and symbol IDs.
    *   **Formats:** Supports `json` for direct LLM context or `graph` for node/edge lists.
    *   **Scoping:** Uses `depth`, `start_line`, and `end_line` to prevent context window overflow.

### C. Module & Interface Discovery
*   `cpp_get_header_info(file_path, build_path=None)`
    *   Returns direct and transitive includes, identifies missing or orphaned headers, and extracts a summary of exported public symbols (the API interface) without implementation details.
*   `cpp_get_preprocessor_state(file_path, build_path=None)`
    *   Returns active `#define` macros and the evaluated state of conditional compilation (`#ifdef`) blocks as seen by the compiler.

### D. Persistence & Knowledge Graph
*   `cpp_export_to_graphdb(file_path_or_dir, build_path, db_uri)`
    *   Directly ingest the AST and symbol relationships into a local Graph Database (e.g., Cognee, Neo4j).
    *   **Schema Nodes:** File, Namespace, Class, Function, Variable, Macro, Type Alias.
    *   **Schema Edges:** `DEFINES`, `DECLARES`, `CALLS`, `INHERITS`, `REFERENCES`, `INCLUDES`, `MEMBER_OF`.

## 4. Technical Specifications

*   **Core Engine:** `libclang` (Python bindings `clang.cindex`).
*   **Context Resolution Pipeline:**
    1. If `build_path` is provided: Query `CompilationDatabase.fromDirectory(build_path)`.
    2. Extract specific compile arguments for `file_path` from the database.
    3. If no `build_path` is provided, or the file is missing from the database, fallback to a standard set of `default_flags` (e.g., `["-std=c++20", "-I.", "-x", "c++"]`).
*   **Performance Optimization:**
    *   Implement an internal **Translation Unit (TU) Cache** keyed by a tuple of `(file_path, build_path)` with an LRU (Least Recently Used) eviction policy. This ensures subsequent queries on the same file are instant.

## 5. Security & Safety
*   **Read-Only:** All tools (except the GraphDB exporter) must be strictly read-only and never modify the source files.
*   **Path Validation:** Ensure all `file_path` and `build_path` arguments are bounded and validated to prevent arbitrary file system access outside intended directories.
