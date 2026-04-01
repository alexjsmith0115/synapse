import json
import os
from datetime import datetime, timezone

from synapps.graph.connection import GraphConnection


def upsert_repository(conn: GraphConnection, path: str, language: str) -> None:
    path = path.rstrip("/")
    name = os.path.basename(path)
    conn.execute(
        "MERGE (n:Repository {path: $path}) "
        "WITH n, "
        "CASE "
        "WHEN n.languages IS NULL THEN [$language] "
        "WHEN NOT ($language IN n.languages) THEN n.languages + [$language] "
        "ELSE n.languages "
        "END AS langs "
        "SET n.languages = langs, n.last_indexed = $ts, n.name = $name "
        "REMOVE n.language",
        {"path": path, "language": language, "ts": _now(), "name": name},
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


def upsert_interface(conn: GraphConnection, full_name: str, name: str, file_path: str = "", line: int | None = None, end_line: int = 0, language: str = "") -> None:
    conn.execute(
        "MERGE (n:Interface {full_name: $full_name}) SET n.name = $name, n.kind = 'interface', n.file_path = $file_path, n.line = $line, n.end_line = $end_line, n.language = $language",
        {"full_name": full_name, "name": name, "file_path": file_path, "line": line, "end_line": end_line, "language": language},
    )


def upsert_class(conn: GraphConnection, full_name: str, name: str, kind: str, file_path: str = "", line: int | None = None, end_line: int = 0, language: str = "") -> None:
    conn.execute(
        "MERGE (n:Class {full_name: $full_name}) SET n.name = $name, n.kind = $kind, n.file_path = $file_path, n.line = $line, n.end_line = $end_line, n.language = $language",
        {"full_name": full_name, "name": name, "kind": kind, "file_path": file_path, "line": line, "end_line": end_line, "language": language},
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
    language: str = "",
    is_classmethod: bool = False,
    is_async: bool = False,
) -> None:
    conn.execute(
        "MERGE (n:Method {full_name: $full_name}) "
        "SET n.name = $name, n.signature = $sig, n.is_abstract = $is_abstract, n.is_static = $is_static, "
        "n.file_path = $file_path, n.line = $line, n.end_line = $end_line, n.language = $language, "
        "n.is_classmethod = $is_classmethod, n.is_async = $is_async",
        {
            "full_name": full_name, "name": name, "sig": signature,
            "is_abstract": is_abstract, "is_static": is_static,
            "file_path": file_path, "line": line, "end_line": end_line,
            "language": language, "is_classmethod": is_classmethod, "is_async": is_async,
        },
    )


def upsert_property(conn: GraphConnection, full_name: str, name: str, type_name: str, file_path: str = "", line: int | None = None, end_line: int = 0, language: str = "") -> None:
    conn.execute(
        "MERGE (n:Property {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name, n.file_path = $file_path, n.line = $line, n.end_line = $end_line, n.language = $language",
        {"full_name": full_name, "name": name, "type_name": type_name, "file_path": file_path, "line": line, "end_line": end_line, "language": language},
    )


def upsert_field(conn: GraphConnection, full_name: str, name: str, type_name: str, file_path: str = "", line: int | None = None, end_line: int = 0, language: str = "") -> None:
    conn.execute(
        "MERGE (n:Field {full_name: $full_name}) SET n.name = $name, n.type_name = $type_name, n.file_path = $file_path, n.line = $line, n.end_line = $end_line, n.language = $language",
        {"full_name": full_name, "name": name, "type_name": type_name, "file_path": file_path, "line": line, "end_line": end_line, "language": language},
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


def set_attributes(conn: GraphConnection, full_name: str, attributes: list[str]) -> None:
    conn.execute(
        "MATCH (n {full_name: $full_name}) SET n.attributes = $attrs",
        {"full_name": full_name, "attrs": json.dumps(attributes)},
    )


_ALLOWED_FLAGS = frozenset({"is_abstract", "is_static", "is_classmethod", "is_async"})


def set_metadata_flags(conn: GraphConnection, full_name: str, flags: dict) -> None:
    """Write boolean metadata flags to an existing node. Only whitelisted flag names are accepted."""
    safe_flags = {k: v for k, v in flags.items() if k in _ALLOWED_FLAGS}
    if not safe_flags:
        return
    set_clauses = ", ".join(f"n.{k} = ${k}" for k in safe_flags)
    conn.execute(
        f"MATCH (n {{full_name: $full_name}}) SET {set_clauses}",
        {"full_name": full_name, **safe_flags},
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_last_indexed_commit(conn: GraphConnection, root_path: str, sha: str) -> None:
    conn.execute(
        "MATCH (r:Repository {path: $path}) SET r.last_indexed_commit = $sha",
        {"path": root_path, "sha": sha},
    )


def get_last_indexed_commit(conn: GraphConnection, root_path: str) -> str | None:
    rows = conn.query(
        "MATCH (r:Repository {path: $path}) RETURN r.last_indexed_commit",
        {"path": root_path},
    )
    return rows[0][0] if rows and rows[0][0] else None


def rename_file_node(conn: GraphConnection, old_path: str, new_path: str) -> None:
    new_name = os.path.basename(new_path)
    conn.execute(
        "MATCH (f:File {path: $old}) SET f.path = $new, f.name = $name",
        {"old": old_path, "new": new_path, "name": new_name},
    )
    conn.execute(
        "MATCH (f:File {path: $new})-[:CONTAINS*]->(n) "
        "WHERE n.file_path = $old SET n.file_path = $new",
        {"old": old_path, "new": new_path},
    )


def upsert_endpoint(conn: GraphConnection, route: str, http_method: str, name: str) -> None:
    conn.execute(
        "MERGE (n:Endpoint {route: $route, http_method: $http_method}) "
        "SET n.name = $name",
        {"route": route, "http_method": http_method, "name": name},
    )


def get_file_symbol_names(conn: GraphConnection, file_path: str) -> set[str]:
    rows = conn.query(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n) "
        "WHERE n.full_name IS NOT NULL "
        "RETURN n.full_name",
        {"path": file_path},
    )
    return {row[0] for row in rows}


def delete_orphaned_symbols(
    conn: GraphConnection, file_path: str, current_full_names: set[str]
) -> int:
    # Scope to nodes whose file_path matches this file.  Without the
    # file_path guard, the CONTAINS* traversal walks through shared
    # Namespace/Package nodes and reaches symbols in OTHER files, deleting
    # them when they're not in this file's keep-list.
    rows = conn.query(
        "MATCH (f:File {path: $path})-[:CONTAINS*]->(n) "
        "WHERE n.full_name IS NOT NULL AND NOT n.full_name IN $keep "
        "AND n.file_path = $path "
        "RETURN n.full_name",
        {"path": file_path, "keep": list(current_full_names)},
    )
    orphans = [r[0] for r in rows]
    for fn in orphans:
        conn.execute(
            "MATCH (n {full_name: $fn}) DETACH DELETE n",
            {"fn": fn},
        )
    return len(orphans)
