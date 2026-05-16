"""Frozen v1 tool input schemas — authoritative parity baseline for test_schema_parity.py.

These dicts are the v1 schema contract (originally in server/schemas.py), expressed in
the canonical form used by the _normalize() helper in test_schema_parity.py:

  - Optional types are represented as anyOf: [{type:X},{type:null}] (FastMCP's form).
  - enum values are preserved where v1 had them (cpp_get_ast.format).
  - minimum constraints are preserved where v1 had them (cpp_get_ast.depth).
  - title is absent (normalizer strips it).
  - description is present and non-empty for every argument.
  - additionalProperties is False for every tool.

ADR-6 (v2): schemas moved from src/ to tests/fixtures/ so the source of truth for
schema validation lives in the test tree, not in production code.
"""

from __future__ import annotations

from typing import Any


def _str(desc: str) -> dict[str, Any]:
    return {"type": "string", "description": desc}


def _int(desc: str) -> dict[str, Any]:
    return {"type": "integer", "description": desc}


def _opt_str(desc: str) -> dict[str, Any]:
    return {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": None,
        "description": desc,
    }


def _opt_int(desc: str) -> dict[str, Any]:
    return {
        "anyOf": [{"type": "integer"}, {"type": "null"}],
        "default": None,
        "description": desc,
    }


EXPECTED: dict[str, dict[str, Any]] = {
    "cpp_get_definition": {
        "type": "object",
        "properties": {
            "file_path": _str("Absolute path to the C++ source file."),
            "line": _int("1-based line number of the symbol."),
            "col": _int("1-based column number of the symbol."),
            "build_path": _opt_str(
                "Optional path to the build directory containing compile_commands.json."
            ),
        },
        "required": ["file_path", "line", "col"],
        "additionalProperties": False,
    },
    "cpp_get_references": {
        "type": "object",
        "properties": {
            "file_path": _str("Absolute path to the C++ source file."),
            "line": _int("1-based line number of the symbol."),
            "col": _int("1-based column number of the symbol."),
            "build_path": _opt_str(
                "Optional path to the build directory containing compile_commands.json."
            ),
        },
        "required": ["file_path", "line", "col"],
        "additionalProperties": False,
    },
    "cpp_get_type_info": {
        "type": "object",
        "properties": {
            "file_path": _str("Absolute path to the C++ source file."),
            "line": _int("1-based line number of the symbol."),
            "col": _int("1-based column number of the symbol."),
            "build_path": _opt_str(
                "Optional path to the build directory containing compile_commands.json."
            ),
        },
        "required": ["file_path", "line", "col"],
        "additionalProperties": False,
    },
    "cpp_get_ast": {
        "type": "object",
        "properties": {
            "file_path": _str("Absolute path to the C++ source file."),
            "build_path": _opt_str(
                "Optional path to the build directory containing compile_commands.json."
            ),
            "format": {
                "type": "string",
                "enum": ["json", "graph"],
                "description": (
                    "Output format: 'json' (hierarchical tree) or 'graph' (nodes+edges)."
                ),
                "default": "json",
            },
            "depth": {
                "type": "integer",
                "description": "Maximum nesting depth for JSON format (default 3).",
                "default": 3,
                "minimum": 1,
            },
            "start_line": _opt_int("First line of line-range filter (1-based, inclusive)."),
            "end_line": _opt_int("Last line of line-range filter (1-based, inclusive)."),
        },
        "required": ["file_path"],
        "additionalProperties": False,
    },
    "cpp_get_header_info": {
        "type": "object",
        "properties": {
            "file_path": _str("Absolute path to the C++ header or source file."),
            "build_path": _opt_str(
                "Optional path to the build directory containing compile_commands.json."
            ),
        },
        "required": ["file_path"],
        "additionalProperties": False,
    },
    "cpp_get_preprocessor_state": {
        "type": "object",
        "properties": {
            "file_path": _str("Absolute path to the C++ source file."),
            "build_path": _opt_str(
                "Optional path to the build directory containing compile_commands.json."
            ),
        },
        "required": ["file_path"],
        "additionalProperties": False,
    },
    "cpp_export_to_graphdb": {
        "type": "object",
        "properties": {
            "file_path_or_dir": _str("Absolute path to a C++ source file or directory to export."),
            "build_path": _str(
                "Absolute path to the build directory containing compile_commands.json."
                " Required for graph export."
            ),
            "db_uri": _str(
                "Bolt URI for the target graph database (e.g. 'bolt://localhost:7687')."
            ),
            "recursive": {
                "type": "boolean",
                "description": (
                    "If true and file_path_or_dir is a directory, recurse into sub-directories."
                ),
                "default": False,
            },
        },
        "required": ["file_path_or_dir", "build_path", "db_uri"],
        "additionalProperties": False,
    },
}
