import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone

from synapps.graph.connection import GraphConnection

_MUTATING_PATTERN = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP)\b")
_STRING_LITERAL_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"")
_DOTTED_PROPERTY_PATTERN = re.compile(r"\w+\.\w+")

_VALID_KINDS = frozenset({
    "Class", "Interface", "Method", "Property", "Field", "Namespace",
    "File", "Directory", "Repository",
})

_TEST_PATH_PATTERN = (
    r"(?:"
    r".*[/\\][A-Za-z0-9.]*[Tt]ests?[/\\].*"
    r"|.*[/\\]__tests__[/\\].*"
    r"|.*[/\\]test-[A-Za-z0-9_-]+[/\\].*"
    r"|.*\.(?:test|spec)\.[jt]sx?$"
    r"|.*_test\.[a-z]+$"
    r"|.*[/\\]src[/\\]test[/\\].*"
    r")"
)


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
    if rows:
        return [r[0] for r in rows]
    return []


def find_neighborhood(conn: GraphConnection, full_name: str) -> dict:
    """Return all directly connected neighbors for a given symbol.

    Uses two separate queries (outgoing and incoming) to avoid Memgraph
    OPTIONAL MATCH + collect issues with bidirectional patterns.
    """
    outgoing = conn.query(
        "MATCH (n {full_name: $full_name})-[r]->(neighbor) "
        "RETURN neighbor, type(r) AS rel_type",
        {"full_name": full_name},
    )
    incoming = conn.query(
        "MATCH (caller)-[r]->(n {full_name: $full_name}) "
        "RETURN caller AS neighbor, type(r) AS rel_type",
        {"full_name": full_name},
    )

    seen: set[tuple[str, str, str]] = set()
    neighbors: list[dict] = []

    def _extract(rows: list, direction: str) -> None:
        for row in rows:
            node = row[0]
            rel_type = row[1]
            fn = node.get("full_name", "") if isinstance(node, Mapping) else ""
            if not fn:
                continue
            key = (fn, rel_type, direction)
            if key in seen:
                continue
            seen.add(key)
            neighbors.append({
                "full_name": fn,
                "name": node.get("name", fn.split(".")[-1]) if isinstance(node, Mapping) else fn.split(".")[-1],
                "kind": node.get("kind", "") if isinstance(node, Mapping) else "",
                "file_path": node.get("file_path", "") if isinstance(node, Mapping) else "",
                "line": node.get("line", 0) if isinstance(node, Mapping) else 0,
                "signature": node.get("signature", "") if isinstance(node, Mapping) else "",
                "rel_type": rel_type,
                "direction": direction,
            })

    _extract(outgoing, "out")
    _extract(incoming, "in")

    return {"full_name": full_name, "neighbors": neighbors}


def find_callers(
    conn: GraphConnection,
    method_full_name: str,
    include_interface_dispatch: bool = True,
    exclude_test_callers: bool = True,
) -> list[dict]:
    if exclude_test_callers:
        direct = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) "
            "WHERE NOT caller.file_path =~ $test_pattern RETURN caller",
            {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
        )
    else:
        direct = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(m:Method {full_name: $full_name}) RETURN caller",
            {"full_name": method_full_name},
        )
    if not include_interface_dispatch:
        return [r[0] for r in direct]
    if exclude_test_callers:
        via_iface = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(im:Method)"
            "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) "
            "WHERE NOT caller.file_path =~ $test_pattern RETURN caller",
            {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
        )
        # Abstract/virtual override dispatch: parent method has DISPATCHES_TO to concrete override.
        # upsert_abstract_dispatches_to creates only DISPATCHES_TO (no IMPLEMENTS), so we
        # need a separate traversal to find callers of the abstract parent that reach this method.
        via_dispatch = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(parent:Method)"
            "-[:DISPATCHES_TO]->(m:Method {full_name: $full_name}) "
            "WHERE NOT caller.file_path =~ $test_pattern RETURN caller",
            {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
        )
    else:
        via_iface = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(im:Method)"
            "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) RETURN caller",
            {"full_name": method_full_name},
        )
        via_dispatch = conn.query(
            "MATCH (caller:Method)-[:CALLS]->(parent:Method)"
            "-[:DISPATCHES_TO]->(m:Method {full_name: $full_name}) RETURN caller",
            {"full_name": method_full_name},
        )
    seen = set()
    result = []
    for row in direct + via_iface + via_dispatch:
        node = row[0]
        key = node.element_id
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result


