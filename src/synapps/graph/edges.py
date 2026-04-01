from synapps.graph.connection import GraphConnection


def upsert_repo_contains_dir(conn: GraphConnection, repo_path: str, dir_path: str) -> None:
    conn.execute(
        "MATCH (src:Repository {path: $repo}), (dst:Directory {path: $dir}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"repo": repo_path, "dir": dir_path},
    )


def upsert_dir_contains(conn: GraphConnection, parent_path: str, child_path: str) -> None:
    conn.execute(
        "MATCH (src {path: $parent}), (dst {path: $child}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"parent": parent_path, "child": child_path},
    )


def upsert_file_contains_symbol(conn: GraphConnection, file_path: str, symbol_full_name: str) -> None:
    conn.execute(
        "MATCH (src:File {path: $file}), (dst {full_name: $sym}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"file": file_path, "sym": symbol_full_name},
    )


def upsert_contains_symbol(conn: GraphConnection, from_full_name: str, to_full_name: str) -> None:
    conn.execute(
        "MATCH (src {full_name: $from_id}), (dst {full_name: $to_id}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"from_id": from_full_name, "to_id": to_full_name},
    )


def upsert_calls(
    conn: GraphConnection,
    caller_full_name: str,
    callee_full_name: str,
    line: int | None = None,
    col: int | None = None,
) -> None:
    if line is not None:
        conn.execute(
            "MATCH (src:Method {full_name: $caller}), (dst:Method {full_name: $callee}) "
            "MERGE (src)-[r:CALLS]->(dst) "
            "SET r.call_sites = coalesce(r.call_sites, []) + [[$line, $col]]",
            {"caller": caller_full_name, "callee": callee_full_name, "line": line, "col": col},
        )
    else:
        conn.execute(
            "MATCH (src:Method {full_name: $caller}), (dst:Method {full_name: $callee}) "
            "MERGE (src)-[:CALLS]->(dst)",
            {"caller": caller_full_name, "callee": callee_full_name},
        )


def upsert_module_calls(
    conn: GraphConnection,
    caller_full_name: str,
    callee_full_name: str,
    line: int | None = None,
    col: int | None = None,
) -> None:
    """CALLS edge from a module :Class node (kind='module') to a :Method node."""
    if line is not None:
        conn.execute(
            "MATCH (src:Class {full_name: $caller}), (dst:Method {full_name: $callee}) "
            "MERGE (src)-[r:CALLS]->(dst) "
            "SET r.call_sites = coalesce(r.call_sites, []) + [[$line, $col]]",
            {"caller": caller_full_name, "callee": callee_full_name, "line": line, "col": col},
        )
    else:
        conn.execute(
            "MATCH (src:Class {full_name: $caller}), (dst:Method {full_name: $callee}) "
            "MERGE (src)-[:CALLS]->(dst)",
            {"caller": caller_full_name, "callee": callee_full_name},
        )


def upsert_inherits(conn: GraphConnection, child_full_name: str, parent_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Class {full_name: $child}), (dst:Class {full_name: $parent}) "
        "MERGE (src)-[:INHERITS]->(dst)",
        {"child": child_full_name, "parent": parent_full_name},
    )


def upsert_interface_inherits(conn: GraphConnection, child_full_name: str, parent_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Interface {full_name: $child}), (dst:Interface {full_name: $parent}) "
        "MERGE (src)-[:INHERITS]->(dst)",
        {"child": child_full_name, "parent": parent_full_name},
    )


def upsert_implements(conn: GraphConnection, class_full_name: str, interface_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Class {full_name: $cls}), (dst {full_name: $iface}) "
        "WHERE dst:Interface OR dst:Class "
        "MERGE (src)-[:IMPLEMENTS]->(dst)",
        {"cls": class_full_name, "iface": interface_full_name},
    )


def upsert_method_implements(conn: GraphConnection, impl_method: str, iface_method: str) -> None:
    conn.execute(
        "MATCH (impl:Method {full_name: $impl}), (iface:Method {full_name: $iface}) "
        "MERGE (impl)-[:IMPLEMENTS]->(iface)",
        {"impl": impl_method, "iface": iface_method},
    )
    # DISPATCHES_TO is the traversal-friendly inverse: iface → impl.
    # Allows [:CALLS|DISPATCHES_TO*] paths to cross interface dispatch boundaries.
    conn.execute(
        "MATCH (impl:Method {full_name: $impl}), (iface:Method {full_name: $iface}) "
        "MERGE (iface)-[:DISPATCHES_TO]->(impl)",
        {"impl": impl_method, "iface": iface_method},
    )


