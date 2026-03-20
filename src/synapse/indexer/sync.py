from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from synapse.graph.connection import GraphConnection

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    updated: int
    deleted: int
    unchanged: int


def compute_sync_diff(
    graph_files: dict[str, str],
    disk_files: dict[str, float],
) -> tuple[set[str], set[str], set[str]]:
    """Compare graph state against disk state.

    Args:
        graph_files: {file_path: last_indexed_iso_string} from the graph.
        disk_files: {file_path: mtime_posix_float} from the filesystem.

    Returns:
        (to_delete, to_reindex, unchanged) — three sets of file paths.
        to_reindex includes both new files and stale files.
    """
    graph_paths = set(graph_files)
    disk_paths = set(disk_files)

    to_delete = graph_paths - disk_paths
    new_files = disk_paths - graph_paths

    to_reindex = set(new_files)
    unchanged = set()

    for path in graph_paths & disk_paths:
        last_indexed = datetime.fromisoformat(graph_files[path])
        last_modified = datetime.fromtimestamp(disk_files[path], tz=timezone.utc)
        if last_modified > last_indexed:
            to_reindex.add(path)
        else:
            unchanged.add(path)

    return to_delete, to_reindex, unchanged


def sync_project(
    conn: GraphConnection,
    indexer,
    root_path: str,
    disk_files: dict[str, float],
) -> SyncResult:
    """Sync graph state with filesystem by re-indexing only changed files.

    Args:
        conn: Graph database connection.
        indexer: Indexer instance (with reindex_file and delete_file methods).
        root_path: Project root path.
        disk_files: {file_path: mtime_posix_float} — current files on disk.

    Raises:
        ValueError: If the project has not been indexed yet (no Repository node).
    """
    repo_rows = conn.query(
        "MATCH (r:Repository {path: $path}) RETURN r.path",
        {"path": root_path},
    )
    if not repo_rows:
        raise ValueError(
            f"Project at {root_path!r} is not indexed. "
            "Run 'index' first before syncing."
        )

    rows = conn.query(
        "MATCH (f:File) WHERE f.path STARTS WITH $root "
        "RETURN f.path, f.last_indexed",
        {"root": root_path + "/"},
    )
    graph_files = {row[0]: row[1] for row in rows if row[0] and row[1]}

    to_delete, to_reindex, unchanged = compute_sync_diff(graph_files, disk_files)

    for path in to_delete:
        log.info("Sync: deleting %s", path)
        indexer.delete_file(path)

    reindexed = 0
    for path in to_reindex:
        log.info("Sync: re-indexing %s", path)
        try:
            indexer.reindex_file(path, root_path)
            reindexed += 1
        except Exception:
            log.warning("Sync: failed to re-index %s, skipping", path, exc_info=True)

    return SyncResult(
        updated=reindexed,
        deleted=len(to_delete),
        unchanged=len(unchanged),
    )
