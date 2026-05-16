"""GraphDB schema: node and edge type constants (ADR-7).

Node types: File, Namespace, Class, Function, Variable, Macro, TypeAlias.
Edge types: DEFINES, DECLARES, CALLS, INHERITS, REFERENCES, INCLUDES, MEMBER_OF.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Node type constants
# ---------------------------------------------------------------------------

NODE_FILE = "File"
NODE_NAMESPACE = "Namespace"
NODE_CLASS = "Class"
NODE_FUNCTION = "Function"
NODE_VARIABLE = "Variable"
NODE_MACRO = "Macro"
NODE_TYPE_ALIAS = "TypeAlias"

ALL_NODE_TYPES: frozenset[str] = frozenset(
    {
        NODE_FILE,
        NODE_NAMESPACE,
        NODE_CLASS,
        NODE_FUNCTION,
        NODE_VARIABLE,
        NODE_MACRO,
        NODE_TYPE_ALIAS,
    }
)

# ---------------------------------------------------------------------------
# Edge type constants
# ---------------------------------------------------------------------------

EDGE_DEFINES = "DEFINES"
EDGE_DECLARES = "DECLARES"
EDGE_CALLS = "CALLS"
EDGE_INHERITS = "INHERITS"
EDGE_REFERENCES = "REFERENCES"
EDGE_INCLUDES = "INCLUDES"
EDGE_MEMBER_OF = "MEMBER_OF"

ALL_EDGE_TYPES: frozenset[str] = frozenset(
    {
        EDGE_DEFINES,
        EDGE_DECLARES,
        EDGE_CALLS,
        EDGE_INHERITS,
        EDGE_REFERENCES,
        EDGE_INCLUDES,
        EDGE_MEMBER_OF,
    }
)