def upsert_abstract_dispatches_to(conn: GraphConnection, child_method: str, parent_method: str) -> None:
    """DISPATCHES_TO from abstract parent method to concrete child method.

    Unlike upsert_method_implements, no IMPLEMENTS edge is created —
    OVERRIDES already exists from OverridesIndexer for ABC inheritance.
    """
    conn.execute(
        "MATCH (parent:Method {full_name: $parent}), (child:Method {full_name: $child}) "
        "MERGE (parent)-[:DISPATCHES_TO]->(child)",
        {"parent": parent_method, "child": child_method},
    )


def upsert_overrides(conn: GraphConnection, method_full_name: str, base_method_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $method}), (dst:Method {full_name: $base}) "
        "MERGE (src)-[:OVERRIDES]->(dst)",
        {"method": method_full_name, "base": base_method_full_name},
    )


def upsert_imports(conn: GraphConnection, file_path: str, package_full_name: str) -> None:
    conn.execute(
        "MATCH (src:File {path: $file}), (dst:Package {full_name: $pkg}) "
        "MERGE (src)-[:IMPORTS]->(dst)",
        {"file": file_path, "pkg": package_full_name},
    )


def upsert_symbol_imports(conn: GraphConnection, file_path: str, symbol_full_name: str) -> None:
    """Create IMPORTS edge from a File to any symbol node (not just Package). Used for Python from-import."""
    conn.execute(
        "MATCH (src:File {path: $file}), (dst {full_name: $sym}) "
        "MERGE (src)-[:IMPORTS]->(dst)",
        {"file": file_path, "sym": symbol_full_name},
    )


def upsert_references(conn: GraphConnection, source_full_name: str, target_full_name: str, kind: str) -> None:
    conn.execute(
        "MATCH (src {full_name: $source}), (dst {full_name: $target}) "
        "WHERE dst:Class OR dst:Interface "
        "MERGE (src)-[r:REFERENCES {kind: $kind}]->(dst)",
        {"source": source_full_name, "target": target_full_name, "kind": kind},
    )


def batch_upsert_calls(conn: GraphConnection, batch: list[dict]) -> None:
    """Batch-write CALLS edges from Method nodes with call_sites."""
    if not batch:
        return
    conn.execute(
        "UNWIND $batch AS row "
        "MATCH (src:Method {full_name: row.caller}), (dst:Method {full_name: row.callee}) "
        "MERGE (src)-[r:CALLS]->(dst) "
        "SET r.call_sites = coalesce(r.call_sites, []) + [[row.line, row.col]]",
        {"batch": batch},
    )


def batch_upsert_module_calls(conn: GraphConnection, batch: list[dict]) -> None:
    """Batch-write CALLS edges from module :Class nodes with call_sites."""
    if not batch:
        return
    conn.execute(
        "UNWIND $batch AS row "
        "MATCH (src:Class {full_name: row.caller}), (dst:Method {full_name: row.callee}) "
        "MERGE (src)-[r:CALLS]->(dst) "
        "SET r.call_sites = coalesce(r.call_sites, []) + [[row.line, row.col]]",
        {"batch": batch},
    )


def delete_outgoing_edges_for_file(conn: GraphConnection, file_path: str) -> None:
    """Delete all outgoing resolution edges from symbols in a file.

    Per D-09: only outgoing edges from changed files; incoming edges intact.
    Per D-10: single consistent behavior, no flags.
    """
    # CALLS + REFERENCES + INHERITS + IMPLEMENTS + DISPATCHES_TO + OVERRIDES from file's symbols
    conn.execute(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n)-[r]->() "
        "WHERE type(r) IN ['CALLS', 'REFERENCES', 'INHERITS', 'IMPLEMENTS', 'DISPATCHES_TO', 'OVERRIDES', 'SERVES', 'HTTP_CALLS', 'TESTS'] "
        "DELETE r",
        {"path": file_path},
    )
    # IMPORTS from the file node itself
    conn.execute(
        "MATCH (f:File {path: $path})-[r:IMPORTS]->() DELETE r",
        {"path": file_path},
    )


