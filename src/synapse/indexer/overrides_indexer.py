from __future__ import annotations

import logging

from synapse.graph.connection import GraphConnection

log = logging.getLogger(__name__)


class OverridesIndexer:
    """Create OVERRIDES edges by name-matching methods across the INHERITS chain.

    Pure graph query — no LSP needed. Runs after structural indexing + call resolution.
    """

    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn

    def index(self) -> int:
        """Create OVERRIDES edges. Returns count of edges created."""
        self._conn.execute(
            "MATCH (child:Class)-[:INHERITS*]->(ancestor:Class) "
            "MATCH (child)-[:CONTAINS]->(child_method:Method) "
            "MATCH (ancestor)-[:CONTAINS]->(ancestor_method:Method) "
            "WHERE child_method.name = ancestor_method.name "
            "AND child_method.full_name <> ancestor_method.full_name "
            "MERGE (child_method)-[:OVERRIDES]->(ancestor_method)"
        )
        rows = self._conn.query(
            "MATCH ()-[r:OVERRIDES]->() RETURN count(r)"
        )
        count = rows[0][0] if rows else 0
        log.info("OVERRIDES edges created: %d", count)
        return count
