from synapse.graph.connection import GraphConnection


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


def upsert_calls(conn: GraphConnection, caller_full_name: str, callee_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $caller}), (dst:Method {full_name: $callee}) "
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


def upsert_references(conn: GraphConnection, source_full_name: str, target_full_name: str, kind: str) -> None:
    conn.execute(
        "MATCH (src {full_name: $source}), (dst {full_name: $target}) "
        "WHERE dst:Class OR dst:Interface "
        "MERGE (src)-[r:REFERENCES {kind: $kind}]->(dst)",
        {"source": source_full_name, "target": target_full_name, "kind": kind},
    )