def batch_upsert_references(conn: GraphConnection, batch: list[dict]) -> None:
    """Batch-write REFERENCES edges.

    First tries to match existing target nodes. For any remaining unmatched
    targets (library types not in the graph), creates stub Class nodes so
    REFERENCES edges can still be created for dependency tracking.
    """
    if not batch:
        return
    # Match existing target nodes
    conn.execute(
        "UNWIND $batch AS row "
        "MATCH (src {full_name: row.source}), (dst {full_name: row.target}) "
        "WHERE dst:Class OR dst:Interface "
        "MERGE (src)-[r:REFERENCES {kind: row.kind}]->(dst)",
        {"batch": batch},
    )
    # Create stubs for library types not yet in the graph
    conn.execute(
        "UNWIND $batch AS row "
        "MATCH (src {full_name: row.source}) "
        "WHERE NOT EXISTS { MATCH (existing {full_name: row.target}) WHERE existing:Class OR existing:Interface } "
        "MERGE (stub:Class {full_name: row.target}) "
        "ON CREATE SET stub.name = split(row.target, '.')[-1], stub.library = true "
        "MERGE (src)-[r:REFERENCES {kind: row.kind}]->(stub)",
        {"batch": batch},
    )


def upsert_serves(conn: GraphConnection, handler_full_name: str, route: str, http_method: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $handler}), (dst:Endpoint {route: $route, http_method: $http_method}) "
        "MERGE (src)-[:SERVES]->(dst)",
        {"handler": handler_full_name, "route": route, "http_method": http_method},
    )


def upsert_http_calls(
    conn: GraphConnection,
    caller_full_name: str,
    route: str,
    http_method: str,
    line: int | None = None,
    col: int | None = None,
) -> None:
    if line is not None:
        conn.execute(
            "MATCH (src:Method {full_name: $caller}), (dst:Endpoint {route: $route, http_method: $http_method}) "
            "MERGE (src)-[r:HTTP_CALLS]->(dst) "
            "SET r.call_sites = coalesce(r.call_sites, []) + [[$line, $col]]",
            {"caller": caller_full_name, "route": route, "http_method": http_method, "line": line, "col": col},
        )
    else:
        conn.execute(
            "MATCH (src:Method {full_name: $caller}), (dst:Endpoint {route: $route, http_method: $http_method}) "
            "MERGE (src)-[:HTTP_CALLS]->(dst)",
            {"caller": caller_full_name, "route": route, "http_method": http_method},
        )


def batch_upsert_serves(conn: GraphConnection, batch: list[dict]) -> None:
    """Batch-write SERVES edges from Method nodes to Endpoint nodes."""
    if not batch:
        return
    conn.execute(
        "UNWIND $batch AS row "
        "MATCH (src:Method {full_name: row.handler}), (dst:Endpoint {route: row.route, http_method: row.http_method}) "
        "MERGE (src)-[:SERVES]->(dst)",
        {"batch": batch},
    )


def batch_upsert_http_calls(conn: GraphConnection, batch: list[dict]) -> None:
    """Batch-write HTTP_CALLS edges from Method nodes to Endpoint nodes."""
    if not batch:
        return
    conn.execute(
        "UNWIND $batch AS row "
        "MATCH (src:Method {full_name: row.caller}), (dst:Endpoint {route: row.route, http_method: row.http_method}) "
        "MERGE (src)-[r:HTTP_CALLS]->(dst) "
        "SET r.call_sites = coalesce(r.call_sites, []) + [[row.line, row.col]]",
        {"batch": batch},
    )


def delete_orphan_endpoints(conn: GraphConnection, repo_path: str) -> None:
    """Remove orphaned endpoints safely for shared-mode graphs.

    Step 1: Remove this repository's CONTAINS edge to endpoints with no
    SERVES or HTTP_CALLS edges.
    Step 2: Delete Endpoint nodes that are fully orphaned (no CONTAINS,
    SERVES, or HTTP_CALLS from any source).
    """
    conn.execute(
        "MATCH (r:Repository {path: $repo})-[c:CONTAINS]->(ep:Endpoint) "
        "WHERE NOT ()-[:SERVES]->(ep) AND NOT ()-[:HTTP_CALLS]->(ep) "
        "DELETE c",
        {"repo": repo_path},
    )
    conn.execute(
        "MATCH (ep:Endpoint) "
        "WHERE NOT ()-[:SERVES]->(ep) AND NOT ()-[:HTTP_CALLS]->(ep) "
        "AND NOT ()-[:CONTAINS]->(ep) "
        "DELETE ep",
        {},
    )
