import os
import re
from datetime import datetime, timezone

from synapse.graph.connection import GraphConnection

_MUTATING_PATTERN = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP)\b")

_VALID_KINDS = frozenset({
    "Class", "Interface", "Method", "Property", "Field", "Namespace",
    "File", "Directory", "Repository",
})


def get_symbol(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (n {full_name: $full_name}) RETURN n",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def find_implementations(conn: GraphConnection, interface_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class)-[:IMPLEMENTS]->(i {full_name: $full_name}) RETURN c "
        "UNION "
        "MATCH (c:Class)-[:INHERITS*]->(base:Class)-[:IMPLEMENTS]->(i {full_name: $full_name}) RETURN c",
        {"full_name": interface_full_name},
    )
    if rows:
        return [r[0] for r in rows]
    # Fallback: suffix match for short names (e.g. "IFoo" matches "MyNs.IFoo")
    rows = conn.query(
        "MATCH (c:Class)-[:IMPLEMENTS]->(i) "
        "WHERE i.full_name ENDS WITH ('.' + $name) OR i.full_name = $name "
        "RETURN c "
        "UNION "
        "MATCH (c:Class)-[:INHERITS*]->(base:Class)-[:IMPLEMENTS]->(i) "
        "WHERE i.full_name ENDS WITH ('.' + $name) OR i.full_name = $name "
        "RETURN c",
        {"name": interface_full_name},
    )
    return [r[0] for r in rows]


def find_callers(
    conn: GraphConnection,
    method_full_name: str,
    include_interface_dispatch: bool = True,
) -> list[dict]:
    direct = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) RETURN caller",
        {"full_name": method_full_name},
    )
    if not include_interface_dispatch:
        return [r[0] for r in direct]
    via_iface = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(im:Method)"
        "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) RETURN caller",
        {"full_name": method_full_name},
    )
    seen = set()
    result = []
    for row in direct + via_iface:
        node = row[0]
        key = node.id if hasattr(node, "id") else node.get("full_name")
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result


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
    implements = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i",
        {"full_name": class_full_name},
    )
    return {
        "parents": [r[0] for r in parents],
        "children": [r[0] for r in children],
        "implements": [r[0] for r in implements],
    }


def search_symbols(
    conn: GraphConnection,
    query: str,
    kind: str | None = None,
    namespace: str | None = None,
    file_path: str | None = None,
) -> list[dict]:
    if kind and kind not in _VALID_KINDS:
        raise ValueError(
            f"Unknown symbol kind: {kind!r}. Valid values: {sorted(_VALID_KINDS)}"
        )
    label = f":{kind}" if kind else ""
    conditions = ["n.full_name IS NOT NULL", "n.name CONTAINS $query"]
    params: dict = {"query": query}
    if namespace:
        conditions.append("n.full_name STARTS WITH $namespace")
        params["namespace"] = namespace
    if file_path:
        conditions.append("n.file_path = $file_path")
        params["file_path"] = file_path
    where = " AND ".join(conditions)
    rows = conn.query(f"MATCH (n{label}) WHERE {where} RETURN n", params)
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
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n:Summarized) "
            "WITH DISTINCT n RETURN n",
            {"path": project_path},
        )
    else:
        rows = conn.query("MATCH (n:Summarized) WITH DISTINCT n RETURN n")
    seen: set[int] = set()
    result = []
    for r in rows:
        node = r[0]
        if node.id not in seen:
            seen.add(node.id)
            result.append(node)
    return result


def list_projects(conn: GraphConnection) -> list[dict]:
    rows = conn.query("MATCH (r:Repository) RETURN r")
    return [r[0] for r in rows]


def get_index_status(conn: GraphConnection, project_path: str) -> dict | None:
    project_path = project_path.rstrip("/")
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
        "last_indexed": repo.properties.get("last_indexed"),
        "file_count": file_count[0][0] if file_count else 0,
        "symbol_count": symbol_count[0][0] if symbol_count else 0,
    }


