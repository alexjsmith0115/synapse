from datetime import datetime, timezone

from synapse.indexer.sync import SyncResult, compute_sync_diff


def _ts(year=2026, month=3, day=20, hour=12) -> str:
    """Return an ISO timestamp string."""
    return datetime(year, month, day, hour, tzinfo=timezone.utc).isoformat()


def _mtime(year=2026, month=3, day=20, hour=14) -> float:
    """Return a POSIX timestamp (float)."""
    return datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp()


def test_stale_file_detected():
    graph = {"/proj/a.cs": _ts(hour=10)}
    disk = {"/proj/a.cs": _mtime(hour=14)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == {"/proj/a.cs"}
    assert unchanged == set()


def test_fresh_file_unchanged():
    graph = {"/proj/a.cs": _ts(hour=14)}
    disk = {"/proj/a.cs": _mtime(hour=10)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == set()
    assert unchanged == {"/proj/a.cs"}


def test_deleted_file_detected():
    graph = {"/proj/a.cs": _ts(), "/proj/gone.cs": _ts()}
    disk = {"/proj/a.cs": _mtime(hour=10)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == {"/proj/gone.cs"}
    assert to_reindex == set()
    assert unchanged == {"/proj/a.cs"}


def test_new_file_detected():
    graph = {"/proj/a.cs": _ts(hour=14)}
    disk = {"/proj/a.cs": _mtime(hour=10), "/proj/new.cs": _mtime(hour=15)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == {"/proj/new.cs"}
    assert unchanged == {"/proj/a.cs"}


def test_empty_graph_all_new():
    graph = {}
    disk = {"/proj/a.cs": _mtime(), "/proj/b.cs": _mtime()}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == {"/proj/a.cs", "/proj/b.cs"}
    assert unchanged == set()


def test_empty_disk_all_deleted():
    graph = {"/proj/a.cs": _ts(), "/proj/b.cs": _ts()}
    disk = {}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == {"/proj/a.cs", "/proj/b.cs"}
    assert to_reindex == set()
    assert unchanged == set()


def test_no_changes():
    graph = {"/proj/a.cs": _ts(hour=14)}
    disk = {"/proj/a.cs": _mtime(hour=10)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == set()
    assert unchanged == {"/proj/a.cs"}


def test_sync_result_total():
    r = SyncResult(updated=3, deleted=1, unchanged=10)
    assert r.updated == 3
    assert r.deleted == 1
    assert r.unchanged == 10
