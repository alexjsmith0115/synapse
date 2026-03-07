from synapse.graph.connection import GraphConnection


def upsert_contains(conn: GraphConnection, from_path: str, to_full_name: str) -> None:
    """Create CONTAINS edge. from_path is a file or directory path; to_full_name is any symbol."""
    conn.execute(
        "MATCH (src {path: $from_id}), (dst {full_name: $to_id}) "
        "MERGE (src)-[:CONTAINS]->(dst)",
        {"from_id": from_path, "to_id": to_full_name},
    )


def upsert_contains_symbol(conn: GraphConnection, from_full_name: str, to_full_name: str) -> None:
    """Create CONTAINS edge between two symbols (e.g. Class -> Method)."""
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


def upsert_implements(conn: GraphConnection, class_full_name: str, interface_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Class {full_name: $cls}), (dst:Class {full_name: $iface}) "
        "MERGE (src)-[:IMPLEMENTS]->(dst)",
        {"cls": class_full_name, "iface": interface_full_name},
    )


def upsert_overrides(conn: GraphConnection, method_full_name: str, base_method_full_name: str) -> None:
    conn.execute(
        "MATCH (src:Method {full_name: $method}), (dst:Method {full_name: $base}) "
        "MERGE (src)-[:OVERRIDES]->(dst)",
        {"method": method_full_name, "base": base_method_full_name},
    )


def upsert_references(conn: GraphConnection, from_full_name: str, type_full_name: str) -> None:
    conn.execute(
        "MATCH (src {full_name: $from_id}), (dst:Class {full_name: $to_id}) "
        "MERGE (src)-[:REFERENCES]->(dst)",
        {"from_id": from_full_name, "to_id": type_full_name},
    )
