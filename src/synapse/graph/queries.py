from synapse.graph.connection import GraphConnection


def get_symbol(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (n {full_name: $full_name}) RETURN n",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def find_implementations(conn: GraphConnection, interface_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class)-[:IMPLEMENTS]->(i:Class {full_name: $full_name}) RETURN c",
        {"full_name": interface_full_name},
    )
    return [r[0] for r in rows]


def find_callers(conn: GraphConnection, method_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) RETURN caller",
        {"full_name": method_full_name},
    )
    return [r[0] for r in rows]


def find_callees(conn: GraphConnection, method_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (m:Method {full_name: $full_name})-[:CALLS]->(callee:Method) RETURN callee",
        {"full_name": method_full_name},
    )
    return [r[0] for r in rows]


def get_hierarchy(conn: GraphConnection, class_full_name: str) -> dict:
    parents = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:INHERITS*]->(p:Class) RETURN p",
        {"full_name": class_full_name},
    )
    children = conn.query(
        "MATCH (c:Class)-[:INHERITS*]->(p:Class {full_name: $full_name}) RETURN c",
        {"full_name": class_full_name},
    )
    return {"parents": [r[0] for r in parents], "children": [r[0] for r in children]}


def search_symbols(conn: GraphConnection, query: str, kind: str | None = None) -> list[dict]:
    if kind:
        rows = conn.query(
            f"MATCH (n:{kind}) WHERE n.name CONTAINS $query RETURN n",
            {"query": query},
        )
    else:
        rows = conn.query(
            "MATCH (n) WHERE n.name CONTAINS $query RETURN n",
            {"query": query},
        )
    return [r[0] for r in rows]


def get_summary(conn: GraphConnection, full_name: str) -> str | None:
    rows = conn.query(
        "MATCH (n:Summarized {full_name: $full_name}) RETURN n.summary",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def list_summarized(conn: GraphConnection, project_path: str | None = None) -> list[dict]:
    if project_path:
        rows = conn.query(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n:Summarized) RETURN n",
            {"path": project_path},
        )
    else:
        rows = conn.query("MATCH (n:Summarized) RETURN n")
    return [r[0] for r in rows]


def list_projects(conn: GraphConnection) -> list[dict]:
    rows = conn.query("MATCH (r:Repository) RETURN r")
    return [r[0] for r in rows]


def get_index_status(conn: GraphConnection, project_path: str) -> dict | None:
    rows = conn.query(
        "MATCH (r:Repository {path: $path}) RETURN r",
        {"path": project_path},
    )
    if not rows:
        return None
    repo = rows[0][0]
    file_count = conn.query(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File) RETURN count(f)",
        {"path": project_path},
    )
    symbol_count = conn.query(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) WHERE NOT n:File AND NOT n:Directory RETURN count(n)",
        {"path": project_path},
    )
    return {
        "path": project_path,
        "last_indexed": repo.get("last_indexed"),
        "file_count": file_count[0][0] if file_count else 0,
        "symbol_count": symbol_count[0][0] if symbol_count else 0,
    }


def execute_readonly_query(conn: GraphConnection, cypher: str) -> list:
    """Prevents accidental writes via MCP by rejecting mutating Cypher statements."""
    normalized = cypher.strip().upper()
    for mutating in ("CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP"):
        if normalized.startswith(mutating) or f" {mutating} " in normalized:
            raise ValueError(f"Mutating Cypher statement not allowed: {mutating}")
    return conn.query(cypher)
