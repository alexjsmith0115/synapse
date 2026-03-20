from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


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
