from synapse.graph.connection import GraphConnection

_INDICES = [
    "CREATE INDEX FOR (n:Repository) ON (n.path)",
    "CREATE INDEX FOR (n:Directory) ON (n.path)",
    "CREATE INDEX FOR (n:File) ON (n.path)",
    "CREATE INDEX FOR (n:Namespace) ON (n.full_name)",
    "CREATE INDEX FOR (n:Class) ON (n.full_name)",
    "CREATE INDEX FOR (n:Method) ON (n.full_name)",
    "CREATE INDEX FOR (n:Property) ON (n.full_name)",
    "CREATE INDEX FOR (n:Field) ON (n.full_name)",
]


def ensure_schema(conn: GraphConnection) -> None:
    """Create graph indices. Safe to call multiple times — FalkorDB ignores duplicate index creation."""
    for statement in _INDICES:
        conn.execute(statement)
