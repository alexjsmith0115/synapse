from datetime import datetime, timezone

from synapse.graph.connection import GraphConnection


def upsert_repository(conn: GraphConnection, path: str, language: str) -> None:
    path = path.rstrip("/")
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


def upsert_package(conn: GraphConnection, full_name: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Package {full_name: $full_name}) SET n.name = $name",
        {"full_name": full_name, "name": name},
    )


def upsert_interface(conn: GraphConnection, full_name: str, name: str, file_path: str = "", line: int | None = None, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Interface {full_name: $full_name}) SET n.name = $name, n.kind = 'interface', n.file_path = $file_path, n.line = $line, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "file_path": file_path, "line": line, "end_line": end_line},
    )


def upsert_class(conn: GraphConnection, full_name: str, name: str, kind: str, file_path: str = "", line: int | None = None, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Class {full_name: $full_name}) SET n.name = $name, n.kind = $kind, n.file_path = $file_path, n.line = $line, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "kind": kind, "file_path": file_path, "line": line, "end_line": end_line},
    )


def upsert_method(
    conn: GraphConnection,
    full_name: str,
    name: str,
    signature: str,
    is_abstract: bool,
    is_static: bool,
    file_path: str = "",
    line: int | None = None,
    end_line: int = 0,
) -> None:
    conn.execute(
        "MERGE (n:Method {full_name: $full_name}) "
        "SET n.name = $name, n.signature = $sig, n.is_abstract = $is_abstract, n.is_static = $is_static, n.file_path = $file_path, n.line = $line, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "sig": signature, "is_abstract": is_abstract, "is_static": is_static, "file_path": file_path, "line": line, "end_line": end_line},
    )


def upsert_property(conn: GraphConnection, full_name: str, name: str, type_name: str, file_path: str = "", line: int | None = None, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Property {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name, n.file_path = $file_path, n.line = $line, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "type_name": type_name, "file_path": file_path, "line": line, "end_line": end_line},
    )


def upsert_field(conn: GraphConnection, full_name: str, name: str, type_name: str, file_path: str = "", line: int | None = None, end_line: int = 0) -> None:
    conn.execute(
        "MERGE (n:Field {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name, n.file_path = $file_path, n.line = $line, n.end_line = $end_line",
        {"full_name": full_name, "name": name, "type_name": type_name, "file_path": file_path, "line": line, "end_line": end_line},
    )


def delete_file_nodes(conn: GraphConnection, file_path: str) -> None:
    """Children must be deleted before the file node to keep the CONTAINS* traversal path intact."""
    conn.execute(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"path": file_path},
    )
    conn.execute(
        "MATCH (f:File {path: $path}) DETACH DELETE f",
        {"path": file_path},
    )


def collect_summaries(conn: GraphConnection, file_path: str) -> list[dict]:
    """Collect all summaries from :Summarized nodes under a file, for save/restore across re-indexing."""
    rows = conn.query(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n:Summarized) "
        "RETURN n.full_name, n.summary, n.summary_updated_at",
        {"path": file_path},
    )
    return [
        {"full_name": r[0], "summary": r[1], "summary_updated_at": r[2]}
        for r in rows
    ]


def restore_summaries(conn: GraphConnection, summaries: list[dict]) -> None:
    """Restore previously collected summaries. Silently skips nodes that no longer exist."""
    for s in summaries:
        conn.execute(
            "MATCH (n {full_name: $full_name}) "
            "SET n:Summarized, n.summary = $content, n.summary_updated_at = $ts",
            {"full_name": s["full_name"], "content": s["summary"], "ts": s["summary_updated_at"]},
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
