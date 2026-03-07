from datetime import datetime, timezone

from synapse.graph.connection import GraphConnection


def upsert_repository(conn: GraphConnection, path: str, language: str) -> None:
    conn.execute(
        "MERGE (n:Repository {path: $path}) SET n.language = $language, n.last_indexed = $ts",
        {"path": path, "language": language, "ts": _now()},
    )


def upsert_directory(conn: GraphConnection, path: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Directory {path: $path}) SET n.name = $name",
        {"path": path, "name": name},
    )


def upsert_file(conn: GraphConnection, path: str, name: str, language: str) -> None:
    conn.execute(
        "MERGE (n:File {path: $path}) SET n.name = $name, n.language = $language, n.last_indexed = $ts",
        {"path": path, "name": name, "language": language, "ts": _now()},
    )


def upsert_namespace(conn: GraphConnection, full_name: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Namespace {full_name: $full_name}) SET n.name = $name",
        {"full_name": full_name, "name": name},
    )


def upsert_class(conn: GraphConnection, full_name: str, name: str, kind: str) -> None:
    conn.execute(
        "MERGE (n:Class {full_name: $full_name}) SET n.name = $name, n.kind = $kind",
        {"full_name": full_name, "name": name, "kind": kind},
    )


def upsert_method(
    conn: GraphConnection,
    full_name: str,
    name: str,
    signature: str,
    is_abstract: bool,
    is_static: bool,
) -> None:
    conn.execute(
        "MERGE (n:Method {full_name: $full_name}) "
        "SET n.name = $name, n.signature = $sig, n.is_abstract = $is_abstract, n.is_static = $is_static",
        {"full_name": full_name, "name": name, "sig": signature, "is_abstract": is_abstract, "is_static": is_static},
    )


def upsert_property(conn: GraphConnection, full_name: str, name: str, type_name: str) -> None:
    conn.execute(
        "MERGE (n:Property {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name",
        {"full_name": full_name, "name": name, "type_name": type_name},
    )


def upsert_field(conn: GraphConnection, full_name: str, name: str, type_name: str) -> None:
    conn.execute(
        "MERGE (n:Field {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name",
        {"full_name": full_name, "name": name, "type_name": type_name},
    )


def delete_file_nodes(conn: GraphConnection, file_path: str) -> None:
    """Delete all nodes that originated from the given file, and their edges."""
    conn.execute(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"path": file_path},
    )
    conn.execute(
        "MATCH (f:File {path: $path}) DETACH DELETE f",
        {"path": file_path},
    )


def set_summary(conn: GraphConnection, full_name: str, content: str) -> None:
    conn.execute(
        "MATCH (n {full_name: $full_name}) "
        "SET n:Summarized, n.summary = $content, n.summary_updated_at = $ts",
        {"full_name": full_name, "content": content, "ts": _now()},
    )


def remove_summary(conn: GraphConnection, full_name: str) -> None:
    conn.execute(
        "MATCH (n:Summarized {full_name: $full_name}) "
        "REMOVE n:Summarized REMOVE n.summary REMOVE n.summary_updated_at",
        {"full_name": full_name},
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
