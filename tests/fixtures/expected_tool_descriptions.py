"""Expected v5 tool descriptions — authoritative source for test_tool_registration.py.

These strings must match the `description=` values in each `@mcp.tool(...)` decorator
in `src/cpp_mcp/tools/*.py`.  If a description changes, update here too.
"""

from __future__ import annotations

EXPECTED_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_definition": (
        "Navigate to the canonical definition of a C++ symbol at a given source position."
    ),
    "get_references": ("Find all usages of a C++ symbol within the current translation unit."),
    "get_type_info": (
        "Retrieve type details (size, alignment, qualifiers, canonical form) for a C++ symbol."
    ),
    "get_ast": ("Return an annotated AST subtree in JSON or graph format for a C++ source file."),
    "get_header_info": (
        "Inspect the include graph and exported symbols for a C++ header or source file."
    ),
    "get_preprocessor_state": (
        "Retrieve active macro definitions and evaluated preprocessor conditional branch state."
    ),
    "ingest_code": (
        "Export C++ symbols and relationships from a file or directory to a graph database."
    ),
}