def get_method_symbol_map(conn: GraphConnection) -> dict[tuple[str, int], str]:
    rows = conn.query(
        "MATCH (m:Method)<-[:CONTAINS]-(f:File) RETURN m.full_name, m.line, f.path"
    )
    return {
        (row[2], row[1]): row[0]
        for row in rows
        if row[0] and row[1] is not None and row[2]
    }


def get_symbol_source_info(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (n {full_name: $full_name}) "
        "WHERE n.file_path IS NOT NULL AND n.file_path <> '' "
        "RETURN n.file_path, n.line, n.end_line",
        {"full_name": full_name},
    )
    if not rows:
        return None
    return {"file_path": rows[0][0], "line": rows[0][1], "end_line": rows[0][2]}


def find_type_references(conn: GraphConnection, full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (src)-[r:REFERENCES]->(t {full_name: $full_name}) RETURN src, r.kind",
        {"full_name": full_name},
    )
    return [{"symbol": row[0], "kind": row[1]} for row in rows]


def find_dependencies(conn: GraphConnection, full_name: str, depth: int = 1) -> list[dict]:
    effective_depth = min(depth, 5)
    rows = conn.query(
        f"MATCH p=(n {{full_name: $full_name}})-[:REFERENCES*1..{effective_depth}]->(t) "
        "RETURN t, length(p)",
        {"full_name": full_name},
    )
    return [{"type": row[0], "depth": row[1]} for row in rows]


def get_containing_type(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (parent)-[:CONTAINS]->(n {full_name: $full_name}) "
        "WHERE parent:Class OR parent:Interface "
        "RETURN parent",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def get_members_overview(conn: GraphConnection, full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (n {full_name: $full_name})-[:CONTAINS]->(child) RETURN child",
        {"full_name": full_name},
    )
    return [r[0] for r in rows]


def get_implemented_interfaces(conn: GraphConnection, class_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i",
        {"full_name": class_full_name},
    )
    return [r[0] for r in rows]


def resolve_full_name(conn: GraphConnection, name: str) -> str | list[str]:
    """Resolve a possibly-short symbol name to its full qualified name.

    Tries exact match first, then falls back to suffix matching.
    When suffix matching returns both Class/Interface and Method nodes for the
    same name (e.g. class + its constructor), Class/Interface nodes are preferred
    to avoid spurious ambiguity errors on short class names.
    Returns the original name unchanged if no match is found (lets
    downstream queries fail naturally with empty results).
    """
    rows = conn.query(
        "MATCH (n {full_name: $name}) RETURN n.full_name LIMIT 1",
        {"name": name},
    )
    if rows:
        return rows[0][0]

    rows = conn.query(
        "MATCH (n) WHERE n.full_name ENDS WITH $suffix "
        "RETURN n.full_name, labels(n)",
        {"suffix": "." + name},
    )
    if not rows:
        return name

    # Prefer Class/Interface nodes over Method nodes when disambiguating
    type_nodes = [r for r in rows if any(lbl in ("Class", "Interface") for lbl in r[1])]
    candidates = type_nodes if type_nodes else rows

    if len(candidates) == 1:
        return candidates[0][0]
    return [r[0] for r in candidates]


def check_staleness(conn: GraphConnection, file_path: str) -> dict | None:
    """Check if a file's graph data is stale relative to disk.

    Compares the stored last_indexed ISO timestamp on the File node against
    the file's mtime on disk.
    """
    rows = conn.query(
        "MATCH (f:File {path: $path}) RETURN f.last_indexed, f.path",
        {"path": file_path},
    )
    if not rows:
        return None

    last_indexed_str = rows[0][0]
    if not last_indexed_str:
        return None

    if not os.path.exists(file_path):
        return None

    last_indexed = datetime.fromisoformat(last_indexed_str)
    last_modified = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
    is_stale = last_modified > last_indexed

    return {
        "file_path": file_path,
        "last_indexed": last_indexed_str,
        "last_modified": last_modified.isoformat(),
        "is_stale": is_stale,
    }


def execute_readonly_query(conn: GraphConnection, cypher: str) -> list:
    """Prevents accidental writes via MCP by rejecting mutating Cypher statements."""
    if _MUTATING_PATTERN.search(cypher.upper()):
        raise ValueError("Mutating Cypher statement not allowed")
    return conn.query(cypher)
