"""Graph schema version constant for ADR-24 writer stamping.

Every ``File`` node written by ``extract_nodes_and_edges`` carries a
``schema_version`` property equal to :data:`SCHEMA_VERSION`.  The
``describe_graph_schema`` introspector (S4) reads this stamp to detect
graphs written by an older version and surfaces an informational note.

ADR-24: live-vs-cached schema discovery + opportunistic version stamp.
"""

from __future__ import annotations

SCHEMA_VERSION: str = "v1"
