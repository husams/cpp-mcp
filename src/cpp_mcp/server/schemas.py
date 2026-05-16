"""JSON Schema definitions for each MCP tool's input.

These dicts are passed to ``mcp.types.Tool(inputSchema=...)`` and validated
by the MCP SDK on every call_tool invocation.

All file_path / build_path arguments are typed as strings (the MCP client
serialises them over JSON-RPC). Line/col arguments are integers.
"""

from __future__ import annotations

from typing import Any


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def _nullable_string(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


def _nullable_integer(description: str) -> dict[str, Any]:
    return {"type": ["integer", "null"], "description": description}


CPP_GET_DEFINITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": _string("Absolute path to the C++ source file."),
        "line": _integer("1-based line number of the symbol."),
        "col": _integer("1-based column number of the symbol."),
        "build_path": _nullable_string(
            "Optional path to the build directory containing compile_commands.json."
        ),
    },
    "required": ["file_path", "line", "col"],
    "additionalProperties": False,
}

CPP_GET_REFERENCES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": _string("Absolute path to the C++ source file."),
        "line": _integer("1-based line number of the symbol."),
        "col": _integer("1-based column number of the symbol."),
        "build_path": _nullable_string(
            "Optional path to the build directory containing compile_commands.json."
        ),
    },
    "required": ["file_path", "line", "col"],
    "additionalProperties": False,
}

CPP_GET_TYPE_INFO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": _string("Absolute path to the C++ source file."),
        "line": _integer("1-based line number of the symbol."),
        "col": _integer("1-based column number of the symbol."),
        "build_path": _nullable_string(
            "Optional path to the build directory containing compile_commands.json."
        ),
    },
    "required": ["file_path", "line", "col"],
    "additionalProperties": False,
}

CPP_GET_AST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": _string("Absolute path to the C++ source file."),
        "build_path": _nullable_string(
            "Optional path to the build directory containing compile_commands.json."
        ),
        "format": {
            "type": "string",
            "enum": ["json", "graph"],
            "description": "Output format: 'json' (hierarchical tree) or 'graph' (nodes+edges).",
            "default": "json",
        },
        "depth": {
            "type": "integer",
            "description": "Maximum nesting depth for JSON format (default 3).",
            "default": 3,
            "minimum": 1,
        },
        "start_line": _nullable_integer("First line of line-range filter (1-based, inclusive)."),
        "end_line": _nullable_integer("Last line of line-range filter (1-based, inclusive)."),
    },
    "required": ["file_path"],
    "additionalProperties": False,
}

CPP_GET_HEADER_INFO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": _string("Absolute path to the C++ header or source file."),
        "build_path": _nullable_string(
            "Optional path to the build directory containing compile_commands.json."
        ),
    },
    "required": ["file_path"],
    "additionalProperties": False,
}

CPP_GET_PREPROCESSOR_STATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": _string("Absolute path to the C++ source file."),
        "build_path": _nullable_string(
            "Optional path to the build directory containing compile_commands.json."
        ),
    },
    "required": ["file_path"],
    "additionalProperties": False,
}

CPP_EXPORT_TO_GRAPHDB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path_or_dir": _string("Absolute path to a C++ source file or directory to export."),
        "build_path": _string(
            "Absolute path to the build directory containing compile_commands.json."
            " Required for graph export."
        ),
        "db_uri": _string("Bolt URI for the target graph database (e.g. 'bolt://localhost:7687')."),
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
}