def find_callees(
    conn: GraphConnection,
    method_full_name: str,
    include_interface_dispatch: bool = True,
) -> list[dict]:
    rows = conn.query(
        "MATCH (m:Method {full_name: $full_name})-[:CALLS]->(callee:Method) RETURN callee",
        {"full_name": method_full_name},
    )
    if not include_interface_dispatch:
        return [r[0] for r in rows]
    via_dispatch = conn.query(
        "MATCH (m:Method {full_name: $full_name})-[:CALLS]->(:Method)-[:DISPATCHES_TO]->(concrete:Method) "
        "RETURN concrete",
        {"full_name": method_full_name},
    )
    seen = set()
    result = []
    for row in rows + via_dispatch:
        node = row[0]
        key = node.element_id
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result


def get_hierarchy(conn: GraphConnection, class_full_name: str) -> dict:
    parents = conn.query(
        "MATCH (c {full_name: $full_name})-[:INHERITS*]->(p) "
        "WHERE p:Class OR p:Interface RETURN p",
        {"full_name": class_full_name},
    )
    children = conn.query(
        "MATCH (c)-[:INHERITS*]->(p {full_name: $full_name}) RETURN c "
        "UNION "
        "MATCH (c:Class)-[:IMPLEMENTS]->(p {full_name: $full_name}) RETURN c",
        {"full_name": class_full_name},
    )
    implements = conn.query(
        "MATCH (c {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i",
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
    language: str | None = None,
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
    if language:
        conditions.append("n.language = $language")
        params["language"] = language
    where = " AND ".join(conditions)
    rows = conn.query(
        f"MATCH (n{label}) WHERE {where} RETURN n "
        "ORDER BY CASE WHEN n.name = $query THEN 0 ELSE 1 END, n.name",
        params,
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
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n:Summarized) "
            "WITH DISTINCT n RETURN n",
            {"path": project_path},
        )
    else:
        rows = conn.query("MATCH (n:Summarized) WITH DISTINCT n RETURN n")
    seen: set[str] = set()
    result = []
    for r in rows:
        node = r[0]
        if node.element_id not in seen:
            seen.add(node.element_id)
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
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File) RETURN count(DISTINCT f)",
        {"path": project_path},
    )
    symbol_count = conn.query(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) WHERE NOT n:File AND NOT n:Directory RETURN count(DISTINCT n)",
        {"path": project_path},
    )
    breakdown_rows = conn.query(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) "
        "WHERE NOT n:File AND NOT n:Directory "
        "WITH DISTINCT n "
        "UNWIND labels(n) AS label "
        "WITH label WHERE label <> 'Summarized' "
        "RETURN label, count(*) AS cnt "
        "ORDER BY cnt DESC",
        {"path": project_path},
    )
    symbol_breakdown = {row[0]: row[1] for row in breakdown_rows}
    return {
        "path": project_path,
        "languages": repo.get("languages", [repo.get("language", "unknown")]),
        "last_indexed": repo.get("last_indexed"),
        "file_count": file_count[0][0] if file_count else 0,
        "symbol_count": symbol_count[0][0] if symbol_count else 0,
        "symbol_breakdown": symbol_breakdown,
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


def find_type_references(conn: GraphConnection, full_name: str, kind: str | None = None) -> list[dict]:
    # Build WHERE clause conditionally — Memgraph may not support `$param IS NULL`
    kind_clause = "WHERE r.kind = $kind " if kind else ""
    rows = conn.query(
        "MATCH (src)-[r:REFERENCES]->(t {full_name: $full_name}) "
        f"{kind_clause}"
        "RETURN src, r.kind",
        {"full_name": full_name, "kind": kind},
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


def find_field_dependencies(conn: GraphConnection, full_name: str) -> list[dict]:
    """Return annotated field dependencies for a class — Field nodes with non-empty type_name.

    Augments find_dependencies with field-level DI info for Java classes where @Autowired,
    @Inject, etc. are the primary dependency injection mechanism.
    """
    import json as _json
    rows = conn.query(
        "MATCH (cls {full_name: $full_name})-[:CONTAINS]->(f:Field) "
        "WHERE f.type_name IS NOT NULL AND f.type_name <> '' "
        "RETURN f.name, f.type_name, f.attributes",
        {"full_name": full_name},
    )
    result = []
    for name, type_name, attributes_raw in rows:
        try:
            annotations = _json.loads(attributes_raw) if attributes_raw else []
        except (ValueError, TypeError):
            annotations = []
        result.append({"name": name, "type_name": type_name, "annotations": annotations})
    return result


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


def get_called_members(
    conn: GraphConnection,
    method_full_name: str,
    dep_full_name: str,
) -> list[dict]:
    """Return only the members of dep that method actually calls."""
    rows = conn.query(
        "MATCH (m:Method {full_name: $method})-[:CALLS]->(callee)<-[:CONTAINS]-(dep {full_name: $dep}) "
        "RETURN DISTINCT callee",
        {"method": method_full_name, "dep": dep_full_name},
    )
    return [r[0] for r in rows]


def get_constructor(conn: GraphConnection, full_name: str) -> dict | None:
    rows = conn.query(
        "MATCH (cls {full_name: $full_name})-[:CONTAINS]->(m:Method) "
        "WHERE (cls:Class OR cls:Interface) AND m.name = cls.name "
        "RETURN m",
        {"full_name": full_name},
    )
    return rows[0][0] if rows else None


def get_implemented_interfaces(conn: GraphConnection, class_full_name: str) -> list[dict]:
    rows = conn.query(
        "MATCH (c:Class {full_name: $full_name})-[:IMPLEMENTS]->(i:Interface) RETURN i",
        {"full_name": class_full_name},
    )
    return [r[0] for r in rows]


def resolve_full_name(conn: GraphConnection, name: str) -> str | list[str] | None:
    """Resolve a possibly-short symbol name to its full qualified name.

    Tries exact match first, then falls back to suffix matching.
    When suffix matching returns both Class/Interface and Method nodes for the
    same name (e.g. class + its constructor), Class/Interface nodes are preferred
    to avoid spurious ambiguity errors on short class names.
    Returns None if no match is found.
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
        return None

    # Prefer Class/Interface nodes over Method nodes when disambiguating
    type_nodes = [r for r in rows if any(lbl in ("Class", "Interface") for lbl in r[1])]
    candidates = type_nodes if type_nodes else rows

    if len(candidates) == 1:
        return candidates[0][0]
    return [r[0] for r in candidates]


def suggest_similar_names(conn: GraphConnection, name: str, limit: int = 5) -> list[str]:
    """Find symbols with names similar to the given name, for 'did you mean?' suggestions."""
    # Extract the simple name (last segment after dots)
    simple = name.rsplit(".", 1)[-1]
    rows = conn.query(
        "MATCH (n) WHERE n.name IS NOT NULL AND n.full_name IS NOT NULL "
        "AND n.name CONTAINS $simple "
        "RETURN DISTINCT n.full_name "
        "ORDER BY CASE WHEN n.name = $simple THEN 0 ELSE 1 END, n.full_name "
        "LIMIT $limit",
        {"simple": simple, "limit": limit},
    )
    return [r[0] for r in rows if r[0] is not None]


def resolve_full_name_with_labels(
    conn: GraphConnection, name: str,
) -> str | list[tuple[str, list[str]]] | None:
    """Like resolve_full_name but preserves label information for ambiguous results."""
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
        return None

    type_nodes = [r for r in rows if any(lbl in ("Class", "Interface") for lbl in r[1])]
    candidates = type_nodes if type_nodes else rows

    if len(candidates) == 1:
        return candidates[0][0]
    return [(r[0], list(r[1])) for r in candidates]


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


def find_callers_with_sites(
    conn: GraphConnection,
    method_full_name: str,
) -> list[dict]:
    """Find non-test callers with call-site positions from CALLS edge properties."""
    direct = conn.query(
        "MATCH (caller:Method)-[r:CALLS]->(m:Method {full_name: $full_name}) "
        "WHERE NOT caller.file_path =~ $test_pattern "
        "RETURN caller, coalesce(r.call_sites, []) AS call_sites",
        {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
    )
    via_iface = conn.query(
        "MATCH (caller:Method)-[r:CALLS]->(im:Method)"
        "<-[:IMPLEMENTS]-(m:Method {full_name: $full_name}) "
        "WHERE NOT caller.file_path =~ $test_pattern "
        "RETURN caller, coalesce(r.call_sites, []) AS call_sites",
        {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
    )
    # Abstract/virtual override dispatch: parent method has DISPATCHES_TO to concrete override.
    # upsert_abstract_dispatches_to creates only DISPATCHES_TO (no IMPLEMENTS), so callers of
    # the abstract parent are missed without this traversal.
    via_dispatch = conn.query(
        "MATCH (caller:Method)-[r:CALLS]->(parent:Method)"
        "-[:DISPATCHES_TO]->(m:Method {full_name: $full_name}) "
        "WHERE NOT caller.file_path =~ $test_pattern "
        "RETURN caller, coalesce(r.call_sites, []) AS call_sites",
        {"full_name": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
    )
    seen: set[str] = set()
    result: list[dict] = []
    for row in direct + via_iface + via_dispatch:
        node = row[0]
        key = node.element_id
        if key not in seen:
            seen.add(key)
            result.append({"caller": node, "call_sites": row[1]})
    return result


def find_relevant_deps(
    conn: GraphConnection,
    class_full_name: str,
    method_full_name: str,
) -> list[dict]:
    """Find constructor deps the method actually calls into."""
    rows = conn.query(
        "MATCH (cls {full_name: $class})-[:CONTAINS]->(member)-[:REFERENCES]->(dep) "
        "WHERE dep:Class OR dep:Interface "
        "WITH DISTINCT dep "
        "MATCH (m:Method {full_name: $method})-[:CALLS]->(callee:Method)<-[:CONTAINS]-(dep) "
        "RETURN DISTINCT dep",
        {"class": class_full_name, "method": method_full_name},
    )
    return [r[0] for r in rows]


def find_test_coverage(
    conn: GraphConnection,
    method_full_name: str,
) -> list[dict]:
    """Find test methods that transitively call the given method (up to 4 hops)."""
    direct = conn.query(
        "MATCH (t:Method)-[:CALLS*1..4]->(m:Method {full_name: $method}) "
        "WHERE t.file_path =~ $test_pattern "
        "RETURN DISTINCT t.full_name, t.file_path",
        {"method": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
    )
    via_iface = conn.query(
        "MATCH (t:Method)-[:CALLS*1..4]->(im:Method)<-[:IMPLEMENTS]-(m:Method {full_name: $method}) "
        "WHERE t.file_path =~ $test_pattern "
        "RETURN DISTINCT t.full_name, t.file_path",
        {"method": method_full_name, "test_pattern": _TEST_PATH_PATTERN},
    )
    seen: set[str] = set()
    result: list[dict] = []
    for r in direct + via_iface:
        if r[0] not in seen:
            seen.add(r[0])
            result.append({"full_name": r[0], "file_path": r[1]})
    return result


def find_all_deps(
    conn: GraphConnection,
    class_full_name: str,
) -> list[dict]:
    """Find all types referenced by members of the given class."""
    rows = conn.query(
        "MATCH (cls {full_name: $class})-[:CONTAINS]->(member)-[:REFERENCES]->(dep) "
        "WHERE dep:Class OR dep:Interface "
        "RETURN DISTINCT dep",
        {"class": class_full_name},
    )
    return [r[0] for r in rows]


def find_tests_for(conn: GraphConnection, method_full_name: str) -> list[dict]:
    """Find test methods that directly cover a production method via TESTS edges."""
    rows = conn.query(
        "MATCH (t:Method)-[:TESTS]->(m:Method {full_name: $fn}) "
        "RETURN t.full_name, t.file_path, t.line",
        {"fn": method_full_name},
    )
    return [{"full_name": r[0], "file_path": r[1], "line": r[2]} for r in rows]


def get_served_endpoint(conn: GraphConnection, method_full_name: str) -> dict | None:
    """Return the HTTP endpoint this method serves, if any."""
    rows = conn.query(
        "MATCH (m:Method {full_name: $fn})-[:SERVES]->(ep) "
        "RETURN ep.http_method, ep.route",
        {"fn": method_full_name},
    )
    if not rows:
        return None
    return {"http_method": rows[0][0], "route": rows[0][1]}


def find_http_callers(conn: GraphConnection, method_full_name: str) -> list[dict]:
    """Find methods that make HTTP calls to the endpoint this method serves."""
    rows = conn.query(
        "MATCH (caller:Method)-[r:HTTP_CALLS]->(ep)<-[:SERVES]-(m:Method {full_name: $fn}) "
        "RETURN caller.full_name, caller.file_path, ep.route",
        {"fn": method_full_name},
    )
    return [{"full_name": r[0], "file_path": r[1], "route": r[2]} for r in rows]


def find_http_endpoints(
    conn: GraphConnection,
    route: str | None = None,
    http_method: str | None = None,
    language: str | None = None,
) -> list:
    """Return (ep, has_server_handler, handler_or_None) tuples for HTTP endpoints.

    When language is set, only endpoints with a SERVES handler in that language
    are returned (client-only endpoints are excluded).
    """
    conditions = []
    params: dict = {}
    if route is not None:
        conditions.append("ep.route CONTAINS $route")
        params["route"] = route
    if http_method is not None:
        conditions.append("ep.http_method = $http_method")
        params["http_method"] = http_method

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    if language is not None:
        # Enforce language filter: endpoints without a matching handler are excluded
        params["language"] = language
        cypher = (
            f"MATCH (ep:Endpoint){where_clause} "
            "MATCH (handler:Method)-[:SERVES]->(ep) "
            "WHERE handler.language = $language "
            "WITH ep, handler, true AS has_server "
            "RETURN ep, has_server, handler "
            "ORDER BY ep.route, ep.http_method"
        )
    else:
        cypher = (
            f"MATCH (ep:Endpoint){where_clause} "
            "OPTIONAL MATCH (handler:Method)-[:SERVES]->(ep) "
            "WITH ep, handler, count(handler) > 0 AS has_server "
            "RETURN ep, has_server, handler "
            "ORDER BY ep.route, ep.http_method"
        )

    rows = conn.query(cypher, params)
    return [[r[0], r[1], r[2]] for r in rows]


def find_http_dependency(conn: GraphConnection, route: str, http_method: str) -> dict:
    """Return handler and callers for an exact route+http_method match.

    Uses exact match (per D-05) on both route and http_method.
    Returns dict with keys: ep, handler, callers.
    """
    handler_rows = conn.query(
        "MATCH (ep:Endpoint {route: $route, http_method: $http_method}) "
        "OPTIONAL MATCH (handler:Method)-[:SERVES]->(ep) "
        "RETURN ep, handler",
        {"route": route, "http_method": http_method},
    )
    if not handler_rows:
        return {"ep": None, "handler": None, "callers": []}

    ep = handler_rows[0][0]
    handler = handler_rows[0][1]

    caller_rows = conn.query(
        "MATCH (ep:Endpoint {route: $route, http_method: $http_method}) "
        "OPTIONAL MATCH (caller:Method)-[:HTTP_CALLS]->(ep) "
        "RETURN caller",
        {"route": route, "http_method": http_method},
    )
    callers = [r[0] for r in caller_rows if r[0] is not None]

    return {"ep": ep, "handler": handler, "callers": callers}


def execute_readonly_query(conn: GraphConnection, cypher: str) -> list:
    """Prevents accidental writes via MCP by rejecting mutating Cypher statements."""
    stripped = _STRING_LITERAL_PATTERN.sub("", cypher)
    stripped = _DOTTED_PROPERTY_PATTERN.sub("", stripped)
    if _MUTATING_PATTERN.search(stripped.upper()):
        raise ValueError("Mutating Cypher statement not allowed")
    return conn.query_with_timeout(cypher)
