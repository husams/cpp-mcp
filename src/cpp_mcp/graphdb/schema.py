"""GraphDB schema: node and edge type constants (ADR-7).

Node types: File, Namespace, Class, Function, Variable, Field, GlobalVariable,
            Macro, TypeAlias.
Edge types: DEFINES, DECLARES, CALLS, INHERITS, REFERENCES, INCLUDES, MEMBER_OF.

v7-S1 additions (ADR-25):
  NODE_FIELD         — non-static class/struct data member (FIELD_DECL).
  NODE_GLOBAL_VARIABLE — namespace-scope, file-scope, or static class data
                         member in its out-of-class form (VAR_DECL /
                         static FIELD_DECL).
  NODE_VARIABLE is retained as a read-side compatibility constant (ADR-25 D1)
  and remains in ALL_NODE_TYPES; the write path still emits it for PARM_DECL
  cursors (transitional until S2 introduces Parameter).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Node type constants
# ---------------------------------------------------------------------------

NODE_FILE = "File"
NODE_NAMESPACE = "Namespace"
NODE_CLASS = "Class"
NODE_FUNCTION = "Function"
NODE_VARIABLE = "Variable"  # retained: read-compat + PARM_DECL (ADR-25 D1, D2)
NODE_FIELD = "Field"  # v7-S1: non-static class/struct data member (ADR-25 D1)
NODE_GLOBAL_VARIABLE = "GlobalVariable"  # v7-S1: namespace/file/static member (ADR-25 D1)
NODE_MACRO = "Macro"
NODE_TYPE_ALIAS = "TypeAlias"

ALL_NODE_TYPES: frozenset[str] = frozenset(
    {
        NODE_FILE,
        NODE_NAMESPACE,
        NODE_CLASS,
        NODE_FUNCTION,
        NODE_VARIABLE,
        NODE_FIELD,
        NODE_GLOBAL_VARIABLE,
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
